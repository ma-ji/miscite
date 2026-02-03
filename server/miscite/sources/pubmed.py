from __future__ import annotations

from dataclasses import dataclass, field
import re
import threading
import xml.etree.ElementTree as ET

import requests

from server.miscite.analysis.shared.normalize import normalize_doi
from server.miscite.core.cache import Cache
from server.miscite.sources.http import backoff_sleep

_EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_ESEARCH_URL = f"{_EUTILS_BASE}/esearch.fcgi"
_ESUMMARY_URL = f"{_EUTILS_BASE}/esummary.fcgi"
_EFETCH_URL = f"{_EUTILS_BASE}/efetch.fcgi"

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.replace("\n", " ").split())
    return cleaned or None


def _parse_year(pubdate: str | None) -> int | None:
    if not pubdate:
        return None
    m = _YEAR_RE.search(pubdate)
    if not m:
        return None
    try:
        return int(m.group(0))
    except Exception:
        return None


def _first_author_family(authors: object) -> str | None:
    if not isinstance(authors, list) or not authors:
        return None
    first = authors[0]
    if not isinstance(first, dict):
        return None
    name = first.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    # ESummary author "name" is typically "Family Initials" or "Family, Initials".
    # We want to align with our bibliography parser's "first author" heuristic, which
    # treats the first token as the key for matching.
    primary = name.strip().split(",", 1)[0].strip()
    if not primary:
        primary = name.strip()
    token = primary.split()[0].strip(" .;:")
    return token.lower() if token else None


def _doi_from_articleids(articleids: object) -> str | None:
    if not isinstance(articleids, list):
        return None
    for item in articleids:
        if not isinstance(item, dict):
            continue
        idtype = str(item.get("idtype") or "").strip().lower()
        if idtype != "doi":
            continue
        doi_val = item.get("value")
        if isinstance(doi_val, str):
            doi_norm = normalize_doi(doi_val)
            if doi_norm:
                return doi_norm
    return None


def _pmcid_from_articleids(articleids: object) -> str | None:
    if not isinstance(articleids, list):
        return None
    for item in articleids:
        if not isinstance(item, dict):
            continue
        idtype = str(item.get("idtype") or "").strip().lower()
        if idtype not in {"pmc", "pmcid"}:
            continue
        val = item.get("value")
        if not isinstance(val, str):
            continue
        cleaned = val.strip()
        if not cleaned:
            continue
        if cleaned.upper().startswith("PMC"):
            return "PMC" + cleaned[3:] if cleaned[3:] else cleaned
        if cleaned.isdigit():
            return f"PMC{cleaned}"
    return None


def _summarize_summary_record(record: dict) -> dict:
    pmid = str(record.get("uid") or "").strip() or None
    title = _clean_text(record.get("title") if isinstance(record.get("title"), str) else None)
    authors = record.get("authors")
    author_names: list[str] = []
    if isinstance(authors, list):
        for a in authors:
            if not isinstance(a, dict):
                continue
            name = a.get("name")
            if isinstance(name, str) and name.strip():
                author_names.append(name.strip())
    pubdate = record.get("pubdate") if isinstance(record.get("pubdate"), str) else None
    year = _parse_year(pubdate)
    journal = record.get("fulljournalname") if isinstance(record.get("fulljournalname"), str) else None
    if not (journal or "").strip():
        journal = record.get("source") if isinstance(record.get("source"), str) else None
    doi = _doi_from_articleids(record.get("articleids"))
    pmcid = _pmcid_from_articleids(record.get("articleids"))
    return {
        "id": pmid,
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "title": title,
        "publication_year": year,
        "journal": _clean_text(journal),
        "first_author": _first_author_family(authors),
        "authors": author_names,
        "pubdate": _clean_text(pubdate),
        "source": _clean_text(record.get("source") if isinstance(record.get("source"), str) else None),
        "pubstatus": _clean_text(record.get("pubstatus") if isinstance(record.get("pubstatus"), str) else None),
        "articleids": record.get("articleids") if isinstance(record.get("articleids"), list) else None,
    }


def _extract_abstract_from_pubmed_xml(xml_text: str) -> str | None:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return None

    parts: list[str] = []
    for node in root.findall(".//AbstractText"):
        text = " ".join(" ".join(node.itertext()).split())
        if not text:
            continue
        label = None
        try:
            label = node.attrib.get("Label") or node.attrib.get("label")
        except Exception:
            label = None
        if isinstance(label, str) and label.strip():
            parts.append(f"{label.strip()}: {text}")
        else:
            parts.append(text)

    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    return "\n".join(parts)


@dataclass
class PubMedClient:
    tool: str = "miscite"
    email: str = ""
    api_key: str = ""
    user_agent: str = "miscite/0.1"
    timeout_seconds: float = 20.0
    cache: Cache | None = None
    _session_local: threading.local = field(default_factory=threading.local, init=False, repr=False)

    def _client(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        return session

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent}

    def _ttl_seconds(self, suggested_days: int) -> float:
        cache = self.cache
        if not cache:
            return 0.0
        days = min(int(suggested_days), int(cache.settings.cache_http_ttl_days))
        return float(max(0, days)) * 86400.0

    def _base_params(self, *, retmode: str = "json") -> dict[str, str]:
        params: dict[str, str] = {"db": "pubmed", "retmode": retmode}
        tool = (self.tool or "").strip()
        if tool:
            params["tool"] = tool
        email = (self.email or "").strip()
        if email:
            params["email"] = email
        api_key = (self.api_key or "").strip()
        if api_key:
            params["api_key"] = api_key
        return params

    def _get_json(self, url: str, *, params: dict[str, str]) -> dict | None:
        for attempt in range(3):
            try:
                resp = self._client().get(url, headers=self._headers(), params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
                return data if isinstance(data, dict) else None
            except requests.RequestException:
                backoff_sleep(attempt)
        return None

    def get_summary_by_pmid(self, pmid: str) -> dict | None:
        pmid = (pmid or "").strip()
        if not pmid:
            return None
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("pubmed.summary_by_pmid", [pmid])
            if hit:
                return cached

        params = self._base_params()
        params["id"] = pmid
        data = self._get_json(_ESUMMARY_URL, params=params)
        result = data.get("result") if isinstance(data, dict) else None
        rec = result.get(pmid) if isinstance(result, dict) else None
        if not isinstance(rec, dict):
            if cache and cache.settings.cache_enabled:
                cache.set_json("pubmed.summary_by_pmid", [pmid], None, ttl_seconds=self._ttl_seconds(1))
            return None

        summarized = _summarize_summary_record(rec)
        if cache and cache.settings.cache_enabled:
            cache.set_json("pubmed.summary_by_pmid", [pmid], summarized, ttl_seconds=self._ttl_seconds(90))
        return summarized

    def get_abstract_by_pmid(self, pmid: str) -> str | None:
        pmid = (pmid or "").strip()
        if not pmid:
            return None

        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("pubmed.abstract_by_pmid", [pmid])
            if hit:
                return cached if isinstance(cached, str) and cached.strip() else None

        params = self._base_params(retmode="xml")
        params["id"] = pmid
        params["rettype"] = "abstract"

        for attempt in range(3):
            try:
                resp = self._client().get(_EFETCH_URL, headers=self._headers(), params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                abstract = _extract_abstract_from_pubmed_xml(resp.text or "")
                if cache and cache.settings.cache_enabled:
                    cache.set_json(
                        "pubmed.abstract_by_pmid",
                        [pmid],
                        abstract,
                        ttl_seconds=self._ttl_seconds(90) if abstract else self._ttl_seconds(1),
                    )
                return abstract
            except requests.RequestException:
                backoff_sleep(attempt)
        return None

    def _summaries_by_pmids(self, pmids: list[str]) -> list[dict]:
        cache = self.cache
        if not pmids:
            return []

        wanted: list[str] = []
        out_by_pmid: dict[str, dict] = {}
        for pmid in pmids:
            pmid = (pmid or "").strip()
            if not pmid:
                continue
            if cache and cache.settings.cache_enabled:
                hit, cached = cache.get_json("pubmed.summary_by_pmid", [pmid])
                if hit:
                    if isinstance(cached, dict):
                        out_by_pmid[pmid] = cached
                    continue
            wanted.append(pmid)

        if wanted:
            params = self._base_params()
            params["id"] = ",".join(wanted)
            data = self._get_json(_ESUMMARY_URL, params=params)
            result = data.get("result") if isinstance(data, dict) else None
            if isinstance(result, dict):
                for pmid in wanted:
                    rec = result.get(pmid)
                    if not isinstance(rec, dict):
                        continue
                    summarized = _summarize_summary_record(rec)
                    out_by_pmid[pmid] = summarized
                    if cache and cache.settings.cache_enabled:
                        cache.set_json("pubmed.summary_by_pmid", [pmid], summarized, ttl_seconds=self._ttl_seconds(90))

        out: list[dict] = []
        for pmid in pmids:
            rec = out_by_pmid.get(pmid)
            if isinstance(rec, dict):
                out.append(rec)
        return out

    def search(self, term: str, *, rows: int = 5) -> list[dict]:
        q = (term or "").strip()
        if not q:
            return []
        rows = max(1, int(rows))

        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("pubmed.search", [q, str(rows)])
            if hit and isinstance(cached, list):
                return cached

        params = self._base_params()
        params["term"] = q
        params["retmax"] = str(rows)
        params["sort"] = "relevance"
        data = self._get_json(_ESEARCH_URL, params=params)
        esearch = data.get("esearchresult") if isinstance(data, dict) else None
        idlist = esearch.get("idlist") if isinstance(esearch, dict) else None
        pmids = [str(x).strip() for x in idlist if str(x).strip()] if isinstance(idlist, list) else []

        results = self._summaries_by_pmids(pmids)
        if cache and cache.settings.cache_enabled:
            cache.set_json("pubmed.search", [q, str(rows)], results, ttl_seconds=self._ttl_seconds(7))
        return results

    def get_work_by_doi(self, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("pubmed.work_by_doi", [doi_norm])
            if hit:
                return cached

        # Prefer a fielded DOI search, but fall back to plain-text search.
        for term in [f"{doi_norm}[DOI]", doi_norm]:
            results = self.search(term, rows=1)
            if results:
                work = results[0]
                if cache and cache.settings.cache_enabled:
                    cache.set_json("pubmed.work_by_doi", [doi_norm], work, ttl_seconds=self._ttl_seconds(90))
                return work

        if cache and cache.settings.cache_enabled:
            cache.set_json("pubmed.work_by_doi", [doi_norm], None, ttl_seconds=self._ttl_seconds(1))
        return None

    def get_work_by_pmcid(self, pmcid: str) -> dict | None:
        raw = (pmcid or "").strip()
        if not raw:
            return None
        m = re.search(r"\bPMC\d+\b", raw, flags=re.IGNORECASE)
        pmcid_norm = m.group(0).upper() if m else raw.upper()
        if not pmcid_norm.startswith("PMC"):
            if pmcid_norm.isdigit():
                pmcid_norm = f"PMC{pmcid_norm}"
            else:
                return None

        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("pubmed.work_by_pmcid", [pmcid_norm])
            if hit:
                return cached

        # PubMed supports searching by PMCID/PMC in the query syntax; try a few common tags.
        for term in [f"{pmcid_norm}[PMCID]", f"{pmcid_norm}[PMC]", pmcid_norm]:
            results = self.search(term, rows=1)
            if results:
                work = results[0]
                if cache and cache.settings.cache_enabled:
                    cache.set_json("pubmed.work_by_pmcid", [pmcid_norm], work, ttl_seconds=self._ttl_seconds(90))
                return work

        if cache and cache.settings.cache_enabled:
            cache.set_json("pubmed.work_by_pmcid", [pmcid_norm], None, ttl_seconds=self._ttl_seconds(1))
        return None

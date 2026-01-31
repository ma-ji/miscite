from __future__ import annotations

from dataclasses import dataclass, field
import xml.etree.ElementTree as ET
import threading

import requests

from server.miscite.cache import Cache
from server.miscite.analysis.normalize import normalize_doi
from server.miscite.sources.http import backoff_sleep

_ARXIV_API = "https://export.arxiv.org/api/query"
_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.replace("\n", " ").split())
    return cleaned if cleaned else None


def _extract_arxiv_id(id_url: str | None) -> str | None:
    if not id_url:
        return None
    parts = id_url.rstrip("/").split("/")
    if not parts:
        return None
    return parts[-1] or None


def _parse_feed(xml_text: str) -> list[dict]:
    entries: list[dict] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return entries

    ns = {"atom": _ATOM_NS, "arxiv": _ARXIV_NS}
    for entry in root.findall("atom:entry", ns):
        id_url = _clean_text(entry.findtext("atom:id", default="", namespaces=ns))
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        summary = _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
        published = _clean_text(entry.findtext("atom:published", default="", namespaces=ns))
        updated = _clean_text(entry.findtext("atom:updated", default="", namespaces=ns))
        doi = _clean_text(entry.findtext("arxiv:doi", default="", namespaces=ns))
        journal_ref = _clean_text(entry.findtext("arxiv:journal_ref", default="", namespaces=ns))
        comment = _clean_text(entry.findtext("arxiv:comment", default="", namespaces=ns))

        authors: list[str] = []
        for auth in entry.findall("atom:author", ns):
            name = _clean_text(auth.findtext("atom:name", default="", namespaces=ns))
            if name:
                authors.append(name)

        primary_category = entry.find("arxiv:primary_category", ns)
        category_term = None
        if primary_category is not None:
            category_term = primary_category.get("term") or None

        entries.append(
            {
                "id": _extract_arxiv_id(id_url),
                "id_url": id_url,
                "title": title,
                "summary": summary,
                "published": published,
                "updated": updated,
                "authors": authors,
                "doi": normalize_doi(doi or ""),
                "journal_ref": journal_ref,
                "comment": comment,
                "primary_category": category_term,
            }
        )
    return entries


@dataclass
class ArxivClient:
    timeout_seconds: float = 20.0
    user_agent: str = "miscite/0.1"
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

    def _ttl_seconds_for_params(self, params: dict[str, str]) -> float:
        if "id_list" in params:
            return self._ttl_seconds(90)
        q = (params.get("search_query") or "").strip().lower()
        if q.startswith("doi:"):
            return self._ttl_seconds(90)
        return self._ttl_seconds(7)

    def _query(self, params: dict[str, str]) -> list[dict]:
        cache = self.cache
        cache_parts = [f"{k}={params[k]}" for k in sorted(params.keys())]
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("arxiv.query", cache_parts)
            if hit and isinstance(cached, list):
                return cached
        for attempt in range(3):
            try:
                resp = self._client().get(_ARXIV_API, params=params, headers=self._headers(), timeout=self.timeout_seconds)
                resp.raise_for_status()
                entries = _parse_feed(resp.text)
                if cache and cache.settings.cache_enabled:
                    cache.set_json("arxiv.query", cache_parts, entries, ttl_seconds=self._ttl_seconds_for_params(params))
                return entries
            except requests.RequestException:
                backoff_sleep(attempt)
        return []

    def get_work_by_id(self, arxiv_id: str) -> dict | None:
        if not arxiv_id:
            return None
        arxiv_id = arxiv_id.strip()
        if not arxiv_id:
            return None
        entries = self._query({"id_list": arxiv_id})
        return entries[0] if entries else None

    def get_work_by_doi(self, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        entries = self._query({"search_query": f"doi:{doi_norm}", "start": "0", "max_results": "1"})
        return entries[0] if entries else None

    def search(self, query: str, *, rows: int = 5) -> list[dict]:
        q = (query or "").strip()
        if not q:
            return []
        params = {"search_query": q, "start": "0", "max_results": str(rows)}
        return self._query(params)

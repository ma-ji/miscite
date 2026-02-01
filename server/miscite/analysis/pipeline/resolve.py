from __future__ import annotations

import logging
import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from server.miscite.analysis.parse.citation_parsing import ReferenceEntry
from server.miscite.analysis.shared.normalize import content_tokens, normalize_doi
from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient, LlmOutputError
from server.miscite.prompts import render_prompt
from server.miscite.sources.arxiv import ArxivClient
from server.miscite.sources.crossref import CrossrefClient
from server.miscite.sources.openalex import OpenAlexClient

from server.miscite.analysis.pipeline.types import ResolvedWork

logger = logging.getLogger(__name__)


def _crossref_title(msg: dict | None) -> str | None:
    if not msg:
        return None
    title = msg.get("title")
    if isinstance(title, list) and title:
        return str(title[0])
    if isinstance(title, str):
        return title
    return None


def _crossref_year(msg: dict | None) -> int | None:
    if not msg:
        return None
    issued = msg.get("issued") or {}
    parts = (issued.get("date-parts") or [[None]])[0]
    try:
        year = int(parts[0])
        return year
    except Exception:
        return None


def _crossref_journal(msg: dict | None) -> str | None:
    if not msg:
        return None
    ctitle = msg.get("container-title")
    if isinstance(ctitle, list) and ctitle:
        return str(ctitle[0])
    if isinstance(ctitle, str):
        return ctitle
    return None


def _crossref_issn(msg: dict | None) -> str | None:
    if not msg:
        return None
    issn = msg.get("ISSN")
    if isinstance(issn, list) and issn:
        return str(issn[0])
    if isinstance(issn, str):
        return issn
    return None


def _crossref_doi(msg: dict | None) -> str | None:
    if not msg:
        return None
    return normalize_doi(str(msg.get("DOI") or ""))


def _crossref_first_author_family(msg: dict | None) -> str | None:
    if not msg:
        return None
    authors = msg.get("author")
    if not isinstance(authors, list) or not authors:
        return None
    first = authors[0]
    if not isinstance(first, dict):
        return None
    family = first.get("family")
    if isinstance(family, str) and family.strip():
        return family.strip().split()[-1].lower()
    literal = first.get("literal")
    if isinstance(literal, str) and literal.strip():
        return literal.strip().split()[-1].lower()
    return None


def _crossref_abstract(msg: dict | None) -> str | None:
    if not msg:
        return None
    abstract = msg.get("abstract")
    if not isinstance(abstract, str) or not abstract.strip():
        return None
    cleaned = re.sub(r"<[^>]+>", " ", abstract)
    cleaned = " ".join(cleaned.split())
    return cleaned if cleaned else None


def _crossref_retraction_detail(msg: dict | None) -> dict | None:
    if not msg:
        return None
    relation = msg.get("relation")
    update_to = msg.get("update-to")
    relation_hits: list[dict] = []
    if isinstance(relation, dict):
        for key, val in relation.items():
            if "retract" in str(key).lower():
                relation_hits.append({"relation_type": key, "items": val})
    update_hits: list[dict] = []
    if isinstance(update_to, list):
        for item in update_to:
            if not isinstance(item, dict):
                continue
            utype = str(item.get("type") or "").lower()
            if "retract" in utype:
                update_hits.append(item)
    if relation_hits or update_hits:
        return {"relation": relation_hits or None, "update_to": update_hits or None}
    return None


def _openalex_abstract(work: dict | None) -> str | None:
    if not work:
        return None
    inv = work.get("abstract_inverted_index")
    if not isinstance(inv, dict) or not inv:
        return None
    pos_to_word: dict[int, str] = {}
    max_pos = -1
    for word, positions in inv.items():
        if not isinstance(positions, list):
            continue
        for p in positions:
            if not isinstance(p, int):
                continue
            pos_to_word[p] = word
            max_pos = max(max_pos, p)
    if max_pos < 0:
        return None
    words = [pos_to_word.get(i, "") for i in range(max_pos + 1)]
    abstract = " ".join(w for w in words if w)
    return abstract.strip() or None


def _openalex_doi(work: dict | None) -> str | None:
    if not isinstance(work, dict):
        return None
    return normalize_doi(str(work.get("doi") or ""))


def _openalex_host_venue(work: dict | None) -> dict | None:
    if not isinstance(work, dict):
        return None
    hv = work.get("host_venue")
    return hv if isinstance(hv, dict) else None


def _openalex_journal(work: dict | None) -> str | None:
    hv = _openalex_host_venue(work)
    if not hv:
        return None
    name = hv.get("display_name")
    return str(name).strip() if isinstance(name, str) and name.strip() else None


def _openalex_publisher(work: dict | None) -> str | None:
    hv = _openalex_host_venue(work)
    if not hv:
        return None
    pub = hv.get("publisher")
    return str(pub).strip() if isinstance(pub, str) and pub.strip() else None


def _openalex_issn(work: dict | None) -> str | None:
    hv = _openalex_host_venue(work)
    if not hv:
        return None
    issn_l = hv.get("issn_l")
    if isinstance(issn_l, str) and issn_l.strip():
        return issn_l.strip()
    issn = hv.get("issn")
    if isinstance(issn, list) and issn:
        first = issn[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    return None


def _openalex_first_author_family(work: dict | None) -> str | None:
    if not isinstance(work, dict):
        return None
    authorships = work.get("authorships")
    if not isinstance(authorships, list) or not authorships:
        return None
    first = authorships[0]
    if not isinstance(first, dict):
        return None
    author = first.get("author")
    if isinstance(author, dict):
        dn = author.get("display_name")
        if isinstance(dn, str) and dn.strip():
            return dn.strip().split()[-1].lower()
    raw = first.get("raw_author_name")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().split()[-1].lower()
    return None


_ARXIV_URL_RE = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(?P<id>[A-Za-z0-9.\-_/]+)", re.IGNORECASE
)
_ARXIV_TAG_RE = re.compile(r"\barxiv\s*:?\s*(?P<id>[A-Za-z0-9.\-_/]+)", re.IGNORECASE)


def _clean_arxiv_id(raw: str | None) -> str | None:
    if not raw:
        return None
    cleaned = raw.strip()
    cleaned = cleaned.rstrip(").,;:]}")
    if cleaned.lower().endswith(".pdf"):
        cleaned = cleaned[:-4]
    return cleaned or None


def _extract_arxiv_id_from_text(text: str | None) -> str | None:
    if not text:
        return None
    m = _ARXIV_URL_RE.search(text)
    if m:
        return _clean_arxiv_id(m.group("id"))
    m = _ARXIV_TAG_RE.search(text)
    if m:
        return _clean_arxiv_id(m.group("id"))
    return None


def _arxiv_id(entry: dict | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    val = entry.get("id")
    return str(val).strip() if isinstance(val, str) and val.strip() else None


def _arxiv_title(entry: dict | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    val = entry.get("title")
    return str(val).strip() if isinstance(val, str) and val.strip() else None


def _arxiv_abstract(entry: dict | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    val = entry.get("summary")
    return str(val).strip() if isinstance(val, str) and val.strip() else None


def _arxiv_year(entry: dict | None) -> int | None:
    if not isinstance(entry, dict):
        return None
    published = entry.get("published")
    if isinstance(published, str) and len(published) >= 4:
        try:
            return int(published[:4])
        except Exception:
            return None
    return None


def _arxiv_first_author_family(entry: dict | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    authors = entry.get("authors")
    if not isinstance(authors, list) or not authors:
        return None
    first = authors[0]
    if isinstance(first, str) and first.strip():
        return first.strip().split()[-1].lower()
    return None


def _arxiv_doi(entry: dict | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    return normalize_doi(str(entry.get("doi") or ""))


def _arxiv_journal(entry: dict | None) -> str | None:
    if not isinstance(entry, dict):
        return None
    journal_ref = entry.get("journal_ref")
    if isinstance(journal_ref, str) and journal_ref.strip():
        return journal_ref.strip()
    return None


def _title_similarity(a: str, b: str) -> float:
    ta = content_tokens(a)
    tb = content_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / max(1, union)


def _summarize_openalex_work(work: dict) -> dict:
    authors: list[dict] = []
    for auth in work.get("authorships") or []:
        if not isinstance(auth, dict):
            continue
        author = auth.get("author")
        if isinstance(author, dict):
            authors.append(
                {
                    "id": author.get("id"),
                    "display_name": author.get("display_name"),
                    "orcid": author.get("orcid"),
                }
            )
    return {
        "id": work.get("id"),
        "doi": work.get("doi"),
        "display_name": work.get("display_name"),
        "title": work.get("title") or work.get("display_name"),
        "publication_year": work.get("publication_year"),
        "type": work.get("type"),
        "host_venue": work.get("host_venue"),
        "primary_location": work.get("primary_location"),
        "best_oa_location": work.get("best_oa_location"),
        "open_access": work.get("open_access"),
        "biblio": work.get("biblio"),
        "cited_by_count": work.get("cited_by_count"),
        "referenced_works_count": (
            len(work.get("referenced_works") or [])
            if isinstance(work.get("referenced_works"), list)
            else None
        ),
        "authorships": authors,
        "is_retracted": work.get("is_retracted"),
        "is_paratext": work.get("is_paratext"),
        "concepts": work.get("concepts"),
    }

def resolve_references(
    *,
    settings: Settings,
    references: list[ReferenceEntry],
    reference_records: dict[str, dict],
    openalex: OpenAlexClient,
    crossref: CrossrefClient,
    arxiv: ArxivClient,
    llm_match_client: OpenRouterClient,
    progress: Callable[[str, float], None] | None = None,
) -> tuple[dict[str, ResolvedWork], int]:
    resolution_cache: dict[str, ResolvedWork] = {}
    resolution_cache_lock = threading.Lock()
    match_llm_calls = 0
    match_llm_calls_lock = threading.Lock()

    def resolve_ref(ref: ReferenceEntry) -> ResolvedWork:
        nonlocal match_llm_calls

        csl = reference_records.get(ref.ref_id)
        csl_title = csl.get("title") if isinstance(csl, dict) else None
        title = (
            str(csl_title).strip()
            if isinstance(csl_title, str) and csl_title.strip()
            else None
        )
        first_author = ref.first_author
        year = ref.year

        doi_from_ref = normalize_doi(ref.doi or "") or normalize_doi(ref.raw or "")
        doi = doi_from_ref
        if doi:
            with resolution_cache_lock:
                cached = resolution_cache.get(doi)
            if cached is not None:
                return cached

        openalex_work: dict | None = None
        openalex_match: dict | None = None
        crossref_msg: dict | None = None
        crossref_match: dict | None = None
        arxiv_entry: dict | None = None
        arxiv_match: dict | None = None

        arxiv_id_from_ref = None
        if isinstance(csl, dict):
            arxiv_id_from_ref = _extract_arxiv_id_from_text(str(csl.get("URL") or ""))
            if not arxiv_id_from_ref:
                arxiv_id_from_ref = _extract_arxiv_id_from_text(
                    str(csl.get("id") or "")
                )
        arxiv_id_from_ref = arxiv_id_from_ref or _extract_arxiv_id_from_text(ref.raw)

        def _clip_query(text_in: str, max_len: int = 180) -> str:
            cleaned = " ".join(text_in.replace('"', "").split())
            return cleaned[:max_len] if len(cleaned) > max_len else cleaned

        def _choose_candidate_with_llm(
            source_label: str, candidates: list[dict]
        ) -> tuple[str | None, float, str]:
            nonlocal match_llm_calls
            candidates = [c for c in candidates if isinstance(c, dict) and c.get("id")]
            if not candidates:
                return None, 0.0, f"No {source_label} candidates with ids."
            with match_llm_calls_lock:
                if match_llm_calls >= settings.llm_match_max_calls:
                    raise RuntimeError(
                        "LLM match call limit exceeded; increase MISCITE_LLM_MATCH_MAX_CALLS."
                    )
                match_llm_calls += 1

            try:
                payload = llm_match_client.chat_json(
                    system=render_prompt(
                        "matching/candidate/system", source_label=source_label
                    ),
                    user=render_prompt(
                        "matching/candidate/user",
                        ref_raw=ref.raw,
                        title=title,
                        first_author=first_author,
                        year=year,
                        doi=doi,
                        candidates=candidates,
                    ),
                )
                best_id = payload.get("best_id")
                conf = payload.get("confidence")
                rationale = str(payload.get("rationale") or "").strip()

                if best_id is not None and not isinstance(best_id, str):
                    raise LlmOutputError("LLM best_id must be string or null.")
                try:
                    conf_f = float(conf)
                except Exception as e:
                    raise LlmOutputError("LLM match confidence must be a number 0..1.") from e
                if conf_f < 0.0 or conf_f > 1.0:
                    raise LlmOutputError("LLM match confidence out of range.")

                cand_ids = {str(c.get("id")) for c in candidates if c.get("id")}
                if best_id is not None and best_id not in cand_ids:
                    raise LlmOutputError("LLM returned an id not in candidate set.")
                return best_id, conf_f, rationale
            except LlmOutputError as e:
                logger.exception(
                    "LLM match disambiguation output invalid; skipping (ref_id=%s, source=%s).",
                    ref.ref_id,
                    source_label,
                )
                note = str(e).strip()
                if len(note) > 200:
                    note = note[:200] + "..."
                return None, 0.0, f"LLM disambiguation failed: {note}"

        def _openalex_search_query() -> str:
            base = title or ref.raw
            parts = [base]
            if first_author:
                parts.append(first_author)
            if year:
                parts.append(str(year))
            return " ".join(parts)

        def _openalex_candidate_score(candidate: dict) -> float:
            cand_title = str(
                candidate.get("display_name") or candidate.get("title") or ""
            ).strip()
            score = _title_similarity(title or ref.raw, cand_title)
            if first_author:
                cand_author = _openalex_first_author_family(candidate)
                if cand_author and cand_author == first_author:
                    score += 0.12
            if year:
                cy = candidate.get("publication_year")
                if isinstance(cy, int):
                    if cy == year:
                        score += 0.08
                    elif abs(cy - year) <= 1:
                        score += 0.04
            cdoi = _openalex_doi(candidate)
            if doi and cdoi and cdoi == doi:
                score += 0.2
            return min(1.0, score)

        def _match_openalex() -> tuple[dict | None, dict | None]:
            if doi:
                work = openalex.get_work_by_doi(doi)
                if work:
                    return work, {"method": "doi", "confidence": 1.0}

            candidates = openalex.search(_openalex_search_query(), rows=10)
            scored = [
                (_openalex_candidate_score(c), c)
                for c in candidates
                if isinstance(c, dict) and c.get("id")
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored:
                top_score, top = scored[0]
                if top_score >= 0.93:
                    work = openalex.get_work_by_id(str(top.get("id") or "")) or top
                    return work, {"method": "search", "confidence": float(top_score)}
                if top_score >= 0.65:
                    top_candidates = [c for _s, c in scored[:5]]
                    packed = []
                    for cand in top_candidates:
                        packed.append(
                            {
                                "id": cand.get("id"),
                                "doi": _openalex_doi(cand),
                                "title": cand.get("display_name") or cand.get("title"),
                                "publication_year": cand.get("publication_year"),
                                "first_author": _openalex_first_author_family(cand),
                                "venue": (
                                    (cand.get("host_venue") or {}).get("display_name")
                                    if isinstance(cand.get("host_venue"), dict)
                                    else None
                                ),
                            }
                        )
                    best_id, conf_f, rationale = _choose_candidate_with_llm(
                        "OpenAlex", packed
                    )
                    if best_id:
                        work = openalex.get_work_by_id(best_id)
                        return work, {
                            "method": "search_llm",
                            "confidence": conf_f,
                            "rationale": rationale,
                        }
                    return None, {
                        "method": "search_llm",
                        "confidence": conf_f,
                        "rationale": rationale,
                        "no_match": True,
                    }
            return None, None

        def _crossref_search_query() -> str:
            base = title or ref.raw
            parts = [base]
            if first_author:
                parts.append(first_author)
            if year:
                parts.append(str(year))
            return " ".join(parts)

        def _crossref_candidate_score(candidate: dict) -> float:
            cand_title = _crossref_title(candidate) or ""
            score = _title_similarity(title or ref.raw, cand_title)
            if first_author:
                cand_author = _crossref_first_author_family(candidate)
                if cand_author and cand_author == first_author:
                    score += 0.12
            if year:
                cy = _crossref_year(candidate)
                if isinstance(cy, int):
                    if cy == year:
                        score += 0.08
                    elif abs(cy - year) <= 1:
                        score += 0.04
            cdoi = _crossref_doi(candidate)
            if doi and cdoi and cdoi == doi:
                score += 0.2
            return min(1.0, score)

        def _match_crossref() -> tuple[dict | None, dict | None]:
            if doi:
                msg = crossref.get_work_by_doi(doi)
                if msg:
                    return msg, {"method": "doi", "confidence": 1.0}

            candidates = crossref.search(_crossref_search_query(), rows=10)
            scored = [
                (_crossref_candidate_score(c), c)
                for c in candidates
                if isinstance(c, dict) and _crossref_doi(c)
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored:
                top_score, top = scored[0]
                if top_score >= 0.93:
                    return top, {"method": "search", "confidence": float(top_score)}
                if top_score >= 0.65:
                    top_candidates = [c for _s, c in scored[:5]]
                    packed = []
                    for cand in top_candidates:
                        packed.append(
                            {
                                "id": _crossref_doi(cand),
                                "doi": _crossref_doi(cand),
                                "title": _crossref_title(cand),
                                "publication_year": _crossref_year(cand),
                                "first_author": _crossref_first_author_family(cand),
                                "venue": _crossref_journal(cand),
                                "publisher": cand.get("publisher"),
                            }
                        )
                    best_id, conf_f, rationale = _choose_candidate_with_llm(
                        "Crossref", packed
                    )
                    if best_id:
                        msg = crossref.get_work_by_doi(best_id) or next(
                            (c for c in candidates if _crossref_doi(c) == best_id), None
                        )
                        if msg:
                            return msg, {
                                "method": "search_llm",
                                "confidence": conf_f,
                                "rationale": rationale,
                            }
                    return None, {
                        "method": "search_llm",
                        "confidence": conf_f,
                        "rationale": rationale,
                        "no_match": True,
                    }
            return None, None

        def _arxiv_search_query() -> str:
            if title:
                base = f'ti:"{_clip_query(title)}"'
            else:
                base = f'all:"{_clip_query(ref.raw)}"'
            parts = [base]
            if first_author:
                parts.append(f'au:"{first_author}"')
            if year:
                parts.append(str(year))
            return " AND ".join(parts)

        def _arxiv_candidate_score(candidate: dict) -> float:
            cand_title = _arxiv_title(candidate) or ""
            score = _title_similarity(title or ref.raw, cand_title)
            if first_author:
                cand_author = _arxiv_first_author_family(candidate)
                if cand_author and cand_author == first_author:
                    score += 0.12
            if year:
                cy = _arxiv_year(candidate)
                if isinstance(cy, int):
                    if cy == year:
                        score += 0.08
                    elif abs(cy - year) <= 1:
                        score += 0.04
            cdoi = _arxiv_doi(candidate)
            if doi and cdoi and cdoi == doi:
                score += 0.2
            return min(1.0, score)

        def _match_arxiv() -> tuple[dict | None, dict | None]:
            if arxiv_id_from_ref:
                entry = arxiv.get_work_by_id(arxiv_id_from_ref)
                if entry:
                    return entry, {"method": "arxiv_id", "confidence": 1.0}
            if doi:
                entry = arxiv.get_work_by_doi(doi)
                if entry:
                    return entry, {"method": "doi", "confidence": 1.0}

            candidates = arxiv.search(_arxiv_search_query(), rows=10)
            scored = [
                (_arxiv_candidate_score(c), c)
                for c in candidates
                if isinstance(c, dict) and _arxiv_id(c)
            ]
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored:
                top_score, top = scored[0]
                if top_score >= 0.93:
                    return top, {"method": "search", "confidence": float(top_score)}
                if top_score >= 0.65:
                    top_candidates = [c for _s, c in scored[:5]]
                    packed = []
                    for cand in top_candidates:
                        packed.append(
                            {
                                "id": _arxiv_id(cand),
                                "doi": _arxiv_doi(cand),
                                "title": _arxiv_title(cand),
                                "publication_year": _arxiv_year(cand),
                                "first_author": _arxiv_first_author_family(cand),
                                "primary_category": cand.get("primary_category"),
                            }
                        )
                    best_id, conf_f, rationale = _choose_candidate_with_llm(
                        "arXiv", packed
                    )
                    if best_id:
                        entry = arxiv.get_work_by_id(best_id) or next(
                            (c for c in candidates if _arxiv_id(c) == best_id), None
                        )
                        if entry:
                            return entry, {
                                "method": "search_llm",
                                "confidence": conf_f,
                                "rationale": rationale,
                            }
                    return None, {
                        "method": "search_llm",
                        "confidence": conf_f,
                        "rationale": rationale,
                        "no_match": True,
                    }
            return None, None

        match_notes: list[str] = []

        openalex_work, openalex_match = _match_openalex()
        if openalex_work is None:
            crossref_msg, crossref_match = _match_crossref()
            if crossref_msg is None:
                arxiv_entry, arxiv_match = _match_arxiv()

        if openalex_work:
            matched_doi = _openalex_doi(openalex_work)
            if matched_doi:
                if doi_from_ref and doi_from_ref != matched_doi:
                    match_notes.append("Resolved DOI differs from reference DOI.")
                doi = matched_doi
        elif crossref_msg:
            matched_doi = _crossref_doi(crossref_msg)
            if matched_doi:
                if doi_from_ref and doi_from_ref != matched_doi:
                    match_notes.append("Resolved DOI differs from reference DOI.")
                doi = matched_doi
        elif arxiv_entry:
            matched_doi = _arxiv_doi(arxiv_entry)
            if matched_doi:
                if doi_from_ref and doi_from_ref != matched_doi:
                    match_notes.append("Resolved DOI differs from reference DOI.")
                doi = matched_doi

        source = None
        if openalex_work:
            source = "openalex"
        elif crossref_msg:
            source = "crossref"
        elif arxiv_entry:
            source = "arxiv"

        abstract = None
        if openalex_work:
            abstract = _openalex_abstract(openalex_work)
        elif arxiv_entry:
            abstract = _arxiv_abstract(arxiv_entry)
        elif crossref_msg:
            abstract = _crossref_abstract(crossref_msg)

        openalex_id = (
            str(openalex_work.get("id") or "")
            if isinstance(openalex_work, dict) and openalex_work.get("id")
            else None
        )
        arxiv_id = _arxiv_id(arxiv_entry)

        is_retracted = None
        retraction_detail = None
        if isinstance(openalex_work, dict):
            val = openalex_work.get("is_retracted")
            if isinstance(val, bool):
                is_retracted = val
                if val:
                    retraction_detail = {"openalex_id": openalex_id}
        elif crossref_msg:
            detail = _crossref_retraction_detail(crossref_msg)
            if detail:
                is_retracted = True
                retraction_detail = detail

        journal = None
        publisher = None
        issn = None
        resolved_year = year
        resolved_title = None
        if openalex_work:
            resolved_title = (
                str(
                    openalex_work.get("display_name")
                    or openalex_work.get("title")
                    or ""
                ).strip()
                or None
            )
            resolved_year = (
                openalex_work.get("publication_year")
                if isinstance(openalex_work.get("publication_year"), int)
                else year
            )
            journal = _openalex_journal(openalex_work)
            publisher = _openalex_publisher(openalex_work)
            issn = _openalex_issn(openalex_work)
        elif crossref_msg:
            resolved_title = _crossref_title(crossref_msg)
            resolved_year = _crossref_year(crossref_msg) or year
            journal = _crossref_journal(crossref_msg)
            publisher = (
                crossref_msg.get("publisher")
                if isinstance(crossref_msg.get("publisher"), str)
                else None
            )
            issn = _crossref_issn(crossref_msg)
        elif arxiv_entry:
            resolved_title = _arxiv_title(arxiv_entry)
            resolved_year = _arxiv_year(arxiv_entry) or year
            journal = _arxiv_journal(arxiv_entry)

        confidence = 0.0
        if source == "openalex" and openalex_match:
            confidence = float(openalex_match.get("confidence") or 0.0)
        elif source == "crossref" and crossref_match:
            confidence = float(crossref_match.get("confidence") or 0.0)
        elif source == "arxiv" and arxiv_match:
            confidence = float(arxiv_match.get("confidence") or 0.0)

        notes = ""
        if source == "openalex":
            if openalex_match and openalex_match.get("method") == "doi":
                notes = "Linked to OpenAlex by DOI."
            elif openalex_match and openalex_match.get("method") == "search_llm":
                notes = "Resolved via OpenAlex search (LLM disambiguation)."
            elif openalex_work:
                notes = "Resolved via OpenAlex search."
        elif source == "crossref":
            if crossref_match and crossref_match.get("method") == "doi":
                notes = "Linked to Crossref by DOI."
            elif crossref_match and crossref_match.get("method") == "search_llm":
                notes = "Resolved via Crossref search (LLM disambiguation)."
            elif crossref_msg:
                notes = "Resolved via Crossref search."
        elif source == "arxiv":
            if arxiv_match and arxiv_match.get("method") == "arxiv_id":
                notes = "Linked to arXiv by ID."
            elif arxiv_match and arxiv_match.get("method") == "doi":
                notes = "Linked to arXiv by DOI."
            elif arxiv_match and arxiv_match.get("method") == "search_llm":
                notes = "Resolved via arXiv search (LLM disambiguation)."
            elif arxiv_entry:
                notes = "Resolved via arXiv search."
        else:
            notes = "Unresolved in OpenAlex/Crossref/arXiv."

        if match_notes:
            notes = " ".join([notes] + match_notes).strip()

        resolved = ResolvedWork(
            doi=doi,
            title=resolved_title,
            abstract=abstract,
            year=resolved_year,
            journal=journal,
            publisher=publisher,
            issn=issn,
            is_retracted=is_retracted,
            retraction_detail=retraction_detail,
            openalex_id=openalex_id,
            openalex_record=(
                _summarize_openalex_work(openalex_work)
                if isinstance(openalex_work, dict)
                else None
            ),
            openalex_match=openalex_match,
            crossref_match=crossref_match,
            arxiv_id=arxiv_id,
            arxiv_record=arxiv_entry if isinstance(arxiv_entry, dict) else None,
            arxiv_match=arxiv_match,
            source=source,
            confidence=confidence,
            resolution_notes=notes,
        )
        if doi:
            with resolution_cache_lock:
                resolution_cache[doi] = resolved
        return resolved

    resolved_by_ref_id: dict[str, ResolvedWork] = {}
    total_refs = len(references)
    if progress:
        progress(f"Resolving {total_refs} references", 0.0)
    step = max(1, total_refs // 10) if total_refs else 1
    resolve_workers = max(1, int(settings.resolve_max_workers))
    if resolve_workers == 1 or total_refs <= 1:
        for idx, ref in enumerate(references, start=1):
            resolved_by_ref_id[ref.ref_id] = resolve_ref(ref)
            if total_refs and (idx == 1 or idx % step == 0 or idx == total_refs):
                if progress:
                    progress(f"Resolved {idx}/{total_refs} references", idx / total_refs)
    else:
        with ThreadPoolExecutor(max_workers=resolve_workers) as ex:
            futures = {ex.submit(resolve_ref, ref): ref for ref in references}
            completed = 0
            try:
                for fut in as_completed(futures):
                    ref = futures[fut]
                    resolved_by_ref_id[ref.ref_id] = fut.result()
                    completed += 1
                    if total_refs and (
                        completed == 1
                        or completed % step == 0
                        or completed == total_refs
                    ):
                        if progress:
                            progress(f"Resolved {completed}/{total_refs} references", completed / total_refs)
            except Exception:
                for fut in futures:
                    fut.cancel()
                raise

    return resolved_by_ref_id, match_llm_calls

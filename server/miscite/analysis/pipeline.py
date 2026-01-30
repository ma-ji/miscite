from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from server.miscite.analysis.citation_parsing import (
    CitationInstance,
    ReferenceEntry,
    split_references,
)
from server.miscite.analysis.deep_analysis import run_deep_analysis
from server.miscite.analysis.llm_parsing import (
    extract_references_section_with_llm,
    parse_citations_with_llm,
    parse_references_with_llm,
)
from server.miscite.analysis.local_nli import LocalNliModel
from server.miscite.analysis.methodology import build_methodology_md
from server.miscite.analysis.normalize import (
    content_tokens,
    normalize_author_year_key,
    normalize_author_year_locator,
    normalize_doi,
)
from server.miscite.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.sources.arxiv import ArxivClient
from server.miscite.sources.crossref import CrossrefClient
from server.miscite.sources.datasets import PredatoryVenueDataset, RetractionWatchDataset
from server.miscite.sources.openalex import OpenAlexClient
from server.miscite.sources.predatory_api import PredatoryApiClient
from server.miscite.sources.retraction_api import RetractionApiClient
from server.miscite.analysis.text_extract import extract_text


@dataclass(frozen=True)
class ResolvedWork:
    doi: str | None
    title: str | None
    abstract: str | None
    year: int | None
    journal: str | None
    publisher: str | None
    issn: str | None
    is_retracted: bool | None
    retraction_detail: dict | None
    openalex_id: str | None
    openalex_record: dict | None
    openalex_match: dict | None
    crossref_match: dict | None
    arxiv_id: str | None
    arxiv_record: dict | None
    arxiv_match: dict | None
    source: str | None
    confidence: float
    resolution_notes: str


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


_ARXIV_URL_RE = re.compile(r"arxiv\.org/(?:abs|pdf)/(?P<id>[A-Za-z0-9.\-_/]+)", re.IGNORECASE)
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
        "referenced_works_count": len(work.get("referenced_works") or []) if isinstance(work.get("referenced_works"), list) else None,
        "authorships": authors,
        "is_retracted": work.get("is_retracted"),
        "is_paratext": work.get("is_paratext"),
        "concepts": work.get("concepts"),
    }


def _token_overlap_score(a: str, b: str) -> float:
    ta = content_tokens(a)
    tb = content_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(1, len(ta))


ProgressCallback = Callable[[str, str | None, float | None], None]


def analyze_document(
    path: Path,
    *,
    settings: Settings,
    progress_cb: ProgressCallback | None = None,
) -> tuple[dict, list[dict], str]:
    started = time.time()
    used_sources: list[dict] = []
    limitations: list[str] = []

    last_progress = -1.0
    last_stage = ""

    def _progress(stage: str, message: str | None = None, progress: float | None = None, *, force: bool = False) -> None:
        nonlocal last_progress, last_stage
        if not progress_cb:
            return
        if progress is not None:
            progress = max(0.0, min(1.0, float(progress)))
            if not force and progress <= last_progress and stage == last_stage:
                return
            if not force and progress - last_progress < 0.01 and stage == last_stage:
                return
            last_progress = progress
        last_stage = stage
        progress_cb(stage, message, progress)

    parser_backend_used = "docling"
    _progress("extract", f"Extracting text from {path.name}", 0.03)
    text = extract_text(path)
    _progress("extract", "Text extracted", 0.08)
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for LLM-based citation/bibliography parsing.")

    llm_parse_client = OpenRouterClient(api_key=settings.openrouter_api_key, model=settings.llm_parse_model)
    llm_match_client = OpenRouterClient(api_key=settings.openrouter_api_key, model=settings.llm_match_model)
    llm_parsing_used = True
    llm_bib_used = True
    llm_citation_used = True
    parse_notes: dict[str, list[str]] = {"references": [], "citations": []}

    _progress("parse", "Locating references section", 0.12)
    main_text, refs_text = split_references(text)
    if not refs_text:
        refs_text, notes = extract_references_section_with_llm(
            llm_parse_client, text, max_chars=settings.llm_bib_parse_max_chars
        )
        parse_notes["references"].extend(notes)
        if refs_text and refs_text in text:
            main_text = text.split(refs_text, 1)[0].strip()
        if not refs_text:
            raise RuntimeError("LLM could not extract a References/Bibliography section; cannot parse bibliography.")

    used_sources.append(
        {
            "name": "OpenRouter (LLM parsing)",
            "detail": (
                f"LLM-assisted parsing of citations/bibliography via {settings.llm_parse_model}; "
                "strict JSON output enforced."
            ),
        }
    )
    used_sources.append(
        {
            "name": "OpenRouter (LLM matching)",
            "detail": f"LLM-assisted match disambiguation (OpenAlex/Crossref/arXiv) via {settings.llm_match_model}.",
        }
    )

    reference_records: dict[str, dict] = {}
    _progress("parse", "Parsing bibliography entries", 0.18)
    references, reference_records, notes = parse_references_with_llm(
        llm_parse_client,
        refs_text,
        max_chars=settings.llm_bib_parse_max_chars,
        max_refs=settings.llm_bib_parse_max_refs,
    )
    parse_notes["references"].extend(notes)
    if not references:
        raise RuntimeError("LLM did not return any bibliography entries.")
    _progress("parse", f"Parsed {len(references)} bibliography entries", 0.28)

    _progress("parse", "Parsing in-text citations", 0.32)
    citations, notes = parse_citations_with_llm(
        llm_parse_client,
        main_text,
        max_chars_full=settings.llm_citation_parse_max_chars,
        max_lines=settings.llm_citation_parse_max_lines,
        max_chars_candidates=settings.llm_citation_parse_max_candidate_chars,
    )
    parse_notes["citations"].extend(notes)
    _progress("parse", f"Parsed {len(citations)} in-text citations", 0.38)

    numeric_map: dict[str, ReferenceEntry] = {}
    author_year_map: dict[str, list[ReferenceEntry]] = {}
    for ref in references:
        if ref.ref_number is not None:
            numeric_map[str(ref.ref_number)] = ref
        if ref.first_author and ref.year:
            raw_key = f"{ref.first_author}-{ref.year}"
            norm_key = normalize_author_year_key(ref.first_author, ref.year)
            if norm_key:
                author_year_map.setdefault(norm_key, []).append(ref)
            if raw_key and raw_key != norm_key:
                author_year_map.setdefault(raw_key, []).append(ref)

    citation_to_ref: list[tuple[CitationInstance, ReferenceEntry | None]] = []
    for cit in citations:
        ref: ReferenceEntry | None = None
        if cit.kind == "numeric":
            ref = numeric_map.get(cit.locator)
        else:
            key = normalize_author_year_locator(cit.locator) or cit.locator
            candidates = author_year_map.get(key) or author_year_map.get(cit.locator) or []
            if len(candidates) == 1:
                ref = candidates[0]
            elif len(candidates) > 1:
                ref = candidates[0]
        citation_to_ref.append((cit, ref))

    crossref = CrossrefClient(
        user_agent=settings.crossref_user_agent,
        mailto=settings.crossref_mailto,
        timeout_seconds=settings.api_timeout_seconds,
    )
    openalex = OpenAlexClient(timeout_seconds=settings.api_timeout_seconds)
    arxiv = ArxivClient(timeout_seconds=settings.api_timeout_seconds, user_agent=settings.crossref_user_agent)
    rw = RetractionWatchDataset(settings.retractionwatch_csv)
    pred = PredatoryVenueDataset(settings.predatory_csv)

    if settings.crossref_mailto or settings.crossref_user_agent:
        used_sources.append({"name": "Crossref REST API", "detail": "Resolve DOI and bibliographic metadata."})
    used_sources.append(
        {
            "name": "OpenAlex API",
            "detail": "Resolve references to OpenAlex works (DOI first; otherwise search by title/author/year) and fetch abstracts + retraction flag.",
        }
    )
    used_sources.append(
        {
            "name": "arXiv API",
            "detail": "Resolve references to arXiv records (DOI/ID when available; otherwise search by title/author/year) and fetch abstracts.",
        }
    )
    if not settings.retractionwatch_csv.exists():
        raise RuntimeError(f"Retraction Watch dataset file not found: {settings.retractionwatch_csv}")
    used_sources.append({"name": "Retraction Watch dataset (local)", "detail": str(settings.retractionwatch_csv)})

    if settings.predatory_csv.exists():
        used_sources.append({"name": "Predatory venue dataset (local)", "detail": str(settings.predatory_csv)})
    if not (settings.predatory_api_enabled or settings.predatory_csv.exists()):
        raise RuntimeError("No predatory venue source configured (enable API or set MISCITE_PREDATORY_CSV).")

    retraction_api = None
    if settings.retraction_api_enabled:
        if not settings.retraction_api_url:
            raise RuntimeError("Retraction API enabled but MISCITE_RETRACTION_API_URL is empty.")
        retraction_api = RetractionApiClient(
            url=settings.retraction_api_url,
            token=settings.retraction_api_token,
            mode=settings.retraction_api_mode,
            timeout_seconds=settings.api_timeout_seconds,
        )
        used_sources.append(
            {
                "name": "Retraction API (custom)",
                "detail": f"{settings.retraction_api_url} (mode={settings.retraction_api_mode})",
            }
        )

    predatory_api = None
    if settings.predatory_api_enabled:
        if not settings.predatory_api_url:
            raise RuntimeError("Predatory API enabled but MISCITE_PREDATORY_API_URL is empty.")
        predatory_api = PredatoryApiClient(
            url=settings.predatory_api_url,
            token=settings.predatory_api_token,
            mode=settings.predatory_api_mode,
            timeout_seconds=settings.api_timeout_seconds,
        )
        used_sources.append(
            {
                "name": "Predatory API (custom)",
                "detail": f"{settings.predatory_api_url} (mode={settings.predatory_api_mode})",
            }
        )

    if not settings.enable_llm_inappropriate:
        raise RuntimeError("MISCITE_ENABLE_LLM_INAPPROPRIATE must be true (no heuristic fallback).")
    llm_client = OpenRouterClient(api_key=settings.openrouter_api_key, model=settings.llm_model)
    llm_used = False
    used_sources.append({"name": "OpenRouter", "detail": f"LLM-assisted inappropriate-citation checks via {settings.llm_model}."})

    local_nli = None
    if settings.enable_local_nli:
        local_nli = LocalNliModel(settings.local_nli_model)
        used_sources.append({"name": "Local NLI model", "detail": settings.local_nli_model})

    resolution_cache: dict[str, ResolvedWork] = {}
    match_llm_calls = 0

    def resolve_ref(ref: ReferenceEntry) -> ResolvedWork:
        nonlocal match_llm_calls

        csl = reference_records.get(ref.ref_id)
        csl_title = csl.get("title") if isinstance(csl, dict) else None
        title = str(csl_title).strip() if isinstance(csl_title, str) and csl_title.strip() else None
        first_author = ref.first_author
        year = ref.year

        doi_from_ref = normalize_doi(ref.doi or "")
        doi = doi_from_ref
        if doi and doi in resolution_cache:
            return resolution_cache[doi]

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
                arxiv_id_from_ref = _extract_arxiv_id_from_text(str(csl.get("id") or ""))
        arxiv_id_from_ref = arxiv_id_from_ref or _extract_arxiv_id_from_text(ref.raw)

        def _clip_query(text_in: str, max_len: int = 180) -> str:
            cleaned = " ".join(text_in.replace('"', "").split())
            return cleaned[:max_len] if len(cleaned) > max_len else cleaned

        def _choose_candidate_with_llm(source_label: str, candidates: list[dict]) -> tuple[str | None, float, str]:
            nonlocal match_llm_calls
            candidates = [c for c in candidates if isinstance(c, dict) and c.get("id")]
            if not candidates:
                return None, 0.0, f"No {source_label} candidates with ids."
            if match_llm_calls >= settings.llm_match_max_calls:
                raise RuntimeError("LLM match call limit exceeded; increase MISCITE_LLM_MATCH_MAX_CALLS.")
            match_llm_calls += 1

            payload = llm_match_client.chat_json(
                system=(
                    f"You link bibliography references to {source_label} records. "
                    "Return ONLY JSON. Be conservative: if unsure, return null."
                ),
                user=(
                    "Pick the best matching record for this reference, or null.\n\n"
                    "Return JSON with keys:\n"
                    "- best_id: string|null (must be one of the candidate ids)\n"
                    "- confidence: number 0..1\n"
                    "- rationale: string\n\n"
                    f"REFERENCE_RAW:\n{ref.raw}\n\n"
                    f"REFERENCE_TITLE:\n{title}\n\n"
                    f"REFERENCE_FIRST_AUTHOR:\n{first_author}\n\n"
                    f"REFERENCE_YEAR:\n{year}\n\n"
                    f"REFERENCE_DOI:\n{doi}\n\n"
                    f"CANDIDATES:\n{candidates}\n"
                ),
            )
            best_id = payload.get("best_id")
            conf = payload.get("confidence")
            rationale = str(payload.get("rationale") or "").strip()

            if best_id is not None and not isinstance(best_id, str):
                raise RuntimeError("LLM best_id must be string or null.")
            try:
                conf_f = float(conf)
            except Exception as e:
                raise RuntimeError("LLM match confidence must be a number 0..1.") from e
            if conf_f < 0.0 or conf_f > 1.0:
                raise RuntimeError("LLM match confidence out of range.")

            cand_ids = {str(c.get("id")) for c in candidates if c.get("id")}
            if best_id is not None and best_id not in cand_ids:
                raise RuntimeError("LLM returned an id not in candidate set.")
            return best_id, conf_f, rationale

        def _openalex_search_query() -> str:
            base = title or ref.raw
            parts = [base]
            if first_author:
                parts.append(first_author)
            if year:
                parts.append(str(year))
            return " ".join(parts)

        def _openalex_candidate_score(candidate: dict) -> float:
            cand_title = str(candidate.get("display_name") or candidate.get("title") or "").strip()
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
            scored = [(_openalex_candidate_score(c), c) for c in candidates if isinstance(c, dict) and c.get("id")]
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
                                "venue": (cand.get("host_venue") or {}).get("display_name")
                                if isinstance(cand.get("host_venue"), dict)
                                else None,
                            }
                        )
                    best_id, conf_f, rationale = _choose_candidate_with_llm("OpenAlex", packed)
                    if best_id:
                        work = openalex.get_work_by_id(best_id)
                        return work, {"method": "search_llm", "confidence": conf_f, "rationale": rationale}
                    return None, {"method": "search_llm", "confidence": conf_f, "rationale": rationale, "no_match": True}
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
            scored = [(_crossref_candidate_score(c), c) for c in candidates if isinstance(c, dict) and _crossref_doi(c)]
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
                    best_id, conf_f, rationale = _choose_candidate_with_llm("Crossref", packed)
                    if best_id:
                        msg = crossref.get_work_by_doi(best_id) or next(
                            (c for c in candidates if _crossref_doi(c) == best_id), None
                        )
                        if msg:
                            return msg, {"method": "search_llm", "confidence": conf_f, "rationale": rationale}
                    return None, {"method": "search_llm", "confidence": conf_f, "rationale": rationale, "no_match": True}
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
            scored = [(_arxiv_candidate_score(c), c) for c in candidates if isinstance(c, dict) and _arxiv_id(c)]
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
                    best_id, conf_f, rationale = _choose_candidate_with_llm("arXiv", packed)
                    if best_id:
                        entry = arxiv.get_work_by_id(best_id) or next((c for c in candidates if _arxiv_id(c) == best_id), None)
                        if entry:
                            return entry, {"method": "search_llm", "confidence": conf_f, "rationale": rationale}
                    return None, {"method": "search_llm", "confidence": conf_f, "rationale": rationale, "no_match": True}
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

        openalex_id = str(openalex_work.get("id") or "") if isinstance(openalex_work, dict) and openalex_work.get("id") else None
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
            resolved_title = str(openalex_work.get("display_name") or openalex_work.get("title") or "").strip() or None
            resolved_year = openalex_work.get("publication_year") if isinstance(openalex_work.get("publication_year"), int) else year
            journal = _openalex_journal(openalex_work)
            publisher = _openalex_publisher(openalex_work)
            issn = _openalex_issn(openalex_work)
        elif crossref_msg:
            resolved_title = _crossref_title(crossref_msg)
            resolved_year = _crossref_year(crossref_msg) or year
            journal = _crossref_journal(crossref_msg)
            publisher = crossref_msg.get("publisher") if isinstance(crossref_msg.get("publisher"), str) else None
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
            openalex_record=_summarize_openalex_work(openalex_work) if isinstance(openalex_work, dict) else None,
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
            resolution_cache[doi] = resolved
        return resolved

    resolved_by_ref_id: dict[str, ResolvedWork] = {}
    total_refs = len(references)
    _progress("resolve", f"Resolving {total_refs} references", 0.42)
    step = max(1, total_refs // 10) if total_refs else 1
    for idx, ref in enumerate(references, start=1):
        resolved_by_ref_id[ref.ref_id] = resolve_ref(ref)
        if total_refs and (idx == 1 or idx % step == 0 or idx == total_refs):
            pct = 0.42 + 0.28 * (idx / total_refs)
            _progress("resolve", f"Resolved {idx}/{total_refs} references", pct)

    resolved_count = sum(1 for w in resolved_by_ref_id.values() if w.source)
    if resolved_count < len(references):
        limitations.append(
            f"Metadata resolution succeeded for {resolved_count}/{len(references)} references; "
            "unmatched references have limited metadata (no abstract / retraction fields)."
        )

    issues: list[dict] = []

    _progress("flags", "Checking missing bibliography references", 0.72)
    missing_bib = 0
    for cit, ref in citation_to_ref:
        if ref is None:
            missing_bib += 1
            issues.append(
                {
                    "type": "missing_bibliography_ref",
                    "title": f"In-text citation not found in bibliography: {cit.raw}",
                    "severity": "high",
                    "details": {"citation": cit.__dict__},
                }
            )

    _progress("flags", "Checking retractions and predatory venues", 0.75)
    unresolved_refs = 0
    retracted_refs = 0
    predatory_matches = 0
    total_refs_for_flags = len(references)
    step_flags = max(1, total_refs_for_flags // 10) if total_refs_for_flags else 1
    for idx, ref in enumerate(references, start=1):
        work = resolved_by_ref_id.get(ref.ref_id)
        if not work:
            continue

        if (not work.source) or work.confidence < 0.55:
            unresolved_refs += 1
            issues.append(
                {
                    "type": "unresolved_reference",
                    "title": f"Bibliography item could not be confidently resolved: {ref.ref_id}",
                    "severity": "medium",
                    "details": {"ref_id": ref.ref_id, "raw": ref.raw, "resolution": work.__dict__},
                }
            )

        retraction_hits: list[dict] = []
        if work.is_retracted is True:
            retraction_hits.append(
                {
                    "source": work.source or "metadata",
                    "detail": work.retraction_detail or {},
                }
            )
        if work.doi:
            if retraction_api:
                rec = retraction_api.lookup_by_doi(work.doi)
                if rec:
                    retraction_hits.append({"source": "retraction_api", "detail": rec})
            record = rw.get_by_doi(work.doi)
            if record:
                retraction_hits.append({"source": "retractionwatch_csv", "detail": record.__dict__})

        if retraction_hits:
            retracted_refs += 1
            strong_sources = {hit["source"] for hit in retraction_hits if hit["source"] in {"retractionwatch_csv", "retraction_api"}}
            db_sources = {hit["source"] for hit in retraction_hits if hit["source"] in {"openalex", "crossref", "arxiv"}}
            high_conf = bool(strong_sources) or len(db_sources) >= 2
            issues.append(
                {
                    "type": "retracted_article",
                    "title": f"Retracted work cited: {work.doi}",
                    "severity": "high",
                    "details": {
                        "ref_id": ref.ref_id,
                        "retraction": retraction_hits,
                        "resolution": work.__dict__,
                        "review_needed": not high_conf,
                    },
                }
            )

        predatory_hits: list[dict] = []
        if predatory_api:
            rec = predatory_api.lookup(journal=work.journal, publisher=work.publisher, issn=work.issn)
            if rec:
                predatory_hits.append({"source": "predatory_api", "detail": rec})

        if settings.predatory_csv.exists():
            match = pred.match(journal=work.journal, publisher=work.publisher, issn=work.issn)
            if match:
                predatory_hits.append({"source": "predatory_csv", "detail": match.as_dict()})

        if predatory_hits:
            predatory_matches += 1
            sources = {hit["source"] for hit in predatory_hits}
            csv_conf = 0.0
            for hit in predatory_hits:
                if hit["source"] == "predatory_csv":
                    detail = hit.get("detail") or {}
                    try:
                        csv_conf = max(csv_conf, float(detail.get("confidence") or 0.0))
                    except Exception:
                        pass
            high_conf = len(sources) >= 2 or csv_conf >= 0.8
            issues.append(
                {
                    "type": "predatory_venue_match",
                    "title": f"Predatory venue match for {ref.ref_id}",
                    "severity": "high",
                    "details": {
                        "ref_id": ref.ref_id,
                        "match": predatory_hits,
                        "resolution": work.__dict__,
                        "review_needed": not high_conf,
                    },
                }
            )
        if total_refs_for_flags and (idx == 1 or idx % step_flags == 0 or idx == total_refs_for_flags):
            pct = 0.75 + 0.1 * (idx / total_refs_for_flags)
            _progress("flags", f"Checked {idx}/{total_refs_for_flags} references", pct)

    _progress("nli", "Checking citation-context alignment", 0.86)
    potentially_inappropriate = 0
    llm_max_calls = settings.llm_max_calls
    llm_calls = 0

    total_citations = len(citation_to_ref)
    step_citations = max(1, total_citations // 10) if total_citations else 1
    for idx, (cit, ref) in enumerate(citation_to_ref, start=1):
        if ref is None:
            continue
        work = resolved_by_ref_id.get(ref.ref_id)
        if not work or not work.title:
            continue

        evidence_text = (work.title or "") + "\n" + (work.abstract or "")
        score = _token_overlap_score(cit.context, evidence_text)
        if score >= 0.06:
            continue

        potentially_inappropriate += 1

        if local_nli and work.abstract:
            verdict = local_nli.classify(premise=work.abstract, hypothesis=cit.context)
            if verdict.label == "entailment" and verdict.confidence >= 0.85:
                # Evidence suggests the citation is plausible even if token overlap is low.
                continue
            if verdict.label == "contradiction" and verdict.confidence >= 0.85:
                issues.append(
                    {
                        "type": "potentially_inappropriate",
                        "title": f"NLI contradiction against abstract ({verdict.confidence:.2f})",
                        "severity": "high",
                        "details": {
                            "citation": cit.__dict__,
                            "ref_id": ref.ref_id,
                            "resolution": work.__dict__,
                            "nli": verdict.__dict__,
                        },
                    }
                )
                continue

        if llm_calls >= llm_max_calls:
            raise RuntimeError("LLM call limit exceeded; increase MISCITE_LLM_MAX_CALLS.")
        llm_calls += 1
        llm_used = True

        verdict = llm_client.chat_json(
            system=(
                "You are an academic citation checker. "
                "You must be conservative: if metadata is insufficient, respond 'uncertain'. "
                "Return ONLY valid JSON."
            ),
            user=_build_inappropriate_prompt(cit, ref, work),
        )

        label = str(verdict.get("label") or "").strip().lower()
        if label not in {"appropriate", "inappropriate", "uncertain"}:
            raise RuntimeError(f"Invalid LLM label: {label!r}")
        try:
            conf_f = float(verdict.get("confidence"))
        except Exception as e:
            raise RuntimeError("Invalid LLM confidence (expected number 0..1).") from e

        if label == "inappropriate" and conf_f >= 0.6:
            issues.append(
                {
                    "type": "potentially_inappropriate",
                    "title": f"LLM flagged inappropriate citation ({conf_f:.2f})",
                    "severity": "medium",
                    "details": {
                        "citation": cit.__dict__,
                        "ref_id": ref.ref_id,
                        "resolution": work.__dict__,
                        "llm": verdict,
                    },
                }
            )
        elif label == "uncertain":
            issues.append(
                {
                    "type": "needs_manual_review",
                    "title": "LLM could not verify citation from metadata",
                    "severity": "low",
                    "details": {
                        "citation": cit.__dict__,
                        "ref_id": ref.ref_id,
                        "resolution": work.__dict__,
                        "llm": verdict,
                    },
                }
            )
        if total_citations and (idx == 1 or idx % step_citations == 0 or idx == total_citations):
            pct = 0.86 + 0.1 * (idx / total_citations)
            _progress("nli", f"Checked {idx}/{total_citations} citations", pct)

    summary = {
        "total_citations": len(citations),
        "missing_bibliography_refs": missing_bib,
        "unresolved_references": unresolved_refs,
        "retracted_references": retracted_refs,
        "predatory_matches": predatory_matches,
        "potentially_inappropriate": potentially_inappropriate,
    }

    deep_analysis_report: dict | None = None
    try:
        deep_budget = max(0, llm_max_calls - llm_calls)
        deep_result = run_deep_analysis(
            settings=settings,
            llm_client=llm_client,
            openalex=openalex,
            references=references,
            resolved_by_ref_id=resolved_by_ref_id,
            citation_to_ref=citation_to_ref,
            paper_excerpt=main_text,
            progress=(lambda msg, frac: _progress("deep", msg, 0.96 + 0.015 * frac)),
            llm_budget=deep_budget,
        )
        used_sources.extend(deep_result.used_sources)
        limitations.extend(deep_result.limitations)
        deep_analysis_report = deep_result.report
    except Exception as e:
        deep_analysis_report = {"status": "failed", "reason": str(e)}

    report = {
        "summary": summary,
        "issues": issues,
        "deep_analysis": deep_analysis_report,
        "references": [
            {
                "ref_id": ref.ref_id,
                "raw": ref.raw,
                "parsed": ref.__dict__,
                "standard_record": reference_records.get(ref.ref_id),
                "resolution": resolved_by_ref_id.get(ref.ref_id).__dict__ if resolved_by_ref_id.get(ref.ref_id) else None,
            }
            for ref in references
        ],
        "data_sources": used_sources,
        "parsing": {
            "parser_backend": parser_backend_used,
            "llm_parsing_used": llm_parsing_used,
            "llm_bib_used": llm_bib_used,
            "llm_citation_used": llm_citation_used,
            "notes": parse_notes,
        },
        "timing": {"seconds": round(time.time() - started, 3)},
    }

    methodology_md = build_methodology_md(
        settings,
        used_sources=used_sources,
        llm_used=llm_used,
        limitations=limitations,
    )
    _progress("finalize", "Report assembled", 0.98, force=True)
    return report, used_sources, methodology_md


def _build_inappropriate_prompt(cit: CitationInstance, ref: ReferenceEntry, work: ResolvedWork) -> str:
    abstract = (work.abstract or "").strip()
    if len(abstract) > 1500:
        abstract = abstract[:1500] + "…"
    return (
        "Assess whether the citation is appropriate, given only metadata.\n\n"
        "Return JSON with keys:\n"
        "- label: one of [\"appropriate\",\"inappropriate\",\"uncertain\"]\n"
        "- confidence: number 0..1\n"
        "- rationale: string\n"
        "- evidence: array of short strings (quote or paraphrase from metadata)\n\n"
        f"CITING SENTENCE:\n{cit.context}\n\n"
        f"REFERENCE ENTRY (raw):\n{ref.raw}\n\n"
        f"RESOLVED DOI: {work.doi}\n"
        f"TITLE: {work.title}\n"
        f"YEAR: {work.year}\n"
        f"JOURNAL: {work.journal}\n"
        f"ABSTRACT:\n{abstract}\n"
    )

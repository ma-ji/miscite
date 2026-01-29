from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from server.miscite.analysis.citation_parsing import (
    CitationInstance,
    ReferenceEntry,
    split_references,
)
from server.miscite.analysis.llm_parsing import (
    extract_references_section_with_llm,
    parse_citations_with_llm,
    parse_references_with_llm,
)
from server.miscite.analysis.local_nli import LocalNliModel
from server.miscite.analysis.methodology import build_methodology_md
from server.miscite.analysis.normalize import content_tokens, normalize_doi
from server.miscite.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
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
    openalex_id: str | None
    openalex_record: dict | None
    openalex_match: dict | None
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
        "open_access": work.get("open_access"),
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


def analyze_document(path: Path, *, settings: Settings) -> tuple[dict, list[dict], str]:
    started = time.time()
    used_sources: list[dict] = []
    limitations: list[str] = []

    parser_backend_used = "docling"
    text = extract_text(path)
    if not settings.openrouter_api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required for LLM-based citation/bibliography parsing.")

    llm_parse_client = OpenRouterClient(api_key=settings.openrouter_api_key, model=settings.llm_parse_model)
    llm_match_client = OpenRouterClient(api_key=settings.openrouter_api_key, model=settings.llm_match_model)
    llm_parsing_used = True
    llm_bib_used = True
    llm_citation_used = True
    parse_notes: dict[str, list[str]] = {"references": [], "citations": []}

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
            "detail": f"LLM-assisted OpenAlex match disambiguation via {settings.llm_match_model}.",
        }
    )

    reference_records: dict[str, dict] = {}
    references, reference_records, notes = parse_references_with_llm(
        llm_parse_client,
        refs_text,
        max_chars=settings.llm_bib_parse_max_chars,
        max_refs=settings.llm_bib_parse_max_refs,
    )
    parse_notes["references"].extend(notes)
    if not references:
        raise RuntimeError("LLM did not return any bibliography entries.")

    citations, notes = parse_citations_with_llm(
        llm_parse_client,
        main_text,
        max_chars_full=settings.llm_citation_parse_max_chars,
        max_lines=settings.llm_citation_parse_max_lines,
        max_chars_candidates=settings.llm_citation_parse_max_candidate_chars,
    )
    parse_notes["citations"].extend(notes)

    numeric_map: dict[str, ReferenceEntry] = {}
    author_year_map: dict[str, list[ReferenceEntry]] = {}
    for ref in references:
        if ref.ref_number is not None:
            numeric_map[str(ref.ref_number)] = ref
        if ref.first_author and ref.year:
            key = f"{ref.first_author}-{ref.year}"
            author_year_map.setdefault(key, []).append(ref)

    citation_to_ref: list[tuple[CitationInstance, ReferenceEntry | None]] = []
    for cit in citations:
        ref: ReferenceEntry | None = None
        if cit.kind == "numeric":
            ref = numeric_map.get(cit.locator)
        else:
            candidates = author_year_map.get(cit.locator) or []
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

        def _openalex_search_query() -> str:
            base = title or ref.raw
            parts = [base]
            if first_author:
                parts.append(first_author)
            if year:
                parts.append(str(year))
            return " ".join(parts)

        def _candidate_score(candidate: dict) -> float:
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

        def _choose_openalex_candidate_with_llm(candidates: list[dict]) -> tuple[str | None, float, str]:
            nonlocal match_llm_calls
            candidates = [c for c in candidates if isinstance(c, dict) and c.get("id")]
            if not candidates:
                return None, 0.0, "No OpenAlex candidates with ids."
            if match_llm_calls >= settings.llm_match_max_calls:
                raise RuntimeError("LLM match call limit exceeded; increase MISCITE_LLM_MATCH_MAX_CALLS.")
            match_llm_calls += 1

            packed: list[dict] = []
            for cand in candidates:
                packed.append(
                    {
                        "id": cand.get("id"),
                        "doi": _openalex_doi(cand),
                        "title": cand.get("display_name") or cand.get("title"),
                        "publication_year": cand.get("publication_year"),
                        "first_author": _openalex_first_author_family(cand),
                        "host_venue": (cand.get("host_venue") or {}).get("display_name") if isinstance(cand.get("host_venue"), dict) else None,
                    }
                )

            payload = llm_match_client.chat_json(
                system=(
                    "You link bibliography references to OpenAlex works. "
                    "Return ONLY JSON. Be conservative: if unsure, return null."
                ),
                user=(
                    "Pick the best matching OpenAlex work for this reference, or null.\n\n"
                    "Return JSON with keys:\n"
                    "- best_openalex_id: string|null (must be one of the candidate ids)\n"
                    "- confidence: number 0..1\n"
                    "- rationale: string\n\n"
                    f"REFERENCE_RAW:\n{ref.raw}\n\n"
                    f"REFERENCE_TITLE:\n{title}\n\n"
                    f"REFERENCE_FIRST_AUTHOR:\n{first_author}\n\n"
                    f"REFERENCE_YEAR:\n{year}\n\n"
                    f"REFERENCE_DOI:\n{doi}\n\n"
                    f"CANDIDATES:\n{packed}\n"
                ),
            )
            best_id = payload.get("best_openalex_id")
            conf = payload.get("confidence")
            rationale = str(payload.get("rationale") or "").strip()

            if best_id is not None and not isinstance(best_id, str):
                raise RuntimeError("LLM best_openalex_id must be string or null.")
            try:
                conf_f = float(conf)
            except Exception as e:
                raise RuntimeError("LLM match confidence must be a number 0..1.") from e
            if conf_f < 0.0 or conf_f > 1.0:
                raise RuntimeError("LLM match confidence out of range.")

            cand_ids = {str(c.get("id")) for c in candidates if c.get("id")}
            if best_id is not None and best_id not in cand_ids:
                raise RuntimeError("LLM returned an OpenAlex id not in candidate set.")
            return best_id, conf_f, rationale

        if doi:
            openalex_work = openalex.get_work_by_doi(doi)
            if openalex_work:
                openalex_match = {"method": "doi", "confidence": 1.0}

        if openalex_work is None:
            candidates = openalex.search(_openalex_search_query(), rows=10)
            scored = [(_candidate_score(c), c) for c in candidates if isinstance(c, dict) and c.get("id")]
            scored.sort(key=lambda x: x[0], reverse=True)
            if scored:
                top_score, top = scored[0]
                if top_score >= 0.93:
                    openalex_work = openalex.get_work_by_id(str(top.get("id") or "")) or top
                    openalex_match = {"method": "search", "confidence": float(top_score)}
                elif top_score >= 0.65:
                    # Fussy results: use LLM to decide among top candidates.
                    top_candidates = [c for _s, c in scored[:5]]
                    best_id, conf_f, rationale = _choose_openalex_candidate_with_llm(top_candidates)
                    if best_id:
                        openalex_work = openalex.get_work_by_id(best_id)
                        openalex_match = {"method": "search_llm", "confidence": conf_f, "rationale": rationale}
                    else:
                        openalex_match = {"method": "search_llm", "confidence": conf_f, "rationale": rationale, "no_match": True}

        if openalex_work:
            openalex_doi = _openalex_doi(openalex_work)
            doi = doi or openalex_doi

        crossref_msg = crossref.get_work_by_doi(doi) if doi else None

        abstract = _openalex_abstract(openalex_work)
        openalex_id = str(openalex_work.get("id") or "") if isinstance(openalex_work, dict) and openalex_work.get("id") else None
        is_retracted = None
        if isinstance(openalex_work, dict):
            val = openalex_work.get("is_retracted")
            if isinstance(val, bool):
                is_retracted = val

        journal = _crossref_journal(crossref_msg) or _openalex_journal(openalex_work)
        publisher = (crossref_msg.get("publisher") if crossref_msg else None) or _openalex_publisher(openalex_work)
        issn = _crossref_issn(crossref_msg) or _openalex_issn(openalex_work)

        confidence = float((openalex_match or {}).get("confidence") or 0.0)
        if doi_from_ref and crossref_msg:
            confidence = 1.0

        if openalex_work and crossref_msg:
            source = "crossref+openalex"
        elif crossref_msg:
            source = "crossref"
        elif openalex_work:
            source = "openalex"
        else:
            source = None

        if openalex_match and openalex_match.get("method") == "doi":
            notes = "Linked to OpenAlex by DOI."
        elif openalex_work:
            notes = "Resolved via OpenAlex search."
        elif crossref_msg:
            notes = "DOI resolved in Crossref; OpenAlex record not found."
        else:
            notes = "Unresolved in OpenAlex/Crossref."

        resolved = ResolvedWork(
            doi=doi,
            title=_crossref_title(crossref_msg) or (str(openalex_work.get("display_name")) if isinstance(openalex_work, dict) else None),
            abstract=abstract,
            year=_crossref_year(crossref_msg) or year,
            journal=journal,
            publisher=publisher,
            issn=issn,
            is_retracted=is_retracted,
            openalex_id=openalex_id,
            openalex_record=_summarize_openalex_work(openalex_work) if isinstance(openalex_work, dict) else None,
            openalex_match=openalex_match,
            source=source,
            confidence=confidence,
            resolution_notes=notes,
        )
        if doi:
            resolution_cache[doi] = resolved
        return resolved

    resolved_by_ref_id: dict[str, ResolvedWork] = {}
    for ref in references:
        resolved_by_ref_id[ref.ref_id] = resolve_ref(ref)

    openalex_linked = sum(1 for w in resolved_by_ref_id.values() if w.openalex_id)
    if openalex_linked < len(references):
        limitations.append(
            f"OpenAlex linking succeeded for {openalex_linked}/{len(references)} references; "
            "unmatched references have limited metadata (no abstract / is_retracted)."
        )

    issues: list[dict] = []

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

    unresolved_refs = 0
    retracted_refs = 0
    predatory_matches = 0
    for ref in references:
        work = resolved_by_ref_id.get(ref.ref_id)
        if not work:
            continue

        if (not work.openalex_id and not work.doi) or work.confidence < 0.55:
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
        if work.doi:
            if work.is_retracted is True:
                retraction_hits.append({"source": "openalex", "detail": {"openalex_id": work.openalex_id}})
            if retraction_api:
                rec = retraction_api.lookup_by_doi(work.doi)
                if rec:
                    retraction_hits.append({"source": "retraction_api", "detail": rec})
            record = rw.get_by_doi(work.doi)
            if record:
                retraction_hits.append({"source": "retractionwatch_csv", "detail": record.__dict__})

        if retraction_hits:
            retracted_refs += 1
            issues.append(
                {
                    "type": "retracted_article",
                    "title": f"Retracted work cited: {work.doi}",
                    "severity": "high",
                    "details": {"ref_id": ref.ref_id, "retraction": retraction_hits, "resolution": work.__dict__},
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
                predatory_hits.append({"source": "predatory_csv", "detail": match.__dict__})

        if predatory_hits:
            predatory_matches += 1
            issues.append(
                {
                    "type": "predatory_venue_match",
                    "title": f"Predatory venue match for {ref.ref_id}",
                    "severity": "high",
                    "details": {"ref_id": ref.ref_id, "match": predatory_hits, "resolution": work.__dict__},
                }
            )

    potentially_inappropriate = 0
    llm_max_calls = settings.llm_max_calls
    llm_calls = 0

    for cit, ref in citation_to_ref:
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

    summary = {
        "total_citations": len(citations),
        "missing_bibliography_refs": missing_bib,
        "unresolved_references": unresolved_refs,
        "retracted_references": retracted_refs,
        "predatory_matches": predatory_matches,
        "potentially_inappropriate": potentially_inappropriate,
    }

    report = {
        "summary": summary,
        "issues": issues,
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

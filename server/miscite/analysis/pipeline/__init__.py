from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from server.miscite.core.cache import Cache
from server.miscite.analysis.parse.citation_parsing import (
    CitationInstance,
    ReferenceEntry,
    normalize_llm_citations,
    split_references,
)
from server.miscite.analysis.deep_analysis.deep_analysis import run_deep_analysis
from server.miscite.analysis.parse.llm_parsing import (
    extract_references_section_with_llm,
    parse_citations_with_llm,
    parse_references_with_llm,
)
from server.miscite.analysis.checks.local_nli import get_local_nli
from server.miscite.analysis.checks.reference_flags import (
    check_missing_bibliography_refs,
    check_retractions_and_predatory_venues,
)
from server.miscite.analysis.checks.inappropriate import check_inappropriate_citations
from server.miscite.analysis.pipeline.resolve import resolve_references
from server.miscite.analysis.report.methodology import build_methodology_md
from server.miscite.analysis.shared.normalize import (
    normalize_author_year_key,
    normalize_author_year_locator,
)
from server.miscite.analysis.extract.text_extract import extract_text
from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.sources.arxiv import ArxivClient
from server.miscite.sources.crossref import CrossrefClient
from server.miscite.sources.openalex import OpenAlexClient
from server.miscite.sources.predatory_api import PredatoryApiClient
from server.miscite.sources.predatory.data import load_predatory_data
from server.miscite.sources.predatory.match import PredatoryMatcher
from server.miscite.sources.retraction_api import RetractionApiClient
from server.miscite.sources.retraction.data import load_retraction_data
from server.miscite.sources.retraction.match import RetractionMatcher


ProgressCallback = Callable[[str, str | None, float | None], None]


def analyze_document(
    path: Path,
    *,
    settings: Settings,
    document_sha256: str | None = None,
    progress_cb: ProgressCallback | None = None,
) -> tuple[dict, list[dict], str]:
    started = time.time()
    used_sources: list[dict] = []
    limitations: list[str] = []

    last_progress = -1.0
    last_stage = ""

    def _progress(
        stage: str,
        message: str | None = None,
        progress: float | None = None,
        *,
        force: bool = False,
    ) -> None:
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

    cache = Cache(settings=settings)
    doc_scope = f"doc:{document_sha256}" if document_sha256 else f"path:{path.name}"
    doc_cache = cache.scoped(doc_scope)

    parser_backend_used = settings.text_extract_backend
    _progress("extract", f"Extracting text from {path.name}", 0.03)
    text: str | None = None
    text_cache_parts = [settings.text_extract_backend, str(path)]
    if settings.cache_text_ttl_days > 0:
        hit, cached_text = doc_cache.get_text_file(
            "text_extract", text_cache_parts, ttl_days=settings.cache_text_ttl_days
        )
        if hit:
            text = cached_text
            _progress("extract", "Using cached extracted text", 0.08)
    if text is None:
        text = extract_text(
            path,
            backend=settings.text_extract_backend,
            timeout_seconds=settings.text_extract_timeout_seconds,
            use_subprocess=settings.text_extract_subprocess,
            process_context=settings.text_extract_process_context,
        )
        if settings.cache_text_ttl_days > 0:
            doc_cache.set_text_file("text_extract", text_cache_parts, text)
        _progress("extract", "Text extracted", 0.08)
    if not settings.openrouter_api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is required for LLM-based citation/bibliography parsing."
        )

    llm_parse_client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        model=settings.llm_parse_model,
        cache=doc_cache,
    )
    llm_match_client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        model=settings.llm_match_model,
        cache=doc_cache,
    )
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
            parse_notes["references"].append(
                "No references section found; proceeding without bibliography entries."
            )

    llm_bib_used = bool((refs_text or "").strip())
    llm_citation_used = bool((main_text or "").strip())

    used_sources.append(
        {
            "name": "OpenRouter (LLM parsing)",
            "detail": (
                f"LLM-assisted parsing of citations/bibliography via {settings.llm_parse_model}; "
                "JSON output enforced with fallback on invalid output."
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
    _progress("parse", "Parsing in-text citations", None)
    fut_refs = None
    fut_cits = None
    try:
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_refs = ex.submit(
                parse_references_with_llm,
                llm_parse_client,
                refs_text,
                max_chars=settings.llm_bib_parse_max_chars,
                max_refs=settings.llm_bib_parse_max_refs,
            )
            fut_cits = ex.submit(
                parse_citations_with_llm,
                llm_parse_client,
                main_text,
                max_chars_full=settings.llm_citation_parse_max_chars,
                max_lines=settings.llm_citation_parse_max_lines,
                max_chars_candidates=settings.llm_citation_parse_max_candidate_chars,
            )
            references, reference_records, notes_refs = fut_refs.result()
            citations, notes_cits = fut_cits.result()
    except Exception:
        for fut in [fut_refs, fut_cits]:
            try:
                if fut is not None:
                    fut.cancel()
            except Exception:
                pass
        raise

    parse_notes["references"].extend(notes_refs)
    if not references:
        parse_notes["references"].append(
            "No bibliography entries parsed; proceeding without reference matching."
        )
    _progress("parse", f"Parsed {len(references)} bibliography entries", 0.28)

    parse_notes["citations"].extend(notes_cits)
    citations = normalize_llm_citations(citations)
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
            candidates = (
                author_year_map.get(key) or author_year_map.get(cit.locator) or []
            )
            if len(candidates) == 1:
                ref = candidates[0]
            elif len(candidates) > 1:
                ref = candidates[0]
        citation_to_ref.append((cit, ref))

    crossref = CrossrefClient(
        user_agent=settings.crossref_user_agent,
        mailto=settings.crossref_mailto,
        timeout_seconds=settings.api_timeout_seconds,
        cache=cache,
    )
    openalex = OpenAlexClient(timeout_seconds=settings.api_timeout_seconds, cache=cache)
    arxiv = ArxivClient(
        timeout_seconds=settings.api_timeout_seconds,
        user_agent=settings.crossref_user_agent,
        cache=cache,
    )
    retraction_data = load_retraction_data(settings.retractionwatch_csv)
    retraction_matcher = RetractionMatcher(retraction_data)
    predatory_data = load_predatory_data(settings.predatory_csv)
    predatory_matcher = PredatoryMatcher(predatory_data)

    if settings.crossref_mailto or settings.crossref_user_agent:
        used_sources.append(
            {
                "name": "Crossref REST API",
                "detail": "Resolve DOI and bibliographic metadata.",
            }
        )
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
        raise RuntimeError(
            f"Retraction Watch dataset file not found: {settings.retractionwatch_csv}"
        )
    used_sources.append(
        {
            "name": "Retraction Watch dataset (local)",
            "detail": str(settings.retractionwatch_csv),
        }
    )

    if settings.predatory_csv.exists():
        used_sources.append(
            {
                "name": "Predatory venue dataset (local)",
                "detail": str(settings.predatory_csv),
            }
        )
    if not (settings.predatory_api_enabled or settings.predatory_csv.exists()):
        raise RuntimeError(
            "No predatory venue source configured (enable API or set MISCITE_PREDATORY_CSV)."
        )

    retraction_api = None
    if settings.retraction_api_enabled:
        if not settings.retraction_api_url:
            raise RuntimeError(
                "Retraction API enabled but MISCITE_RETRACTION_API_URL is empty."
            )
        retraction_api = RetractionApiClient(
            url=settings.retraction_api_url,
            token=settings.retraction_api_token,
            mode=settings.retraction_api_mode,
            timeout_seconds=settings.api_timeout_seconds,
            cache=cache,
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
            raise RuntimeError(
                "Predatory API enabled but MISCITE_PREDATORY_API_URL is empty."
            )
        predatory_api = PredatoryApiClient(
            url=settings.predatory_api_url,
            token=settings.predatory_api_token,
            mode=settings.predatory_api_mode,
            timeout_seconds=settings.api_timeout_seconds,
            cache=cache,
        )
        used_sources.append(
            {
                "name": "Predatory API (custom)",
                "detail": f"{settings.predatory_api_url} (mode={settings.predatory_api_mode})",
            }
        )

    if not settings.enable_llm_inappropriate:
        raise RuntimeError(
            "MISCITE_ENABLE_LLM_INAPPROPRIATE must be true (no heuristic fallback)."
        )
    llm_client = OpenRouterClient(
        api_key=settings.openrouter_api_key, model=settings.llm_model, cache=doc_cache
    )
    llm_deep_client = OpenRouterClient(
        api_key=settings.openrouter_api_key,
        model=settings.llm_deep_analysis_model,
        cache=doc_cache,
    )
    llm_used = False
    used_sources.append(
        {
            "name": "OpenRouter",
            "detail": f"LLM-assisted inappropriate-citation checks via {settings.llm_model}.",
        }
    )

    local_nli = None
    if settings.enable_local_nli:
        local_nli = get_local_nli(
            settings.local_nli_model, accelerator=settings.accelerator
        )
        used_sources.append(
            {"name": "Local NLI model", "detail": settings.local_nli_model}
        )

    resolved_by_ref_id, _match_llm_calls_used = resolve_references(
        settings=settings,
        references=references,
        reference_records=reference_records,
        openalex=openalex,
        crossref=crossref,
        arxiv=arxiv,
        llm_match_client=llm_match_client,
        progress=(lambda msg, frac: _progress("resolve", msg, 0.42 + 0.28 * frac)),
    )
    resolved_count = sum(1 for w in resolved_by_ref_id.values() if w.source)
    if resolved_count < len(references):
        limitations.append(
            f"Metadata resolution succeeded for {resolved_count}/{len(references)} references; "
            "unmatched references have limited metadata (no abstract / retraction fields)."
        )

    issues: list[dict] = []

    new_issues, missing_bib = check_missing_bibliography_refs(
        citation_to_ref=citation_to_ref,
        progress=(lambda msg, frac: _progress("flags", msg, 0.72 + 0.03 * frac)),
    )
    issues.extend(new_issues)

    new_issues, unresolved_refs, retracted_refs, predatory_matches = check_retractions_and_predatory_venues(
        settings=settings,
        references=references,
        resolved_by_ref_id=resolved_by_ref_id,
        retraction_matcher=retraction_matcher,
        predatory_matcher=predatory_matcher,
        retraction_api=retraction_api,
        predatory_api=predatory_api,
        progress=(lambda msg, frac: _progress("flags", msg, 0.75 + 0.10 * frac)),
    )
    issues.extend(new_issues)

    llm_max_calls = int(settings.llm_max_calls)
    new_issues, potentially_inappropriate, llm_calls, used_llm = check_inappropriate_citations(
        settings=settings,
        llm_client=llm_client,
        local_nli=local_nli,
        citation_to_ref=citation_to_ref,
        resolved_by_ref_id=resolved_by_ref_id,
        progress=(lambda msg, frac: _progress("nli", msg, 0.86 + 0.10 * frac)),
    )
    if used_llm:
        llm_used = True
    issues.extend(new_issues)
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
            llm_client=llm_deep_client,
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
                "resolution": (
                    resolved_by_ref_id.get(ref.ref_id).__dict__
                    if resolved_by_ref_id.get(ref.ref_id)
                    else None
                ),
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

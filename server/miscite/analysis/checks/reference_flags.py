from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from server.miscite.analysis.match.types import CitationMatch
from server.miscite.analysis.parse.citation_parsing import ReferenceEntry
from server.miscite.analysis.pipeline.types import ResolvedWork
from server.miscite.core.config import Settings
from server.miscite.sources.predatory_api import PredatoryApiClient
from server.miscite.sources.predatory.match import PredatoryMatcher
from server.miscite.sources.retraction_api import RetractionApiClient
from server.miscite.sources.retraction.match import RetractionMatcher


def check_missing_bibliography_refs(
    *,
    citation_matches: list[CitationMatch],
    progress: Callable[[str, float], None] | None = None,
) -> tuple[list[dict], int, int]:
    if progress:
        progress("Checking missing bibliography references", 0.0)

    issues: list[dict] = []
    missing_bib = 0
    ambiguous_bib = 0
    for match in citation_matches:
        cit = match.citation
        ref = match.ref
        if match.status == "unmatched" or ref is None:
            missing_bib += 1
            issues.append(
                {
                    "type": "missing_bibliography_ref",
                    "title": f"In-text citation not found in bibliography: {cit.raw}",
                    "severity": "high",
                    "details": {
                        "citation": cit.__dict__,
                        "match": {
                            "status": match.status,
                            "confidence": match.confidence,
                            "method": match.method,
                            "notes": match.notes,
                            "candidates": [c.__dict__ for c in match.candidates],
                        },
                    },
                }
            )
            continue

        if match.status == "ambiguous":
            ambiguous_bib += 1
            issues.append(
                {
                    "type": "ambiguous_bibliography_ref",
                    "title": f"Ambiguous bibliography match for in-text citation: {cit.raw}",
                    "severity": "medium",
                    "details": {
                        "citation": cit.__dict__,
                        "match": {
                            "status": match.status,
                            "confidence": match.confidence,
                            "method": match.method,
                            "notes": match.notes,
                            "candidates": [c.__dict__ for c in match.candidates],
                        },
                    },
                }
            )

    if progress:
        progress("Checked missing bibliography references", 1.0)

    return issues, missing_bib, ambiguous_bib


def check_retractions_and_predatory_venues(
    *,
    settings: Settings,
    references: list[ReferenceEntry],
    resolved_by_ref_id: dict[str, ResolvedWork],
    retraction_matcher: RetractionMatcher,
    predatory_matcher: PredatoryMatcher,
    retraction_api: RetractionApiClient | None,
    predatory_api: PredatoryApiClient | None,
    progress: Callable[[str, float], None] | None = None,
) -> tuple[list[dict], int, int, int]:
    if progress:
        progress("Checking retractions and predatory venues", 0.0)

    issues: list[dict] = []
    unresolved_refs = 0
    retracted_refs = 0
    predatory_matches = 0

    total = len(references)
    step = max(1, total // 10) if total else 1

    pred_csv_enabled = settings.predatory_csv.exists()

    def _check_one(ref: ReferenceEntry) -> tuple[list[dict], int, int, int]:
        local_issues: list[dict] = []
        unresolved_local = 0
        retracted_local = 0
        predatory_local = 0

        work = resolved_by_ref_id.get(ref.ref_id)
        if not work:
            return local_issues, unresolved_local, retracted_local, predatory_local

        if (not work.source) or work.confidence < 0.55:
            unresolved_local += 1
            local_issues.append(
                {
                    "type": "unresolved_reference",
                    "title": f"Bibliography item could not be confidently resolved: {ref.ref_id}",
                    "severity": "medium",
                    "details": {
                        "ref_id": ref.ref_id,
                        "raw": ref.raw,
                        "resolution": work.__dict__,
                    },
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
            record = retraction_matcher.get_by_doi(work.doi)
            if record:
                retraction_hits.append({"source": "retractionwatch_csv", "detail": record.__dict__})

        if retraction_hits:
            retracted_local += 1
            strong_sources = {
                hit["source"]
                for hit in retraction_hits
                if hit["source"] in {"retractionwatch_csv", "retraction_api"}
            }
            db_sources = {
                hit["source"]
                for hit in retraction_hits
                if hit["source"] in {"openalex", "crossref", "pubmed", "arxiv"}
            }
            high_conf = bool(strong_sources) or len(db_sources) >= 2
            local_issues.append(
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

        if pred_csv_enabled:
            match = predatory_matcher.match(journal=work.journal, publisher=work.publisher, issn=work.issn)
            if match:
                predatory_hits.append({"source": "predatory_csv", "detail": match.as_dict()})

        if predatory_hits:
            predatory_local += 1
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
            local_issues.append(
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

        return local_issues, unresolved_local, retracted_local, predatory_local

    check_workers = max(
        1,
        min(
            int(settings.resolve_max_workers),
            int(settings.job_api_max_parallel),
        ),
    )

    if check_workers == 1 or total <= 1:
        for idx, ref in enumerate(references, start=1):
            local_issues, unresolved_local, retracted_local, predatory_local = _check_one(ref)
            issues.extend(local_issues)
            unresolved_refs += unresolved_local
            retracted_refs += retracted_local
            predatory_matches += predatory_local
            if progress and total and (idx == 1 or idx % step == 0 or idx == total):
                progress(f"Checked {idx}/{total} references", idx / total)
    else:
        ordered_results: dict[int, tuple[list[dict], int, int, int]] = {}
        with ThreadPoolExecutor(max_workers=check_workers) as ex:
            futures = {
                ex.submit(_check_one, ref): idx
                for idx, ref in enumerate(references, start=1)
            }
            completed = 0
            try:
                for fut in as_completed(futures):
                    idx = futures[fut]
                    ordered_results[idx] = fut.result()
                    completed += 1
                    if progress and total and (
                        completed == 1 or completed % step == 0 or completed == total
                    ):
                        progress(f"Checked {completed}/{total} references", completed / total)
            except Exception:
                for fut in futures:
                    fut.cancel()
                raise

        for idx in range(1, total + 1):
            item = ordered_results.get(idx)
            if not item:
                continue
            local_issues, unresolved_local, retracted_local, predatory_local = item
            issues.extend(local_issues)
            unresolved_refs += unresolved_local
            retracted_refs += retracted_local
            predatory_matches += predatory_local

    return issues, unresolved_refs, retracted_refs, predatory_matches

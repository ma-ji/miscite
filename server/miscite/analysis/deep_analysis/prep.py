from __future__ import annotations

from collections import Counter, defaultdict

from server.miscite.analysis.parse.citation_parsing import CitationInstance, ReferenceEntry
from server.miscite.analysis.deep_analysis.types import ResolvedWorkLike
from server.miscite.core.config import Settings


def build_citation_stats(
    citation_to_ref: list[tuple[CitationInstance, ReferenceEntry | None]],
) -> tuple[Counter[str], dict[str, list[str]]]:
    cite_counts: Counter[str] = Counter()
    cite_contexts: dict[str, list[str]] = defaultdict(list)
    for cit, ref in citation_to_ref:
        if not ref:
            continue
        cite_counts[ref.ref_id] += 1
        if cit.context:
            cite_contexts[ref.ref_id].append(cit.context.strip())
    return cite_counts, dict(cite_contexts)


def filter_verified_original_refs(
    *,
    settings: Settings,
    references: list[ReferenceEntry],
    resolved_by_ref_id: dict[str, ResolvedWorkLike],
) -> list[ReferenceEntry]:
    verified: list[ReferenceEntry] = []
    for ref in references:
        work = resolved_by_ref_id.get(ref.ref_id)
        if not work:
            continue
        if not work.source:
            continue
        if work.confidence < settings.deep_analysis_min_confidence:
            continue
        verified.append(ref)
    return verified

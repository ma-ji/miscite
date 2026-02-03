from __future__ import annotations

from collections import Counter, defaultdict

from server.miscite.analysis.match.types import CitationMatch
from server.miscite.analysis.parse.citation_parsing import ReferenceEntry
from server.miscite.analysis.deep_analysis.types import ResolvedWorkLike
from server.miscite.core.config import Settings


def build_citation_stats(
    citation_matches: list[CitationMatch],
) -> tuple[Counter[str], dict[str, list[str]]]:
    cite_counts: Counter[str] = Counter()
    cite_contexts: dict[str, list[str]] = defaultdict(list)
    for match in citation_matches:
        if not match.ref or match.status != "matched":
            continue
        cite_counts[match.ref.ref_id] += 1
        if match.citation.context:
            cite_contexts[match.ref.ref_id].append(match.citation.context.strip())
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

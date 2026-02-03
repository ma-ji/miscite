from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from server.miscite.analysis.parse.citation_parsing import CitationInstance, ReferenceEntry


CitationMatchStatus = Literal["matched", "ambiguous", "unmatched"]


@dataclass(frozen=True)
class CitationMatchCandidate:
    ref_id: str
    score: float
    reasons: list[str]


@dataclass(frozen=True)
class CitationMatch:
    citation: CitationInstance
    ref: ReferenceEntry | None
    status: CitationMatchStatus
    confidence: float
    method: str
    candidates: list[CitationMatchCandidate]
    notes: list[str]


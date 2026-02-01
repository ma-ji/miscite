from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol


class ResolvedWorkLike(Protocol):
    doi: str | None
    title: str | None
    year: int | None
    openalex_id: str | None
    openalex_record: dict | None
    source: str | None
    confidence: float


ProgressFn = Callable[[str, float], None]


@dataclass(frozen=True)
class DeepAnalysisResult:
    report: dict
    used_sources: list[dict]
    limitations: list[str]

from __future__ import annotations

from dataclasses import dataclass

from server.miscite.sources.predatory.data import PredatoryData, PredatoryRecord
from server.miscite.sources.predatory.normalize import normalize_issn, normalize_predatory_name


@dataclass(frozen=True)
class PredatoryMatch:
    record: PredatoryRecord
    match_type: str  # "issn_exact" | "name_exact"
    confidence: float

    def as_dict(self) -> dict:
        return {
            "record": self.record.__dict__,
            "match_type": self.match_type,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PredatoryMatcher:
    data: PredatoryData

    def match(self, *, journal: str | None, publisher: str | None, issn: str | None) -> PredatoryMatch | None:
        issn_n = normalize_issn(issn)
        if issn_n:
            rec = self.data.by_issn.get(issn_n)
            if rec:
                return PredatoryMatch(record=rec, match_type="issn_exact", confidence=1.0)

        journal_n = normalize_predatory_name(journal or "")
        if journal_n:
            rec = self.data.by_journal_name.get(journal_n)
            if rec:
                return PredatoryMatch(record=rec, match_type="name_exact", confidence=0.85)

        publisher_n = normalize_predatory_name(publisher or "")
        if publisher_n:
            rec = self.data.by_publisher_name.get(publisher_n)
            if rec:
                return PredatoryMatch(record=rec, match_type="name_exact", confidence=0.85)

        return None

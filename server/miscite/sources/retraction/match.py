from __future__ import annotations

from dataclasses import dataclass

from server.miscite.analysis.shared.normalize import normalize_doi
from server.miscite.sources.retraction.data import RetractionData, RetractionRecord


@dataclass(frozen=True)
class RetractionMatcher:
    data: RetractionData

    def get_by_doi(self, doi: str, *, retractions_only: bool = True) -> RetractionRecord | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        record = self.data.by_doi.get(doi_norm)
        if not record:
            return None
        if retractions_only:
            nature = (record.retraction_nature or "").lower()
            if nature and "retraction" not in nature:
                return None
        return record

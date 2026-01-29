from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from server.miscite.analysis.normalize import normalize_doi


@dataclass(frozen=True)
class RetractionRecord:
    doi: str
    record_id: str
    title: str
    journal: str
    publisher: str
    urls: str
    retraction_date: str
    retraction_nature: str
    reason: str
    paywalled: str
    notes: str


_RETRACTION_CACHE: dict[Path, tuple[float, dict[str, RetractionRecord]]] = {}
_PREDATORY_CACHE: dict[Path, tuple[float, list["PredatoryRecord"]]] = {}


class RetractionWatchDataset:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self._by_doi: dict[str, RetractionRecord] | None = None

    def _load(self) -> None:
        by_doi: dict[str, RetractionRecord] = {}
        if not self.csv_path.exists():
            self._by_doi = {}
            _RETRACTION_CACHE[self.csv_path] = (-1.0, self._by_doi)
            return

        mtime = self.csv_path.stat().st_mtime
        cached = _RETRACTION_CACHE.get(self.csv_path)
        if cached and cached[0] == mtime:
            self._by_doi = cached[1]
            return
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise RuntimeError("Retraction Watch CSV has no header row.")

            required = {
                "Record ID",
                "Title",
                "Journal",
                "Publisher",
                "URLS",
                "RetractionDate",
                "RetractionNature",
                "Reason",
                "OriginalPaperDOI",
                "Paywalled",
                "Notes",
            }
            missing = required.difference(set(reader.fieldnames))
            if missing:
                raise RuntimeError(f"Retraction Watch CSV missing required columns: {sorted(missing)}")

            for row in reader:
                doi = normalize_doi((row.get("OriginalPaperDOI") or "").strip())
                if not doi:
                    continue
                record = RetractionRecord(
                    doi=doi,
                    record_id=(row.get("Record ID") or "").strip(),
                    title=(row.get("Title") or "").strip(),
                    journal=(row.get("Journal") or "").strip(),
                    publisher=(row.get("Publisher") or "").strip(),
                    urls=(row.get("URLS") or "").strip(),
                    retraction_date=(row.get("RetractionDate") or "").strip(),
                    retraction_nature=(row.get("RetractionNature") or "").strip(),
                    reason=(row.get("Reason") or "").strip(),
                    paywalled=(row.get("Paywalled") or "").strip(),
                    notes=(row.get("Notes") or "").strip(),
                )
                existing = by_doi.get(doi)
                if existing is None:
                    by_doi[doi] = record
                else:
                    # Prefer a record explicitly marked as a retraction, if present.
                    if ("retraction" not in (existing.retraction_nature or "").lower()) and (
                        "retraction" in (record.retraction_nature or "").lower()
                    ):
                        by_doi[doi] = record
        self._by_doi = by_doi
        _RETRACTION_CACHE[self.csv_path] = (mtime, by_doi)

    def get_by_doi(self, doi: str, *, retractions_only: bool = True) -> RetractionRecord | None:
        if self._by_doi is None:
            self._load()
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        record = (self._by_doi or {}).get(doi_norm)
        if not record:
            return None
        if retractions_only:
            nature = (record.retraction_nature or "").lower()
            if nature and "retraction" not in nature:
                return None
        return record


@dataclass(frozen=True)
class PredatoryRecord:
    name: str
    venue_type: str  # "journal" | "publisher"
    issn: str
    source: str
    notes: str


class PredatoryVenueDataset:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self._records: list[PredatoryRecord] | None = None

    def _load(self) -> None:
        records: list[PredatoryRecord] = []
        if not self.csv_path.exists():
            self._records = []
            _PREDATORY_CACHE[self.csv_path] = (-1.0, self._records)
            return

        mtime = self.csv_path.stat().st_mtime
        cached = _PREDATORY_CACHE.get(self.csv_path)
        if cached and cached[0] == mtime:
            self._records = cached[1]
            return
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise RuntimeError("Predatory CSV has no header row.")
            required = {"name", "type", "issn", "source", "notes"}
            missing = required.difference(set(reader.fieldnames))
            if missing:
                raise RuntimeError(f"Predatory CSV missing required columns: {sorted(missing)}")
            for row in reader:
                records.append(
                    PredatoryRecord(
                        name=(row.get("name") or "").strip(),
                        venue_type=(row.get("type") or "").strip().lower(),
                        issn=(row.get("issn") or "").strip(),
                        source=(row.get("source") or "").strip(),
                        notes=(row.get("notes") or "").strip(),
                    )
                )
        self._records = records
        _PREDATORY_CACHE[self.csv_path] = (mtime, records)

    @staticmethod
    def _norm(s: str) -> str:
        cleaned = "".join(ch.lower() for ch in s.strip() if ch.isalnum() or ch.isspace())
        return " ".join(cleaned.split())

    def match(self, *, journal: str | None, publisher: str | None, issn: str | None) -> PredatoryRecord | None:
        if self._records is None:
            self._load()
        journal_n = self._norm(journal or "")
        publisher_n = self._norm(publisher or "")
        issn_n = (issn or "").replace("-", "").strip().lower()

        for rec in self._records or []:
            if issn_n and rec.issn:
                if issn_n == rec.issn.replace("-", "").strip().lower():
                    return rec
            if rec.venue_type == "journal" and journal_n and rec.name:
                name_n = self._norm(rec.name)
                if journal_n == name_n or name_n in journal_n:
                    return rec
            if rec.venue_type == "publisher" and publisher_n and rec.name:
                name_n = self._norm(rec.name)
                if publisher_n == name_n or name_n in publisher_n:
                    return rec
        return None

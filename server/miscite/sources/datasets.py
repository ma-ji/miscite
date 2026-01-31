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


class PredatoryVenueDataset:
    def __init__(self, csv_path: Path):
        self.csv_path = csv_path
        self._records: list[PredatoryRecord] | None = None
        self._by_issn: dict[str, PredatoryRecord] | None = None
        self._by_journal_name: dict[str, PredatoryRecord] | None = None
        self._by_publisher_name: dict[str, PredatoryRecord] | None = None

    def _load(self) -> None:
        records: list[PredatoryRecord] = []
        if not self.csv_path.exists():
            self._build_indexes([])
            _PREDATORY_CACHE[self.csv_path] = (-1.0, self._records or [])
            return

        mtime = self.csv_path.stat().st_mtime
        cached = _PREDATORY_CACHE.get(self.csv_path)
        if cached and cached[0] == mtime:
            self._build_indexes(list(cached[1]))
            return
        with self.csv_path.open("r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                raise RuntimeError("Predatory CSV has no header row.")

            fieldnames = [name.strip() for name in reader.fieldnames if name]
            lower_map = {name.lower(): name for name in fieldnames}

            required = {"name", "type", "issn", "source", "notes"}
            has_required = required.issubset(lower_map.keys())
            has_alt = "journal" in lower_map or "publisher" in lower_map

            if not has_required and not has_alt:
                raise RuntimeError(
                    "Predatory CSV missing required columns. Expected either "
                    "name/type/issn/source/notes or journal/publisher/issn/source/notes."
                )

            for row in reader:
                if has_required:
                    records.append(
                        PredatoryRecord(
                            name=(row.get(lower_map["name"]) or "").strip(),
                            venue_type=(row.get(lower_map["type"]) or "").strip().lower(),
                            issn=(row.get(lower_map.get("issn", "")) or "").strip(),
                            source=(row.get(lower_map.get("source", "")) or "").strip(),
                            notes=(row.get(lower_map.get("notes", "")) or "").strip(),
                        )
                    )
                    continue

                journal = (row.get(lower_map.get("journal", "")) or "").strip()
                publisher = (row.get(lower_map.get("publisher", "")) or "").strip()
                issn = (row.get(lower_map.get("issn", "")) or "").strip()
                source = (row.get(lower_map.get("source", "")) or "").strip()
                notes = (row.get(lower_map.get("notes", "")) or "").strip()

                if journal:
                    records.append(
                        PredatoryRecord(
                            name=journal,
                            venue_type="journal",
                            issn=issn,
                            source=source,
                            notes=notes,
                        )
                    )
                if publisher:
                    records.append(
                        PredatoryRecord(
                            name=publisher,
                            venue_type="publisher",
                            issn=issn,
                            source=source,
                            notes=notes,
                        )
                    )
        self._build_indexes(records)
        _PREDATORY_CACHE[self.csv_path] = (mtime, records)

    def _build_indexes(self, records: list[PredatoryRecord]) -> None:
        by_issn: dict[str, PredatoryRecord] = {}
        by_journal: dict[str, PredatoryRecord] = {}
        by_publisher: dict[str, PredatoryRecord] = {}

        for rec in records:
            issn_n = (rec.issn or "").replace("-", "").strip().lower()
            if issn_n and issn_n not in by_issn:
                by_issn[issn_n] = rec
            name_n = self._norm(rec.name or "")
            if not name_n:
                continue
            if rec.venue_type == "journal":
                by_journal.setdefault(name_n, rec)
            elif rec.venue_type == "publisher":
                by_publisher.setdefault(name_n, rec)

        self._records = records
        self._by_issn = by_issn
        self._by_journal_name = by_journal
        self._by_publisher_name = by_publisher

    @staticmethod
    def _norm(s: str) -> str:
        cleaned = "".join(ch.lower() for ch in s.strip() if ch.isalnum() or ch.isspace())
        return " ".join(cleaned.split())

    def match(self, *, journal: str | None, publisher: str | None, issn: str | None) -> PredatoryMatch | None:
        if self._records is None:
            self._load()
        journal_n = self._norm(journal or "")
        publisher_n = self._norm(publisher or "")
        issn_n = (issn or "").replace("-", "").strip().lower()

        if issn_n and self._by_issn:
            rec = self._by_issn.get(issn_n)
            if rec:
                return PredatoryMatch(record=rec, match_type="issn_exact", confidence=1.0)
        if journal_n and self._by_journal_name:
            rec = self._by_journal_name.get(journal_n)
            if rec:
                return PredatoryMatch(record=rec, match_type="name_exact", confidence=0.85)
        if publisher_n and self._by_publisher_name:
            rec = self._by_publisher_name.get(publisher_n)
            if rec:
                return PredatoryMatch(record=rec, match_type="name_exact", confidence=0.85)
        return None

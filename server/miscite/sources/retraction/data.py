from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from server.miscite.analysis.shared.normalize import normalize_doi


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


@dataclass(frozen=True)
class RetractionData:
    by_doi: dict[str, RetractionRecord]


_RETRACTION_CACHE: dict[Path, tuple[float, RetractionData]] = {}


def load_retraction_data(csv_path: Path) -> RetractionData:
    if not csv_path.exists():
        cached = _RETRACTION_CACHE.get(csv_path)
        if cached and cached[0] == -1.0:
            return cached[1]
        data = RetractionData(by_doi={})
        _RETRACTION_CACHE[csv_path] = (-1.0, data)
        return data

    mtime = csv_path.stat().st_mtime
    cached = _RETRACTION_CACHE.get(csv_path)
    if cached and cached[0] == mtime:
        return cached[1]

    by_doi = _read_retraction_csv(csv_path)
    data = RetractionData(by_doi=by_doi)
    _RETRACTION_CACHE[csv_path] = (mtime, data)
    return data


def _read_retraction_csv(csv_path: Path) -> dict[str, RetractionRecord]:
    by_doi: dict[str, RetractionRecord] = {}
    with csv_path.open("r", encoding="utf-8", newline="") as f:
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
    return by_doi

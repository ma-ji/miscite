from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from server.miscite.sources.predatory.normalize import normalize_issn, normalize_predatory_name


@dataclass(frozen=True)
class PredatoryRecord:
    name: str
    venue_type: str  # "journal" | "publisher"
    issn: str
    source: str
    notes: str


@dataclass(frozen=True)
class PredatoryData:
    records: list[PredatoryRecord]
    by_issn: dict[str, PredatoryRecord]
    by_journal_name: dict[str, PredatoryRecord]
    by_publisher_name: dict[str, PredatoryRecord]


_PREDATORY_CACHE: dict[Path, tuple[float, PredatoryData]] = {}


def load_predatory_data(csv_path: Path) -> PredatoryData:
    if not csv_path.exists():
        cached = _PREDATORY_CACHE.get(csv_path)
        if cached and cached[0] == -1.0:
            return cached[1]
        data = _build_predatory_data([])
        _PREDATORY_CACHE[csv_path] = (-1.0, data)
        return data

    mtime = csv_path.stat().st_mtime
    cached = _PREDATORY_CACHE.get(csv_path)
    if cached and cached[0] == mtime:
        return cached[1]

    records = _read_predatory_csv(csv_path)
    data = _build_predatory_data(records)
    _PREDATORY_CACHE[csv_path] = (mtime, data)
    return data


def _read_predatory_csv(csv_path: Path) -> list[PredatoryRecord]:
    records: list[PredatoryRecord] = []
    with csv_path.open("r", encoding="utf-8", newline="") as f:
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
    return records


def _build_predatory_data(records: list[PredatoryRecord]) -> PredatoryData:
    by_issn: dict[str, PredatoryRecord] = {}
    by_journal: dict[str, PredatoryRecord] = {}
    by_publisher: dict[str, PredatoryRecord] = {}

    for rec in records:
        issn_n = normalize_issn(rec.issn)
        if issn_n and issn_n not in by_issn:
            by_issn[issn_n] = rec
        name_n = normalize_predatory_name(rec.name or "")
        if not name_n:
            continue
        if rec.venue_type == "journal":
            by_journal.setdefault(name_n, rec)
        elif rec.venue_type == "publisher":
            by_publisher.setdefault(name_n, rec)

    return PredatoryData(
        records=list(records),
        by_issn=by_issn,
        by_journal_name=by_journal,
        by_publisher_name=by_publisher,
    )

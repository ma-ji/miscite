from __future__ import annotations

import contextlib
import csv
import io
import os
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from server.miscite.core.config import Settings


@dataclass(frozen=True)
class PredatorySyncResult:
    updated: bool
    skipped_reason: str | None
    target_csv: str
    detail: dict


def sync_predatory_datasets(settings: Settings, *, force: bool = False) -> PredatorySyncResult:
    target = settings.predatory_csv
    target.parent.mkdir(parents=True, exist_ok=True)
    stamp = target.parent / ".predatory_last_sync"

    with _file_lock(target.parent / ".predatory_sync.lock"):
        if not force and target.exists():
            freshness_path = stamp if stamp.exists() else target
            if _is_fresh(freshness_path, settings.predatory_sync_interval_hours):
                return PredatorySyncResult(
                    updated=False,
                    skipped_reason="fresh",
                    target_csv=str(target),
                    detail={"age_hours": _age_hours(freshness_path)},
                )
        elif not force and stamp.exists() and _is_fresh(stamp, settings.predatory_sync_interval_hours):
            return PredatorySyncResult(
                updated=False,
                skipped_reason="fresh",
                target_csv=str(target),
                detail={"age_hours": _age_hours(stamp)},
            )

        sources = [
            ("predatory_publishers", settings.predatory_publishers_url, "publisher"),
            ("predatory_journals", settings.predatory_journals_url, "journal"),
        ]

        all_records: list[tuple[str, str, str, str, str]] = []
        detail: dict = {}
        for label, url, kind in sources:
            if not url:
                raise RuntimeError(f"Missing URL for {label} (set MISCITE_PREDATORY_{label.upper()}_URL).")
            csv_url = _to_google_csv_url(url)
            rows = _download_csv_rows(csv_url, timeout=settings.api_timeout_seconds)
            records = _rows_to_records(rows, kind=kind, source_label=label, source_url=csv_url)
            detail[label] = {"url": csv_url, "rows": len(rows), "records": len(records)}
            all_records.extend(records)

        if not all_records:
            raise RuntimeError("Predatory sync produced zero records.")

        _write_predatory_csv(all_records, target)
        _touch(stamp)
        return PredatorySyncResult(updated=True, skipped_reason=None, target_csv=str(target), detail=detail)


def _to_google_csv_url(sheet_url: str) -> str:
    parsed = urlparse(sheet_url)
    if "docs.google.com" not in parsed.netloc or "/spreadsheets/" not in parsed.path:
        raise RuntimeError("Predatory list URL must be a Google Sheets URL.")
    if "export" in parsed.path and "format=csv" in parsed.query:
        return sheet_url

    parts = parsed.path.split("/d/")
    if len(parts) < 2:
        raise RuntimeError("Could not parse Google Sheets ID from URL.")
    tail = parts[1]
    sheet_id = tail.split("/", 1)[0]
    if not sheet_id:
        raise RuntimeError("Could not parse Google Sheets ID from URL.")

    query = parse_qs(parsed.query)
    gid = None
    if "gid" in query and query["gid"]:
        gid = query["gid"][0]
    if not gid and parsed.fragment:
        frag = parse_qs(parsed.fragment)
        if "gid" in frag and frag["gid"]:
            gid = frag["gid"][0]
    if not gid:
        gid = "0"

    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _download_csv_rows(url: str, *, timeout: float) -> list[list[str]]:
    headers = {"Accept": "text/csv,application/octet-stream;q=0.9,*/*;q=0.8"}
    resp = requests.get(url, headers=headers, timeout=timeout)
    resp.raise_for_status()
    text = resp.text
    if text.lstrip().startswith("<"):
        raise RuntimeError("Predatory list download returned HTML, not CSV. Ensure the sheet is public.")
    reader = csv.reader(io.StringIO(text))
    rows = [[cell.strip() for cell in row] for row in reader]
    return rows


def _rows_to_records(
    rows: list[list[str]],
    *,
    kind: str,
    source_label: str,
    source_url: str,
) -> list[tuple[str, str, str, str, str]]:
    header_idx, header_map = _detect_header(rows)
    start = header_idx + 1 if header_idx is not None else 0

    records: list[tuple[str, str, str, str, str]] = []
    seen: set[tuple[str, str, str]] = set()

    for row in rows[start:]:
        if not row or not any(cell for cell in row):
            continue

        if header_map:
            if kind == "journal":
                name = _get_cell(row, header_map.get("journal"))
            else:
                name = _get_cell(row, header_map.get("publisher"))
            issn = _get_cell(row, header_map.get("issn")) or ""
            notes = _get_cell(row, header_map.get("notes")) or ""
        else:
            name = _best_name_from_row(row)
            issn = ""
            notes = ""

        if not name:
            continue

        venue_type = kind
        source = source_label
        if notes:
            notes = f"{notes}; source_url={source_url}"
        else:
            notes = f"source_url={source_url}"

        key = (name.strip().lower(), venue_type.strip().lower(), issn.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        records.append((name, venue_type, issn, source, notes))

    return records


def _detect_header(rows: list[list[str]]) -> tuple[int | None, dict[str, int]]:
    header_map: dict[str, int] = {}
    for idx, row in enumerate(rows[:20]):
        lower = [cell.strip().lower() for cell in row if cell.strip()]
        if not lower:
            continue
        candidates: dict[str, int] = {}
        for col, cell in enumerate(row):
            val = cell.strip().lower()
            if val in {"journal", "journal name", "journal title", "title"}:
                candidates["journal"] = col
            if val in {"publisher", "publisher name", "publisher(s)"}:
                candidates["publisher"] = col
            if val in {"issn", "issn-l", "issn_l"}:
                candidates["issn"] = col
            if val in {"notes", "note", "comments", "comment", "remarks", "remark", "reason", "status", "url", "website"}:
                candidates["notes"] = col
        if candidates:
            return idx, candidates
    return None, header_map


def _get_cell(row: list[str], idx: int | None) -> str | None:
    if idx is None:
        return None
    if idx < 0 or idx >= len(row):
        return None
    return row[idx].strip()


def _best_name_from_row(row: list[str]) -> str | None:
    cells = [c.strip() for c in row if c and c.strip()]
    if not cells:
        return None
    if len(cells) >= 2 and cells[0].isdigit():
        return cells[1]
    return cells[0]


def _write_predatory_csv(records: list[tuple[str, str, str, str, str]], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(target.parent), prefix=".pred.", suffix=".tmp", newline="") as tmp:
        tmp_path = Path(tmp.name)
        writer = csv.writer(tmp)
        writer.writerow(["name", "type", "issn", "source", "notes"])
        for name, venue_type, issn, source, notes in records:
            writer.writerow([name, venue_type, issn, source, notes])
        tmp.flush()
        os.fsync(tmp.fileno())
    tmp_path.replace(target)


def _is_fresh(path: Path, interval_hours: int) -> bool:
    if interval_hours <= 0:
        return False
    if not path.exists():
        return False
    return _age_hours(path) < float(interval_hours)


def _age_hours(path: Path) -> float:
    try:
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return 1e9
    return max(0.0, (time.time() - mtime) / 3600.0)


@contextlib.contextmanager
def _file_lock(lock_path: Path):
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    import fcntl  # type: ignore

    f = lock_path.open("a+")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        yield
    finally:
        with contextlib.suppress(Exception):
            f.close()


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a"):
        os.utime(path, None)

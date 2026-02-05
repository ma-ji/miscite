from __future__ import annotations

from functools import lru_cache
import re
from pathlib import Path
from typing import Any

from server.miscite.analysis.parse.citation_parsing import ReferenceEntry


_DEFAULT_PATH = Path(__file__).resolve()
# repo root: .../server/miscite/analysis/shared/excluded_sources.py -> parents[4]
_REPO_ROOT = _DEFAULT_PATH.parents[4]
DEFAULT_EXCLUDED_SOURCES_PATH = _REPO_ROOT / "docs" / "excluded_sources.txt"


def _normalize_name(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split()).strip()


@lru_cache(maxsize=32)
def _load_excluded_sources_cached(path_str: str, mtime_ns: int, size: int) -> frozenset[str]:
    del mtime_ns, size  # cache key invalidates on file changes; values unused in body.
    src_path = Path(path_str)
    try:
        raw = src_path.read_text(encoding="utf-8")
    except OSError:
        return frozenset()
    out: set[str] = set()
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            continue
        norm = _normalize_name(line)
        if norm:
            out.add(norm)
    return frozenset(out)


def load_excluded_sources(path: Path | None = None) -> set[str]:
    src_path = (path or DEFAULT_EXCLUDED_SOURCES_PATH).resolve()
    try:
        stat = src_path.stat()
    except FileNotFoundError:
        return set()
    except OSError:
        return set()
    return set(
        _load_excluded_sources_cached(
            str(src_path),
            int(stat.st_mtime_ns),
            int(stat.st_size),
        )
    )


def matches_excluded_source(name: str | None, excluded: set[str]) -> bool:
    if not name or not excluded:
        return False
    norm = _normalize_name(name)
    if not norm:
        return False
    if norm in excluded:
        return True
    for ex in excluded:
        if ex and ex in norm:
            return True
    return False


def _append_values(candidates: list[str], value: object) -> None:
    if isinstance(value, str) and value.strip():
        candidates.append(value.strip())
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str) and item.strip():
                candidates.append(item.strip())


def collect_reference_candidates(ref: ReferenceEntry, record: dict | None) -> list[str]:
    candidates: list[str] = []
    _append_values(candidates, ref.raw)
    if not isinstance(record, dict):
        return candidates
    for key in (
        "container-title",
        "container_title",
        "journal",
        "publisher",
        "publisher-place",
        "source",
        "collection-title",
        "event",
        "event-title",
        "genre",
    ):
        _append_values(candidates, record.get(key))
    issued = record.get("issued")
    if isinstance(issued, dict):
        _append_values(candidates, issued.get("season"))
    return candidates


def collect_openalex_source_candidates(work: dict | None) -> list[str]:
    candidates: list[str] = []
    if not isinstance(work, dict):
        return candidates
    host = work.get("host_venue")
    if isinstance(host, dict):
        _append_values(candidates, host.get("display_name"))
        _append_values(candidates, host.get("publisher"))
    for loc_key in ("primary_location", "best_oa_location"):
        loc = work.get(loc_key)
        if not isinstance(loc, dict):
            continue
        src = loc.get("source")
        if isinstance(src, dict):
            _append_values(candidates, src.get("display_name"))
    return candidates


def collect_resolved_work_candidates(work: Any) -> list[str]:
    candidates: list[str] = []
    if work is None:
        return candidates
    if isinstance(work, dict):
        _append_values(candidates, work.get("journal"))
        _append_values(candidates, work.get("publisher"))
        openalex_record = work.get("openalex_record")
        if isinstance(openalex_record, dict):
            candidates.extend(collect_openalex_source_candidates(openalex_record))
        return candidates

    _append_values(candidates, getattr(work, "journal", None))
    _append_values(candidates, getattr(work, "publisher", None))
    openalex_record = getattr(work, "openalex_record", None)
    if isinstance(openalex_record, dict):
        candidates.extend(collect_openalex_source_candidates(openalex_record))
    return candidates


def openalex_work_is_excluded(work: dict | None, excluded: set[str]) -> bool:
    if not excluded:
        return False
    return any(
        matches_excluded_source(name, excluded)
        for name in collect_openalex_source_candidates(work)
    )


def resolved_work_is_excluded(work: Any, excluded: set[str]) -> bool:
    if not excluded:
        return False
    return any(
        matches_excluded_source(name, excluded)
        for name in collect_resolved_work_candidates(work)
    )


def reference_is_excluded(ref: ReferenceEntry, record: dict | None, excluded: set[str]) -> bool:
    if not excluded:
        return False
    for cand in collect_reference_candidates(ref, record):
        if matches_excluded_source(cand, excluded):
            return True
    return False

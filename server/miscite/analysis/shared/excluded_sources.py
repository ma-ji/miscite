from __future__ import annotations

from pathlib import Path
import re

from server.miscite.analysis.parse.citation_parsing import ReferenceEntry


_DEFAULT_PATH = Path(__file__).resolve()
# repo root: .../server/miscite/analysis/shared/excluded_sources.py -> parents[4]
_REPO_ROOT = _DEFAULT_PATH.parents[4]
DEFAULT_EXCLUDED_SOURCES_PATH = _REPO_ROOT / "docs" / "excluded_sources.txt"


def _normalize_name(name: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split()).strip()


def load_excluded_sources(path: Path | None = None) -> set[str]:
    src_path = path or DEFAULT_EXCLUDED_SOURCES_PATH
    try:
        raw = src_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return set()
    except OSError:
        return set()
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
    return out


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


def reference_is_excluded(ref: ReferenceEntry, record: dict | None, excluded: set[str]) -> bool:
    if not excluded:
        return False
    for cand in collect_reference_candidates(ref, record):
        if matches_excluded_source(cand, excluded):
            return True
    return False

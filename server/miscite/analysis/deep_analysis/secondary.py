from __future__ import annotations

import re
from typing import Any


_BOOK_REVIEW_TITLE_PATTERNS = [
    re.compile(r"\bbook review\b", re.IGNORECASE),
    re.compile(r"\breview of\b", re.IGNORECASE),
    re.compile(r"^review[:\-]\s", re.IGNORECASE),
]

_ALLOWLIST_TITLE_PATTERNS = [
    re.compile(r"\bliterature review\b", re.IGNORECASE),
    re.compile(r"\breview of (the )?literature\b", re.IGNORECASE),
    re.compile(r"\bsystematic review\b", re.IGNORECASE),
    re.compile(r"\bscoping review\b", re.IGNORECASE),
    re.compile(r"\bmeta[- ]analysis\b", re.IGNORECASE),
]


def _normalize_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _token_is_secondary(token: str) -> bool:
    norm = _normalize_token(token)
    if not norm:
        return False
    if "bookreview" in norm or re.search(r"\bbook review(s)?\b", norm):
        return True
    parts = set(norm.split())
    if "book" in parts and ("review" in parts or "reviews" in parts):
        return True
    return False


def _collect_type_tokens(
    *,
    record: dict | None,
    work_type: str | None,
    type_crossref: str | None,
    genre: Any,
) -> list[str]:
    out: list[str] = []
    for val in (work_type, type_crossref):
        if isinstance(val, str) and val.strip():
            out.append(val.strip())

    if isinstance(genre, str) and genre.strip():
        out.append(genre.strip())
    elif isinstance(genre, list):
        for item in genre:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())

    def _append_label_tokens(items: Any) -> None:
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
                continue
            if not isinstance(item, dict):
                continue
            for key in ("display_name", "keyword", "name", "label"):
                val = item.get(key)
                if isinstance(val, str) and val.strip():
                    out.append(val.strip())
                    break

    if isinstance(record, dict):
        for key in ("type", "type_crossref", "genre", "subtype"):
            val = record.get(key)
            if isinstance(val, str) and val.strip():
                out.append(val.strip())
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, str) and item.strip():
                        out.append(item.strip())
        _append_label_tokens(record.get("keywords"))
        _append_label_tokens(record.get("concepts"))
        _append_label_tokens(record.get("topics"))
    return out


def _title_is_secondary(title: str | None) -> bool:
    if not isinstance(title, str):
        return False
    text = " ".join(title.split())
    if not text:
        return False
    lower = text.lower()
    for pat in _ALLOWLIST_TITLE_PATTERNS:
        if pat.search(lower):
            return False
    for pat in _BOOK_REVIEW_TITLE_PATTERNS:
        if pat.search(lower):
            return True
    return False


def is_secondary_reference(
    *,
    title: str | None,
    openalex_record: dict | None = None,
    work_type: str | None = None,
    type_crossref: str | None = None,
    genre: Any = None,
) -> bool:
    tokens = _collect_type_tokens(
        record=openalex_record,
        work_type=work_type,
        type_crossref=type_crossref,
        genre=genre,
    )
    if any(_token_is_secondary(t) for t in tokens):
        return True
    inferred_title = title
    if not inferred_title and isinstance(openalex_record, dict):
        inferred_title = openalex_record.get("display_name") or openalex_record.get("title")
    return _title_is_secondary(inferred_title)

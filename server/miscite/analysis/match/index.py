from __future__ import annotations

import re
from dataclasses import dataclass

from server.miscite.analysis.parse.citation_parsing import ReferenceEntry
from server.miscite.analysis.shared.normalize import normalize_author_name, normalize_year_token

_REFNUM_RE = re.compile(
    r"^\s*(?:\[(?P<bracket>\d{1,4})\]\s*|(?P<plain>\d{1,4})[\).]\s+)"
)
_YEAR_TOKEN_RE = re.compile(r"\b(?P<year>(?:19|20)\d{2}[a-z]?)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ReferenceIndex:
    by_number: dict[str, ReferenceEntry]
    by_author_year: dict[str, list[ReferenceEntry]]
    by_author: dict[str, list[ReferenceEntry]]
    author_surnames_by_ref_id: dict[str, set[str]]
    year_token_by_ref_id: dict[str, str | None]


def _extract_ref_number(raw: str) -> int | None:
    if not raw:
        return None
    match = _REFNUM_RE.match(raw)
    if not match:
        return None
    try:
        hit = match.group("bracket") or match.group("plain")
        return int(hit) if hit else None
    except Exception:
        return None


def _extract_year_token(raw: str, *, fallback_year: int | None) -> str | None:
    text = raw or ""
    if fallback_year:
        # Prefer a suffixed year token like "2020a" if present in the raw string.
        m = re.search(rf"\b{int(fallback_year)}[a-z]\b", text, re.IGNORECASE)
        if m:
            return normalize_year_token(m.group(0))
        return normalize_year_token(str(int(fallback_year)))
    m = _YEAR_TOKEN_RE.search(text)
    if not m:
        return None
    return normalize_year_token(m.group("year"))


def _extract_author_surnames_from_csl(csl: dict | None) -> set[str]:
    if not isinstance(csl, dict):
        return set()
    authors = csl.get("author")
    if not isinstance(authors, list):
        return set()
    surnames: set[str] = set()
    for item in authors:
        if not isinstance(item, dict):
            continue
        family = item.get("family")
        if isinstance(family, str) and family.strip():
            norm = normalize_author_name(family)
            if norm:
                surnames.add(norm)
    return surnames


def build_reference_index(
    references: list[ReferenceEntry],
    *,
    reference_records: dict[str, dict],
) -> ReferenceIndex:
    by_number: dict[str, ReferenceEntry] = {}
    by_author_year: dict[str, list[ReferenceEntry]] = {}
    by_author: dict[str, list[ReferenceEntry]] = {}
    author_surnames_by_ref_id: dict[str, set[str]] = {}
    year_token_by_ref_id: dict[str, str | None] = {}

    for ref in references:
        year_token = _extract_year_token(ref.raw, fallback_year=ref.year)
        year_token_by_ref_id[ref.ref_id] = year_token

        csl = reference_records.get(ref.ref_id)
        author_surnames = _extract_author_surnames_from_csl(csl)
        if ref.first_author:
            first_author_norm = normalize_author_name(ref.first_author)
            if first_author_norm:
                author_surnames.add(first_author_norm)
        author_surnames_by_ref_id[ref.ref_id] = author_surnames

        # Numeric index
        ref_number = ref.ref_number
        if ref_number is None:
            ref_number = _extract_ref_number(ref.raw)
        if ref_number is not None:
            by_number.setdefault(str(ref_number), ref)

        # Author-year indices
        first_author_norm = normalize_author_name(ref.first_author)
        if first_author_norm:
            by_author.setdefault(first_author_norm, []).append(ref)
            if year_token:
                key_full = f"{first_author_norm}-{year_token}"
                by_author_year.setdefault(key_full, []).append(ref)
                # Also index under the unsuffixed year (e.g., 2020a -> 2020) for robustness.
                if len(year_token) >= 5 and year_token[:4].isdigit():
                    key_unsuffixed = f"{first_author_norm}-{year_token[:4]}"
                    if key_unsuffixed != key_full:
                        by_author_year.setdefault(key_unsuffixed, []).append(ref)
            elif ref.year:
                by_author_year.setdefault(f"{first_author_norm}-{int(ref.year)}", []).append(ref)

    return ReferenceIndex(
        by_number=by_number,
        by_author_year=by_author_year,
        by_author=by_author,
        author_surnames_by_ref_id=author_surnames_by_ref_id,
        year_token_by_ref_id=year_token_by_ref_id,
    )

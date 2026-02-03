from __future__ import annotations

import re
import unicodedata


_DOI_CLEAN_RE = re.compile(r"^[\s\[\(\{<]*(?P<doi>10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
_DOI_CORE_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
_AUTHOR_TOKEN_RE = re.compile(r"[a-z][a-z'’\\-]+", re.IGNORECASE)


def normalize_doi(raw: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip()

    match = _DOI_CLEAN_RE.match(raw)
    if match:
        candidate = match.group("doi")
    else:
        m2 = _DOI_CORE_RE.search(raw)
        if not m2:
            return None
        candidate = m2.group(1)

    candidate = candidate.rstrip(").,;]")
    return candidate.lower()


_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "with",
}


def content_tokens(text: str) -> set[str]:
    return {t for t in tokenize(text) if t not in _STOPWORDS and len(t) > 2}


def normalize_author_name(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    decomposed = unicodedata.normalize("NFKD", raw)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    cleaned = "".join(ch for ch in stripped.lower() if ch.isalnum())
    return cleaned or None


def normalize_year_token(value: str | int | None) -> str | None:
    if value is None:
        return None
    raw = str(value).strip().lower()
    if not raw:
        return None
    cleaned = "".join(ch for ch in raw if ch.isalnum())
    return cleaned or None


def normalize_author_year_key(author: str | None, year: int | str | None) -> str | None:
    author_norm = normalize_author_name(author)
    year_norm = normalize_year_token(year)
    if not (author_norm and year_norm):
        return None
    return f"{author_norm}-{year_norm}"


def normalize_author_year_locator(locator: str | None) -> str | None:
    if not locator:
        return None
    loc = str(locator).strip().lower()
    if not loc:
        return None
    author_raw = loc
    year_raw = ""
    if "-" in loc:
        author_raw, year_raw = loc.rsplit("-", 1)
    else:
        parts = loc.split()
        if len(parts) >= 2:
            year_raw = parts[-1]
            author_raw = " ".join(parts[:-1])
        else:
            match = re.search(r"(19|20)\d{2}[a-z]?$", loc)
            if match:
                year_raw = match.group(0)
                author_raw = loc[: match.start()]
    author_raw = author_raw.strip()
    if author_raw:
        multi_author_hint = (
            "," in author_raw
            or "&" in author_raw
            or ";" in author_raw
            or " and " in author_raw
            or " et al" in author_raw
        )
        if multi_author_hint:
            cut = author_raw
            for sep in [",", "&", ";"]:
                if sep in cut:
                    cut = cut.split(sep, 1)[0]
            if " and " in cut:
                cut = cut.split(" and ", 1)[0]
            if " et al" in cut:
                cut = cut.split(" et al", 1)[0]
            cut = cut.strip()
            m = _AUTHOR_TOKEN_RE.search(cut)
            if m:
                author_raw = m.group(0)
    author_norm = normalize_author_name(author_raw)
    year_norm = normalize_year_token(year_raw)
    if author_norm and year_norm:
        return f"{author_norm}-{year_norm}"
    if author_norm:
        return author_norm
    return normalize_year_token(loc) or loc

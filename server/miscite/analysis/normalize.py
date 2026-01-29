from __future__ import annotations

import re


_DOI_CLEAN_RE = re.compile(r"^[\s\[\(\{<]*(?P<doi>10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
_DOI_CORE_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)


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

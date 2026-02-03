from __future__ import annotations

import re
from dataclasses import dataclass

from server.miscite.analysis.shared.normalize import normalize_doi


_REF_HEADING_RE = re.compile(r"(^|\n)\s*(references|bibliography)\s*(\n|$)", re.IGNORECASE)


def split_references(text: str) -> tuple[str, str]:
    if not text:
        return "", ""
    match = None
    for m in _REF_HEADING_RE.finditer(text):
        match = m
    if not match:
        return text, ""
    start = match.start()
    end = match.end()
    return text[:start].strip(), text[end:].strip()


_DOI_RE = re.compile(r"(10\.\d{4,9}/[-._;()/:A-Z0-9]+)", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_REFNUM_RE = re.compile(
    r"^\s*(?:\[(?P<bracket>\d{1,4})\]\s*|(?P<plain>\d{1,4})[\).]\s+)"
)
_AUTHOR_START_RE = re.compile(r"^\s*([A-Z][A-Za-z'’\-]+)")


@dataclass(frozen=True)
class ReferenceEntry:
    ref_id: str
    raw: str
    ref_number: int | None
    doi: str | None
    year: int | None
    first_author: str | None


def parse_reference_entries(references_text: str) -> list[ReferenceEntry]:
    if not references_text:
        return []

    raw = references_text.replace("\r\n", "\n")
    lines = [ln.strip() for ln in raw.split("\n")]

    entries: list[str] = []
    current: list[str] = []

    def flush():
        nonlocal current
        if current:
            joined = " ".join([c for c in current if c]).strip()
            if joined:
                entries.append(joined)
        current = []

    for ln in lines:
        if not ln:
            flush()
            continue
        if _REFNUM_RE.match(ln) and current:
            flush()
        current.append(ln)
    flush()

    parsed: list[ReferenceEntry] = []
    for i, entry in enumerate(entries, start=1):
        num = None
        mnum = _REFNUM_RE.match(entry)
        if mnum:
            try:
                hit = mnum.group("bracket") or mnum.group("plain")
                num = int(hit) if hit else None
            except ValueError:
                num = None

        doi = None
        mdoi = _DOI_RE.search(entry)
        if mdoi:
            doi = normalize_doi(mdoi.group(1))

        year = None
        my = _YEAR_RE.search(entry)
        if my:
            try:
                year = int(my.group(1))
            except ValueError:
                year = None

        first_author = None
        ma = _AUTHOR_START_RE.match(entry)
        if ma:
            first_author = ma.group(1).lower()

        ref_id = str(num) if num is not None else f"ref-{i}"
        parsed.append(
            ReferenceEntry(ref_id=ref_id, raw=entry, ref_number=num, doi=doi, year=year, first_author=first_author)
        )
    return parsed


@dataclass(frozen=True)
class CitationInstance:
    kind: str  # "numeric" | "author_year"
    raw: str
    locator: str  # numeric: "12" ; author_year: "smith-2020"
    context: str


_AY_YEAR_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b", re.IGNORECASE)
_AY_AUTHOR_RE = re.compile(r"[A-Za-z][A-Za-z'’\-]+")
_AY_LEADING_RE = re.compile(r"^(see|see also|cf\.|cf|e\.g\.|eg)\s+", re.IGNORECASE)
_AY_SPLIT_RE = re.compile(r"\s*;\s*")


def split_multi_citations(citations: list[CitationInstance]) -> list[CitationInstance]:
    out: list[CitationInstance] = []
    for cit in citations:
        if cit.kind == "numeric":
            out.extend(_split_numeric_citation(cit))
        elif cit.kind == "author_year":
            out.extend(_split_author_year_citation(cit))
        else:
            out.append(cit)
    return out


def normalize_llm_citations(citations: list[CitationInstance]) -> list[CitationInstance]:
    groups: dict[tuple[str, str, str], list[CitationInstance]] = {}
    order: list[tuple[str, str, str]] = []
    for cit in citations:
        key = (cit.kind, (cit.raw or "").strip(), (cit.context or "").strip())
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(cit)

    out: list[CitationInstance] = []
    for key in order:
        kind, raw_key, context_key = key
        group = groups[key]
        cit = group[0]

        if kind == "numeric":
            locators = [(c.locator or "").strip() for c in group]
            locator_set = {l for l in locators if l}
            raw = raw_key
            body = raw_key
            if body.startswith("[") and body.endswith("]"):
                body = body[1:-1]
            if body.startswith("(") and body.endswith(")"):
                body = body[1:-1]
            raw_has_multi = any(ch in body for ch in [",", "-", "–", ";"])

            if raw_has_multi and len(locator_set) <= 1:
                numbers = _expand_numeric_citation_body(body)
                if numbers:
                    for num in numbers:
                        out.append(CitationInstance(kind="numeric", raw=f"[{num}]", locator=str(num), context=context_key))
                    continue

            for c in group:
                locator = (c.locator or "").strip()
                if locator.isdigit() and raw_has_multi:
                    out.append(CitationInstance(kind="numeric", raw=f"[{locator}]", locator=locator, context=c.context))
                else:
                    out.append(c)
            continue

        if kind == "author_year":
            raw = raw_key
            if ";" in raw_key and len(group) == 1:
                out.extend(_split_author_year_citation(cit))
            else:
                out.extend(group)
            continue

        out.extend(group)

    return out


def _split_numeric_citation(cit: CitationInstance) -> list[CitationInstance]:
    raw = (cit.raw or "").strip()
    if not raw:
        return [cit]
    body = raw
    if body.startswith("[") and body.endswith("]"):
        body = body[1:-1]
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    if not any(ch in body for ch in [",", "-", "–", ";"]):
        return [cit]
    numbers = _expand_numeric_citation_body(body)
    if len(numbers) <= 1:
        return [cit]
    return [
        CitationInstance(kind="numeric", raw=f"[{num}]", locator=str(num), context=cit.context) for num in numbers
    ]


def _split_author_year_citation(cit: CitationInstance) -> list[CitationInstance]:
    raw = (cit.raw or "").strip()
    if not raw:
        return [cit]
    year_hits = list(_AY_YEAR_RE.finditer(raw))
    if ";" not in raw and len(year_hits) <= 1:
        return [cit]
    body = raw
    if body.startswith("(") and body.endswith(")"):
        body = body[1:-1]
    parts = [p.strip() for p in _AY_SPLIT_RE.split(body) if p.strip()]
    if len(parts) <= 1:
        return [cit]
    out: list[CitationInstance] = []
    for part in parts:
        year_match = _AY_YEAR_RE.search(part)
        if not year_match:
            continue
        year = year_match.group(0).lower()
        author_part = part[: year_match.start()].strip()
        author_part = _AY_LEADING_RE.sub("", author_part).strip()
        author_part = author_part.rstrip(",;")
        author_match = _AY_AUTHOR_RE.search(author_part)
        if not author_match:
            continue
        author = author_match.group(0).lower()
        locator = f"{author}-{year}"
        raw_piece = f"({part.strip()})" if raw.startswith("(") and raw.endswith(")") else part.strip()
        out.append(CitationInstance(kind="author_year", raw=raw_piece, locator=locator, context=cit.context))
    return out if out else [cit]


_NUMERIC_CIT_RE = re.compile(r"\[(?P<body>\s*\d+(?:\s*[-–]\s*\d+)?(?:\s*,\s*\d+(?:\s*[-–]\s*\d+)?)*)\s*\]")
_NARRATIVE_AY_RE = re.compile(
    r"\b(?P<author>[A-Z][A-Za-z'’\-]+)(?:\s+et\s+al\.)?\s*\(\s*(?P<year>(?:19|20)\d{2}[a-z]?)\s*\)"
)
_PAREN_AY_CONTAINER_RE = re.compile(r"\((?P<body>[^)]*\b(?:19|20)\d{2}[a-z]?[^)]*)\)")
_PAREN_AY_ITEM_RE = re.compile(
    r"\b(?P<author>[A-Z][A-Za-z'’\-]+)(?:\s+et\s+al\.)?(?:\s*(?:&|and)\s*[A-Z][A-Za-z'’\-]+)?\s*,\s*(?P<year>(?:19|20)\d{2}[a-z]?)"
)


def _sentence_context(text: str, start: int, end: int) -> str:
    left_candidates = [
        text.rfind("\n", 0, start),
        text.rfind(".", 0, start),
        text.rfind("?", 0, start),
        text.rfind("!", 0, start),
    ]
    left = max(left_candidates)
    left = 0 if left == -1 else left + 1
    right_candidates = [text.find("\n", end), text.find(".", end), text.find("?", end), text.find("!", end)]
    right = min([c for c in right_candidates if c != -1], default=len(text))
    snippet = text[left:right].strip()
    if len(snippet) > 600:
        snippet = snippet[:600] + "…"
    return snippet


def extract_citation_instances(main_text: str) -> list[CitationInstance]:
    text = main_text or ""
    instances: list[CitationInstance] = []

    for m in _NUMERIC_CIT_RE.finditer(text):
        body = m.group("body")
        context = _sentence_context(text, m.start(), m.end())
        nums = _expand_numeric_citation_body(body)
        for n in nums:
            instances.append(CitationInstance(kind="numeric", raw=m.group(0), locator=str(n), context=context))

    for m in _NARRATIVE_AY_RE.finditer(text):
        author = m.group("author").lower()
        year = m.group("year").lower()
        context = _sentence_context(text, m.start(), m.end())
        instances.append(CitationInstance(kind="author_year", raw=m.group(0), locator=f"{author}-{year}", context=context))

    for container in _PAREN_AY_CONTAINER_RE.finditer(text):
        body = container.group("body")
        for m in _PAREN_AY_ITEM_RE.finditer(body):
            author = m.group("author").lower()
            year = m.group("year").lower()
            context = _sentence_context(text, container.start(), container.end())
            instances.append(
                CitationInstance(kind="author_year", raw=container.group(0), locator=f"{author}-{year}", context=context)
            )

    return instances


def _expand_numeric_citation_body(body: str) -> list[int]:
    out: list[int] = []
    parts = [p.strip() for p in body.replace("–", "-").split(",") if p.strip()]
    for part in parts:
        if "-" in part:
            left, right = [s.strip() for s in part.split("-", 1)]
            try:
                a = int(left)
                b = int(right)
            except ValueError:
                continue
            if a <= 0 or b <= 0:
                continue
            if b < a:
                a, b = b, a
            # Guard against crazy expansions.
            if b - a > 200:
                continue
            out.extend(list(range(a, b + 1)))
        else:
            try:
                n = int(part)
            except ValueError:
                continue
            if n > 0:
                out.append(n)
    return out

from __future__ import annotations

import re
from dataclasses import dataclass

from server.miscite.analysis.citation_parsing import CitationInstance, ReferenceEntry
from server.miscite.analysis.normalize import normalize_doi
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.prompts import get_prompt, render_prompt


@dataclass(frozen=True)
class LlmParseResult:
    citations: list[CitationInstance]
    references: list[ReferenceEntry]
    reference_records: dict[str, dict]
    notes: list[str]


def parse_references_with_llm(
    llm: OpenRouterClient,
    references_text: str,
    *,
    max_chars: int,
    max_refs: int,
) -> tuple[list[ReferenceEntry], dict[str, dict], list[str]]:
    notes: list[str] = []
    text = (references_text or "").strip()
    if not text:
        raise RuntimeError("No references text provided for LLM bibliography parsing.")

    if len(text) > max_chars:
        notes.append(f"References text truncated from {len(text)} to {max_chars} chars for LLM parsing.")
        text = text[:max_chars]

    payload = llm.chat_json(system=_SYSTEM_REFERENCES, user=_references_prompt(text, max_refs=max_refs))

    refs_raw = payload.get("references")
    if not isinstance(refs_raw, list):
        raise RuntimeError("LLM references JSON missing 'references' list.")

    reference_records: dict[str, dict] = {}
    references: list[ReferenceEntry] = []
    for i, item in enumerate(refs_raw[:max_refs], start=1):
        if not isinstance(item, dict):
            continue
        raw = str(item.get("raw") or "").strip()
        if not raw:
            continue

        ref_number = _safe_int(item.get("ref_number"))
        doi = normalize_doi(str(item.get("doi") or ""))

        csl = item.get("csl")
        if isinstance(csl, dict):
            doi = doi or normalize_doi(str(csl.get("DOI") or csl.get("doi") or ""))

        year = _extract_year(item.get("year"), csl)
        first_author = _extract_first_author(item.get("first_author"), csl)

        ref_id = str(ref_number) if ref_number is not None else str(item.get("id") or f"ref-{i}")
        references.append(
            ReferenceEntry(ref_id=ref_id, raw=raw, ref_number=ref_number, doi=doi, year=year, first_author=first_author)
        )
        if isinstance(csl, dict):
            reference_records[ref_id] = csl

    out_notes = []
    notes_payload = payload.get("notes")
    if isinstance(notes_payload, list):
        out_notes.extend([str(n) for n in notes_payload if str(n).strip()])
    out_notes.extend(notes)
    return references, reference_records, out_notes


def extract_references_section_with_llm(
    llm: OpenRouterClient,
    full_text: str,
    *,
    max_chars: int,
) -> tuple[str | None, list[str]]:
    notes: list[str] = []
    text = (full_text or "").strip()
    if not text:
        raise RuntimeError("No document text provided for LLM references-section extraction.")

    if len(text) > max_chars:
        notes.append(f"Document text truncated from {len(text)} to {max_chars} chars for references-section extraction.")
        text = text[-max_chars:]
        notes.append("Used tail of document for references-section extraction.")

    payload = llm.chat_json(system=_SYSTEM_REF_SECTION, user=_references_section_prompt(text))
    refs_text = payload.get("references_text")
    if refs_text is not None and not isinstance(refs_text, str):
        raise RuntimeError("LLM references_text must be a string or null.")
    refs_text = (refs_text or "").strip() or None

    conf = payload.get("confidence")
    if conf is not None:
        try:
            conf_f = float(conf)
        except Exception as e:
            raise RuntimeError("LLM references-section confidence must be a number 0..1.") from e
        if conf_f < 0.0 or conf_f > 1.0:
            raise RuntimeError("LLM references-section confidence out of range.")

    out_notes = []
    notes_payload = payload.get("notes")
    if isinstance(notes_payload, list):
        out_notes.extend([str(n) for n in notes_payload if str(n).strip()])
    out_notes.extend(notes)
    return refs_text, out_notes


def parse_citations_with_llm(
    llm: OpenRouterClient,
    main_text: str,
    *,
    max_chars_full: int,
    max_lines: int,
    max_chars_candidates: int,
) -> tuple[list[CitationInstance], list[str]]:
    notes: list[str] = []
    text = (main_text or "").strip()
    if not text:
        raise RuntimeError("No main text provided for LLM citation parsing.")

    if len(text) <= max_chars_full:
        content = text
    else:
        # Reduce prompt size: only include lines that likely contain citations.
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        picked: list[str] = []
        total = 0
        for ln in lines:
            if not _looks_like_citation_line(ln):
                continue
            if len(picked) >= max_lines:
                break
            if total + len(ln) + 1 > max_chars_candidates:
                break
            picked.append(ln)
            total += len(ln) + 1
        content = "\n".join(picked)
        notes.append(
            f"Main text too large for full LLM pass ({len(text)} chars); sent {len(content)} chars of citation-like lines."
        )

    payload = llm.chat_json(system=_SYSTEM_CITATIONS, user=_citations_prompt(content))

    cits_raw = payload.get("citations")
    if not isinstance(cits_raw, list):
        raise RuntimeError("LLM citations JSON missing 'citations' list.")

    citations: list[CitationInstance] = []
    for item in cits_raw:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip().lower()
        if kind not in {"numeric", "author_year"}:
            continue
        raw = str(item.get("raw") or "").strip()
        locator = str(item.get("locator") or "").strip().lower()
        context = str(item.get("context") or "").strip()
        if not (raw and locator and context):
            continue
        citations.append(CitationInstance(kind=kind, raw=raw, locator=locator, context=context))

    out_notes = []
    notes_payload = payload.get("notes")
    if isinstance(notes_payload, list):
        out_notes.extend([str(n) for n in notes_payload if str(n).strip()])
    out_notes.extend(notes)
    return citations, out_notes


def _safe_int(value) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        return int(value)
    except Exception:
        return None


def _extract_year(year_value, csl: dict | None) -> int | None:
    y = _safe_int(year_value)
    if y:
        return y
    if isinstance(csl, dict):
        issued = csl.get("issued")
        if isinstance(issued, dict):
            dp = issued.get("date-parts")
            if isinstance(dp, list) and dp and isinstance(dp[0], list) and dp[0]:
                return _safe_int(dp[0][0])
    return None


def _extract_first_author(value, csl: dict | None) -> str | None:
    v = str(value or "").strip()
    if v:
        return v.lower()
    if isinstance(csl, dict):
        authors = csl.get("author")
        if isinstance(authors, list) and authors:
            first = authors[0]
            if isinstance(first, dict):
                family = str(first.get("family") or "").strip()
                if family:
                    return family.lower()
    return None


_YEAR_HINT_RE = re.compile(r"\b(19|20)\d{2}[a-z]?\b")
_NUMERIC_HINT_RE = re.compile(r"\[\s*\d")
_AUTHOR_HINT_RE = re.compile(r"\b(et\s+al\.|\([A-Za-z].*?(19|20)\d{2})")


def _looks_like_citation_line(line: str) -> bool:
    if _NUMERIC_HINT_RE.search(line):
        return True
    if _YEAR_HINT_RE.search(line) and _AUTHOR_HINT_RE.search(line):
        return True
    # Some styles: "Smith et al. (2020)"
    if "et al" in line.lower() and _YEAR_HINT_RE.search(line):
        return True
    return False


_SYSTEM_REFERENCES = get_prompt("parsing/references/system")


def _references_prompt(text: str, *, max_refs: int) -> str:
    return render_prompt("parsing/references/user", text=text, max_refs=max_refs)


_SYSTEM_CITATIONS = get_prompt("parsing/citations/system")


_SYSTEM_REF_SECTION = get_prompt("parsing/ref_section/system")


def _references_section_prompt(text: str) -> str:
    return render_prompt("parsing/ref_section/user", text=text)


def _citations_prompt(text: str) -> str:
    return render_prompt("parsing/citations/user", text=text)

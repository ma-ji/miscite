from __future__ import annotations

import re
from typing import Any

from server.miscite.analysis.deep_analysis.subsections import Subsection
from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.prompts import get_prompt, render_prompt

_MAX_HEADING_LINE_LEN = 120
_MAX_HEADING_WORDS = 14

_FIGURE_PREFIX = re.compile(r"^(figure|fig\.|table|appendix|supplement|supp\.|equation|eq\.)\b", re.IGNORECASE)
_URL_HINT = re.compile(r"https?://", re.IGNORECASE)
_DOI_HINT = re.compile(r"\b10\.\d{4,9}/\S+\b", re.IGNORECASE)

_NUMBERING_PREFIX = re.compile(r"^\s*(\(?\d+(?:\.\d+){0,6}\)?|[IVXLC]+)\s*[\.\)\-:]\s+", re.IGNORECASE)


def extract_subsections_with_llm(
    *,
    settings: Settings,
    llm_client: OpenRouterClient,
    text: str,
) -> tuple[list[Subsection], dict[str, Any], list[str]]:
    """
    Build a standardized subsection structure using an LLM over heading candidates.

    Returns (subsections, structure_report, notes). Falls back to an empty subsection list if no headings found.
    """
    raw = (text or "").replace("\r\n", "\n")
    lines = raw.split("\n")
    candidates, trunc = _heading_candidates(lines, max_candidates=int(settings.deep_analysis_structure_max_candidates))
    if not candidates:
        return [], {"mode": "llm", "status": "skipped", "reason": "No heading candidates found.", "truncation": trunc}, []

    title_by_line = {int(c["line"]): str(c["text"]) for c in candidates if isinstance(c, dict)}
    payload = llm_client.chat_json(
        system=get_prompt("deep_analysis/structure/system"),
        user=render_prompt(
            "deep_analysis/structure/user",
            candidates="\n".join([f"{c['line']} | indent={c['indent']} | {c['text']}" for c in candidates]),
        ),
    )
    headings, notes = _validate_headings_payload(payload, total_lines=len(lines))
    # Enforce non-renaming: always use the exact candidate text for the chosen heading line.
    enforced: list[dict[str, Any]] = []
    for h in headings:
        line_no = int(h.get("line") or 0)
        if line_no not in title_by_line:
            continue
        enforced.append({"line": line_no, "title": title_by_line[line_no], "level": int(h.get("level") or 1)})
    headings = enforced
    if not headings:
        return [], {
            "mode": "llm",
            "status": "skipped",
            "reason": "LLM did not return usable headings.",
            "notes": notes,
            "truncation": trunc,
        }, notes

    subsections = _subsections_from_headings(lines, headings)
    structure_report = {
        "mode": "llm",
        "status": "completed",
        "headings": headings,
        "subsections": [
            {
                "subsection_id": s.subsection_id,
                "title": s.title,
                "level": s.level,
                "chars": len(s.text or ""),
            }
            for s in subsections
        ],
        "notes": notes,
        "truncation": trunc,
    }
    return subsections, structure_report, notes


def _heading_candidates(lines: list[str], *, max_candidates: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    scored: list[tuple[int, int, str]] = []

    def _is_blank(idx: int) -> bool:
        if idx < 0 or idx >= len(lines):
            return True
        return not (lines[idx] or "").strip()

    indents: dict[int, int] = {}
    for idx, ln in enumerate(lines):
        raw_line = ln or ""
        indents[idx + 1] = len(raw_line) - len(raw_line.lstrip(" \t"))
        text = raw_line.strip()
        if not text:
            continue
        if len(text) > _MAX_HEADING_LINE_LEN:
            continue
        if len(text.split()) > _MAX_HEADING_WORDS:
            continue
        lower = text.lower()
        if _URL_HINT.search(lower) or _DOI_HINT.search(lower):
            continue
        if _FIGURE_PREFIX.match(lower):
            continue
        if text.endswith((".", ";", ",")):
            continue

        prev_blank = _is_blank(idx - 1)
        next_blank = _is_blank(idx + 1)

        score = 0
        if _NUMBERING_PREFIX.match(text):
            score += 4
        if prev_blank and next_blank:
            score += 3
        elif prev_blank or next_blank:
            score += 1
        if text.isupper() and len(text) >= 5:
            score += 2
        if any(token in lower for token in ["introduction", "methods", "results", "discussion", "conclusion", "abstract"]):
            score += 1

        if score <= 0:
            continue
        scored.append((score, idx + 1, text))

    # If we found very few candidates, broaden with a weaker heuristic.
    if len(scored) < 6:
        for idx, ln in enumerate(lines):
            raw_line = ln or ""
            indents[idx + 1] = len(raw_line) - len(raw_line.lstrip(" \t"))
            text = raw_line.strip()
            if not text:
                continue
            if len(text) > _MAX_HEADING_LINE_LEN or len(text.split()) > _MAX_HEADING_WORDS:
                continue
            lower = text.lower()
            if _URL_HINT.search(lower) or _DOI_HINT.search(lower) or _FIGURE_PREFIX.match(lower):
                continue
            if text.endswith((".", ";", ",")):
                continue
            if _NUMBERING_PREFIX.match(text) or (text.isupper() and len(text) >= 5):
                scored.append((1, idx + 1, text))

    # Deduplicate by line number.
    best_by_line: dict[int, tuple[int, str]] = {}
    for score, line_no, text in scored:
        prev = best_by_line.get(line_no)
        if prev is None or score > prev[0]:
            best_by_line[line_no] = (score, text)

    items = [(ln, sc, tx) for ln, (sc, tx) in best_by_line.items()]
    items.sort(key=lambda x: (-x[1], x[0]))

    trunc = {"candidates_total": len(items), "candidates_used": len(items), "hit_max_candidates": False}
    if max_candidates > 0 and len(items) > max_candidates:
        trunc["hit_max_candidates"] = True
        trunc["candidates_used"] = max_candidates
        items = items[:max_candidates]

    # Present candidates in line order.
    items.sort(key=lambda x: x[0])
    return [{"line": int(line_no), "indent": int(indents.get(int(line_no), 0)), "text": text} for line_no, _score, text in items], trunc


def _validate_headings_payload(payload: Any, *, total_lines: int) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(payload, dict):
        return [], ["LLM structure payload was not a JSON object."]
    raw_headings = payload.get("headings")
    raw_notes = payload.get("notes")
    notes = [str(n).strip() for n in raw_notes if isinstance(raw_notes, list) and isinstance(n, str) and n.strip()] if isinstance(raw_notes, list) else []
    if not isinstance(raw_headings, list):
        return [], notes + ["LLM structure payload missing 'headings' list."]

    cleaned: list[dict[str, Any]] = []
    last_line = 0
    seen_lines: set[int] = set()
    for item in raw_headings:
        if not isinstance(item, dict):
            continue
        line = item.get("line")
        title = item.get("title")
        level = item.get("level")
        try:
            line_i = int(line)
        except Exception:
            continue
        if line_i <= 0 or line_i > max(1, int(total_lines)):
            continue
        if line_i in seen_lines:
            continue
        if line_i <= last_line:
            continue
        if not isinstance(title, str) or not title.strip():
            continue
        try:
            level_i = int(level)
        except Exception:
            level_i = 1
        level_i = max(1, min(6, level_i))
        title_clean = " ".join(title.split()).strip()
        cleaned.append({"line": line_i, "title": title_clean, "level": level_i})
        seen_lines.add(line_i)
        last_line = line_i

    return cleaned, notes


def _subsections_from_headings(lines: list[str], headings: list[dict[str, Any]]) -> list[Subsection]:
    if not headings:
        return []
    # headings are already validated + strictly increasing
    out: list[Subsection] = []

    first_line = int(headings[0]["line"])
    preamble = "\n".join(lines[: max(0, first_line - 1)]).strip()
    if preamble:
        out.append(Subsection(subsection_id="S0", title="opening", level=1, text=preamble))

    for i, h in enumerate(headings, start=1):
        line_no = int(h["line"])
        title = str(h["title"])
        level = int(h.get("level") or 1)
        start = min(max(0, line_no), len(lines))
        end = min(max(0, int(headings[i]["line"]) - 1), len(lines)) if i < len(headings) else len(lines)
        body = "\n".join(lines[start:end]).strip()
        if not body:
            continue
        out.append(Subsection(subsection_id=f"S{len(out)+1}", title=title, level=level, text=body))

    # Re-number ids sequentially (stable order).
    renumbered: list[Subsection] = []
    for idx, s in enumerate(out, start=1):
        renumbered.append(Subsection(subsection_id=f"S{idx}", title=s.title, level=s.level, text=s.text))
    return renumbered

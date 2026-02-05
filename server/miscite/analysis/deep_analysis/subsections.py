from __future__ import annotations

import re
from collections import defaultdict, deque
from dataclasses import dataclass

from server.miscite.analysis.match.match import match_citations_to_references
from server.miscite.analysis.parse.citation_parsing import (
    CitationInstance,
    ReferenceEntry,
    extract_citation_instances,
    normalize_llm_citations,
    split_multi_citations,
)


@dataclass(frozen=True)
class Subsection:
    subsection_id: str
    title: str
    level: int
    text: str


_HEADING_RE = re.compile(
    r"^\s*(?P<num>\d+(?:\.\d+){0,6})?\s*(?:[\)\.:\-–—]\s*)?(?P<title>[A-Za-z][A-Za-z0-9 &/\\-]{2,80})\s*$"
)


def extract_subsections(text: str) -> list[Subsection]:
    """
    Best-effort subsection splitter based on heading-like lines.

    If no headings are detected, returns a single subsection with the entire text.
    """
    raw = (text or "").replace("\r\n", "\n")
    if not raw.strip():
        return []

    lines = raw.split("\n")
    headings: list[tuple[int, str, int]] = []

    def _looks_like_heading(line: str) -> bool:
        candidate = line.strip()
        if len(candidate) < 3 or len(candidate) > 90:
            return False
        if candidate.endswith("."):
            return False
        if "http://" in candidate.lower() or "https://" in candidate.lower():
            return False
        if "[" in candidate or "]" in candidate:
            return False
        if candidate.count(",") >= 2:
            return False
        if len(candidate.split()) > 12:
            return False
        return True

    for idx, ln in enumerate(lines):
        if not _looks_like_heading(ln):
            continue
        m = _HEADING_RE.match(ln)
        if not m:
            continue
        num = (m.group("num") or "").strip()
        title = (m.group("title") or "").strip()
        if not title:
            continue
        level = (num.count(".") + 1) if num else 1
        full_title = f"{num} {title}".strip() if num else title
        headings.append((idx, full_title, level))

    if not headings:
        return [Subsection(subsection_id="S1", title="opening", level=1, text=raw.strip())]

    # Drop headings that are too close together (often extraction noise).
    filtered: list[tuple[int, str, int]] = []
    for item in headings:
        if filtered and item[0] - filtered[-1][0] <= 1:
            continue
        filtered.append(item)

    subsections: list[Subsection] = []

    # Include any preamble text before the first heading.
    first_heading_idx = filtered[0][0]
    preamble = "\n".join(lines[:first_heading_idx]).strip()
    if preamble:
        subsections.append(Subsection(subsection_id="S0", title="opening", level=1, text=preamble))

    for i, (line_idx, title, level) in enumerate(filtered, start=1):
        start_line = line_idx + 1
        end_line = filtered[i][0] if i < len(filtered) else len(lines)
        body = "\n".join(lines[start_line:end_line]).strip()
        if not body:
            continue
        subsections.append(Subsection(subsection_id=f"S{i}", title=title, level=level, text=body))

    return subsections or [Subsection(subsection_id="S1", title="opening", level=1, text=raw.strip())]


def collapse_to_top_level_sections(subsections: list[Subsection]) -> list[Subsection]:
    """
    Collapse a subsection list to "top-level sections" by combining all nested levels under
    the nearest preceding top-level heading.

    Top-level is defined as the minimum level observed (often 1).
    """
    if not subsections:
        return []

    try:
        # Ignore the synthetic "opening" preamble when choosing top-level; otherwise it can
        # incorrectly force all headings to be treated as nested.
        non_opening = [s for s in subsections if (s.title or "").strip().lower() != "opening"]
        level_source = non_opening if non_opening else subsections
        top_level = min(int(s.level) for s in level_source if isinstance(s.level, int))
    except Exception:
        top_level = 1

    out: list[Subsection] = []
    current_title = ""
    current_level = top_level
    current_text_parts: list[str] = []

    def _flush() -> None:
        nonlocal current_title, current_level, current_text_parts
        text = "\n\n".join([p for p in current_text_parts if (p or "").strip()]).strip()
        if current_title and text:
            out.append(Subsection(subsection_id=f"S{len(out) + 1}", title=current_title, level=current_level, text=text))
        current_title = ""
        current_level = top_level
        current_text_parts = []

    for s in subsections:
        title = (s.title or "").strip()
        body = (s.text or "").strip()
        if not body:
            continue
        level = int(s.level) if isinstance(s.level, int) else top_level

        if level <= top_level or not current_title:
            _flush()
            current_title = title or "opening"
            current_level = top_level
            current_text_parts = [body]
            continue

        # Nested heading: include its title as a separator so the combined text remains scannable.
        if title:
            current_text_parts.append(f"{title}\n{body}".strip())
        else:
            current_text_parts.append(body)

    _flush()
    return out


def extract_cited_ref_ids_by_subsection(
    *,
    subsections: list[Subsection],
    references: list[ReferenceEntry],
    reference_records: dict[str, dict],
) -> dict[str, set[str]]:
    """
    Extract citations *from the subsection text* (regex) and match to bibliography entries.

    This is independent of the pipeline's LLM citation parsing (which may be partial or line-based).
    """
    if not subsections or not references:
        return {}

    cited: dict[str, set[str]] = defaultdict(set)
    for subsection in subsections:
        cits = extract_citation_instances(subsection.text)
        if not cits:
            continue
        cits = split_multi_citations(cits)
        cits = normalize_llm_citations(cits)
        matches = match_citations_to_references(cits, references, reference_records=reference_records)
        for m in matches:
            if m.status != "matched" or not m.ref:
                continue
            cited[subsection.subsection_id].add(m.ref.ref_id)
    return dict(cited)


def build_weak_adjacency(nodes: set[str], edges: list[tuple[str, str]]) -> dict[str, set[str]]:
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for src, dst in edges:
        if src not in adj or dst not in adj:
            continue
        adj[src].add(dst)
        adj[dst].add(src)
    return adj


def subnetwork_nodes_by_distance(
    *,
    adjacency: dict[str, set[str]],
    seed_nodes: set[str],
    max_hops: int,
    max_nodes: int,
) -> tuple[dict[str, int], bool]:
    dist: dict[str, int] = {}
    if not adjacency or not seed_nodes:
        return dist, False

    q: deque[str] = deque()
    for s in seed_nodes:
        if s in adjacency and s not in dist:
            dist[s] = 0
            q.append(s)

    hit_max_nodes = False
    while q:
        cur = q.popleft()
        d = dist[cur]
        if d >= max_hops:
            continue
        for nb in adjacency.get(cur, ()):
            if nb in dist:
                continue
            if len(dist) >= max_nodes:
                hit_max_nodes = True
                q.clear()
                break
            dist[nb] = d + 1
            q.append(nb)

    return dist, hit_max_nodes

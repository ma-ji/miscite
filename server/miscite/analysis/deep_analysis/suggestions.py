from __future__ import annotations

import re
from typing import Any

from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.prompts import get_prompt, render_prompt


_SECTION_ALIAS: dict[str, str] = {
    "abstract": "Abstract",
    "introduction": "Introduction",
    "background": "Background",
    "literature review": "Literature Review",
    "related work": "Literature Review",
    "related works": "Literature Review",
    "methods": "Methods",
    "methodology": "Methods",
    "materials and methods": "Methods",
    "materials & methods": "Methods",
    "data": "Data",
    "dataset": "Data",
    "results": "Results",
    "findings": "Results",
    "discussion": "Discussion",
    "conclusion": "Conclusion",
    "conclusions": "Conclusion",
    "limitations": "Limitations",
    "future work": "Future Work",
    "future directions": "Future Work",
    "implications": "Implications",
}

_DEFAULT_SECTION_ORDER = [
    "Introduction",
    "Literature Review",
    "Methods",
    "Results",
    "Discussion",
    "Conclusion",
    "Limitations",
    "Future Work",
]

_HEADING_LINE_RE = re.compile(r"^[\s\d\.\-–—]*([A-Za-z][A-Za-z &/\\-]{2,})\s*$")


def extract_section_order(text: str) -> list[str]:
    if not text:
        return list(_DEFAULT_SECTION_ORDER)
    seen: set[str] = set()
    order: list[str] = []
    for line in text.splitlines():
        candidate = line.strip()
        if len(candidate) < 3 or len(candidate) > 80:
            continue
        match = _HEADING_LINE_RE.match(candidate)
        if not match:
            continue
        heading = match.group(1)
        norm = re.sub(r"[^a-z0-9& ]+", " ", heading.lower()).strip()
        norm = re.sub(r"\s+", " ", norm)
        label = _SECTION_ALIAS.get(norm)
        if not label or label in seen:
            continue
        seen.add(label)
        order.append(label)
    return order or list(_DEFAULT_SECTION_ORDER)


def build_suggestions(
    *,
    settings: Settings,
    llm_client: OpenRouterClient,
    paper_excerpt: str,
    llm_budget: int | None,
    citation_groups: list[dict],
    references_by_rid: dict[str, dict],
    section_order: list[str],
) -> tuple[dict, int]:
    calls_used = 0

    if not isinstance(citation_groups, list) or not citation_groups:
        return {"status": "skipped", "reason": "No citation groups available."}, calls_used
    if not isinstance(references_by_rid, dict) or not references_by_rid:
        return {"status": "skipped", "reason": "No reference list available."}, calls_used

    section_order = [s for s in section_order if isinstance(s, str) and s.strip()]
    if not section_order:
        section_order = list(_DEFAULT_SECTION_ORDER)

    # Build a compact, no-dup payload for suggestions (references are always via [R#] markers).
    groups_payload: dict[str, dict[str, Any]] = {}
    for group in citation_groups:
        if not isinstance(group, dict):
            continue
        gkey = str(group.get("key") or "").strip()
        title = str(group.get("title") or "").strip()
        rids = group.get("rids")
        if not gkey or not title or not isinstance(rids, list):
            continue
        items: list[dict[str, Any]] = []
        seen_rids: set[str] = set()
        for rid in rids:
            if not isinstance(rid, str) or not rid.strip():
                continue
            rid = rid.strip()
            if rid in seen_rids:
                continue
            seen_rids.add(rid)
            ref = references_by_rid.get(rid)
            if not isinstance(ref, dict):
                continue
            items.append(
                {
                    "rid": rid,
                    "in_paper": bool(ref.get("in_paper")),
                    "title": ref.get("title"),
                    "year": ref.get("year"),
                    "venue": ref.get("venue"),
                }
            )
        if items:
            groups_payload[gkey] = {"title": title, "items": items}

    if not groups_payload:
        return {"status": "skipped", "reason": "No reference items available for suggestions."}, calls_used

    # If no budget or disabled, return a heuristic guide.
    if not settings.enable_deep_analysis_llm_suggestions or (llm_budget is not None and llm_budget <= 0):
        overview, sections = _heuristic_suggestions(groups_payload, references_by_rid, section_order)
        return (
            {
                "status": "completed",
                "mode": "heuristic",
                "overview": overview,
                "sections": sections,
            },
            calls_used,
        )

    calls_used += 1
    excerpt = " ".join((paper_excerpt or "").split())
    if len(excerpt) > settings.deep_analysis_paper_excerpt_max_chars:
        excerpt = excerpt[: settings.deep_analysis_paper_excerpt_max_chars] + "\u2026"

    try:
        llm_out = llm_client.chat_json(
            system=get_prompt("deep_analysis/suggestions/system"),
            user=render_prompt(
                "deep_analysis/suggestions/user",
                excerpt=excerpt,
                groups_payload=groups_payload,
                section_order="\n".join(section_order),
            ),
        )
    except Exception as e:
        overview, sections = _heuristic_suggestions(groups_payload, references_by_rid, section_order)
        note = str(e).strip()
        if len(note) > 240:
            note = note[:240] + "\u2026"
        return (
            {
                "status": "completed",
                "mode": "heuristic",
                "overview": overview,
                "sections": sections,
                "note": f"LLM suggestions failed ({note}); used a fallback.",
            },
            calls_used,
        )

    if not isinstance(llm_out, dict):
        overview, sections = _heuristic_suggestions(groups_payload, references_by_rid, section_order)
        return (
            {
                "status": "completed",
                "mode": "heuristic",
                "overview": overview,
                "sections": sections,
                "note": "LLM suggestion output was invalid; used a fallback.",
            },
            calls_used,
        )

    overview = llm_out.get("overview")
    sections = llm_out.get("sections")
    if not isinstance(overview, str) or not isinstance(sections, list):
        h_overview, h_sections = _heuristic_suggestions(groups_payload, references_by_rid, section_order)
        return (
            {
                "status": "completed",
                "mode": "heuristic",
                "overview": h_overview,
                "sections": h_sections,
                "note": "LLM suggestion output had an unexpected shape; used a fallback.",
            },
            calls_used,
        )

    index_by_title = {s.lower(): idx for idx, s in enumerate(section_order)}
    def _section_sort_key(item: dict[str, Any]) -> tuple[int, str]:
        title = str(item.get("title") or "").strip()
        key = title.lower()
        if key in index_by_title:
            return (index_by_title[key], "")
        return (len(section_order) + 1, key)

    try:
        sections = sorted(
            [s for s in sections if isinstance(s, dict) and isinstance(s.get("title"), str)],
            key=_section_sort_key,
        )
    except Exception:
        # Keep LLM order if sorting fails.
        pass

    return (
        {
            "status": "completed",
            "mode": "llm",
            "overview": overview,
            "sections": sections,
            "groups_used": list(groups_payload.keys()),
        },
        calls_used,
    )


def _heuristic_suggestions(
    groups_payload: dict[str, dict[str, Any]],
    references_by_rid: dict[str, dict],
    section_order: list[str],
) -> tuple[str, list[dict]]:
    section_order = [s for s in section_order if isinstance(s, str) and s.strip()]
    if not section_order:
        section_order = list(_DEFAULT_SECTION_ORDER)

    def _last_name(author: str) -> str:
        cleaned = " ".join((author or "").split()).strip()
        if not cleaned:
            return "Unknown"
        if "," in cleaned:
            return cleaned.split(",", 1)[0].strip() or "Unknown"
        return cleaned.split()[-1] if cleaned.split() else "Unknown"

    def _apa_in_text(meta: dict[str, Any]) -> str:
        authors = meta.get("authors") if isinstance(meta.get("authors"), list) else []
        year = meta.get("year")
        year_str = str(year) if isinstance(year, int) and year > 0 else "n.d."
        names = [_last_name(a) for a in authors if isinstance(a, str) and a.strip()]
        if not names:
            return f"(Unknown, {year_str})"
        if len(names) == 1:
            return f"({names[0]}, {year_str})"
        if len(names) == 2:
            return f"({names[0]} & {names[1]}, {year_str})"
        return f"({names[0]} et al., {year_str})"

    section_prefs = {
        "highly_connected": ["Introduction", "Literature Review", "Background"],
        "core_papers": ["Literature Review", "Background", "Introduction"],
        "bibliographic_coupling": ["Literature Review", "Methods", "Discussion"],
        "bridge_papers": ["Methods", "Results", "Discussion"],
        "tangential_citations": ["Discussion", "Conclusion", "Limitations"],
    }

    def _pick_section(key: str) -> str:
        prefs = section_prefs.get(key, [])
        for sec in section_order:
            if sec in prefs:
                return sec
        return section_order[0]

    def _bullet_for(
        rid: str,
        *,
        section_title: str,
        group_label: str,
        action_add: str,
        action_strengthen: str,
    ) -> str:
        ref = references_by_rid.get(rid) if isinstance(references_by_rid.get(rid), dict) else {}
        in_paper = bool(ref.get("in_paper"))
        action = action_strengthen if in_paper else action_add
        priority = "High" if not in_paper else "Low"
        cite = _apa_in_text(ref)
        return f"[{rid}] {group_label} (Priority: {priority}) - In {section_title}, {action} {cite}"

    def _overview_sentence(priority: int, rid: str, section_title: str, action: str) -> str:
        ref = references_by_rid.get(rid) if isinstance(references_by_rid.get(rid), dict) else {}
        cite = _apa_in_text(ref)
        pr_label = "High" if not ref.get("in_paper") else "Low"
        return f"Priority {priority} ({pr_label}): In {section_title}, {action} {cite} [{rid}]."

    overview_sentences: list[str] = []
    priority_order = ["highly_connected", "core_papers", "bridge_papers", "tangential_citations", "bibliographic_coupling"]
    priority = 1
    for key in priority_order:
        group = groups_payload.get(key)
        items = group.get("items") if isinstance(group, dict) else None
        if not isinstance(items, list) or not items:
            continue
        picked = None
        for item in items:
            if not isinstance(item, dict):
                continue
            if not item.get("in_paper"):
                picked = item
                break
        if picked is None:
            picked = items[0] if isinstance(items[0], dict) else None
        if not isinstance(picked, dict):
            continue
        rid = str(picked.get("rid") or "").strip()
        if not rid:
            continue
        section_title = _pick_section(key)
        if key == "tangential_citations":
            action = "justify or remove the citation so it directly supports the claim."
        elif key == "bridge_papers":
            action = "use this to connect subtopics and clarify the transition."
        elif key == "core_papers":
            action = "add a 1-2 sentence summary of how your work builds on it."
        elif key == "bibliographic_coupling":
            action = "clarify how its framing aligns or contrasts with your approach."
        else:
            action = "strengthen the rationale for citing this work."
        overview_sentences.append(_overview_sentence(priority, rid, section_title, action))
        priority += 1
        if priority > 3:
            break

    overview = (
        " ".join(overview_sentences)
        if overview_sentences
        else "No major deep-analysis priorities were generated for this run."
    )

    section_buckets: dict[str, list[str]] = {title: [] for title in section_order}
    group_plan = [
        ("core_papers", "Core background refs"),
        ("bridge_papers", "Refs connecting ideas"),
        ("highly_connected", "Refs to add"),
        ("bibliographic_coupling", "Refs to add"),
        ("tangential_citations", "Refs to consider removing"),
    ]

    for key, label in group_plan:
        group = groups_payload.get(key)
        if not isinstance(group, dict):
            continue
        items = group.get("items")
        if not isinstance(items, list) or not items:
            continue
        try:
            items = sorted(items, key=lambda item: bool(item.get("in_paper")) if isinstance(item, dict) else True)
        except Exception:
            pass
        section_title = _pick_section(key)
        bullets: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("rid") or "").strip()
            if not rid:
                continue
            if key == "tangential_citations":
                bullets.append(
                    _bullet_for(
                        rid,
                        section_title=section_title,
                        group_label=label,
                        action_add="add one sentence explaining why it supports your specific claim (or remove it).",
                        action_strengthen="add one sentence explaining why it supports your specific claim, or remove it if it's not doing real work for the argument.",
                    )
                )
            elif key == "bridge_papers":
                bullets.append(
                    _bullet_for(
                        rid,
                        section_title=section_title,
                        group_label=label,
                        action_add="use it to connect subtopics and clarify the transition you are making (explain how it links them).",
                        action_strengthen="use it to make the transition between subtopics more explicit (explain the link).",
                    )
                )
            elif key == "core_papers":
                bullets.append(
                    _bullet_for(
                        rid,
                        section_title=section_title,
                        group_label=label,
                        action_add="add a 1-2 sentence summary of what it contributes that your paper builds on.",
                        action_strengthen="add a clearer 1-2 sentence summary of what it contributes and how your paper builds on it.",
                    )
                )
            elif key == "bibliographic_coupling":
                bullets.append(
                    _bullet_for(
                        rid,
                        section_title=section_title,
                        group_label=label,
                        action_add="situate your work alongside it and clarify the overlap in framing or evidence.",
                        action_strengthen="add one sentence clarifying how its framing compares to yours.",
                    )
                )
            else:  # highly_connected
                bullets.append(
                    _bullet_for(
                        rid,
                        section_title=section_title,
                        group_label=label,
                        action_add="add it where you motivate the problem, justify the method, or discuss prior evidence.",
                        action_strengthen="strengthen the surrounding sentence so the reason for citing it is explicit.",
                    )
                )
        if bullets:
            section_buckets[section_title].extend(bullets)

    sections = [{"title": title, "bullets": bullets} for title, bullets in section_buckets.items() if bullets]

    if not sections:
        sections.append({"title": "No strong recommendations", "bullets": ["No deep suggestions were generated for this run."]})

    return overview, sections

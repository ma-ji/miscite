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
_RID_RE = re.compile(r"R\d{1,4}", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


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
            rid_norm = _normalize_rid(rid)
            if not rid_norm or rid_norm in seen_rids:
                continue
            seen_rids.add(rid_norm)
            ref = references_by_rid.get(rid_norm)
            if not isinstance(ref, dict):
                continue
            items.append(
                {
                    "rid": rid_norm,
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

    section_anchors = _build_section_anchor_map(paper_excerpt, section_order)
    default_anchor = _extract_first_sentence(paper_excerpt)

    if not settings.enable_deep_analysis_llm_suggestions or (llm_budget is not None and llm_budget <= 0):
        overview, items = _heuristic_suggestions(
            groups_payload=groups_payload,
            references_by_rid=references_by_rid,
            section_order=section_order,
            section_anchors=section_anchors,
            default_anchor=default_anchor,
        )
        return (
            {
                "status": "completed",
                "mode": "heuristic",
                "overview": overview,
                "items": items,
            },
            calls_used,
        )

    calls_used += 1
    excerpt = " ".join((paper_excerpt or "").split())
    if len(excerpt) > settings.deep_analysis_paper_excerpt_max_chars:
        excerpt = excerpt[: settings.deep_analysis_paper_excerpt_max_chars] + "..."

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
        overview, items = _heuristic_suggestions(
            groups_payload=groups_payload,
            references_by_rid=references_by_rid,
            section_order=section_order,
            section_anchors=section_anchors,
            default_anchor=default_anchor,
        )
        note = str(e).strip()
        if len(note) > 240:
            note = note[:240] + "..."
        return (
            {
                "status": "completed",
                "mode": "heuristic",
                "overview": overview,
                "items": items,
                "note": f"Suggestion generation failed ({note}); used a fallback.",
            },
            calls_used,
        )

    validated = _validate_llm_suggestions(
        llm_out,
        allowed_rids=set(references_by_rid.keys()),
        allowed_sections=set(section_order),
        excerpt=excerpt,
        section_anchors=section_anchors,
        default_anchor=default_anchor,
    )
    if not validated:
        overview, items = _heuristic_suggestions(
            groups_payload=groups_payload,
            references_by_rid=references_by_rid,
            section_order=section_order,
            section_anchors=section_anchors,
            default_anchor=default_anchor,
        )
        return (
            {
                "status": "completed",
                "mode": "heuristic",
                "overview": overview,
                "items": items,
                "note": "Suggestion output had an unexpected shape; used a fallback.",
            },
            calls_used,
        )

    by_order = {title: idx for idx, title in enumerate(section_order)}
    items = sorted(
        validated["items"],
        key=lambda item: (
            by_order.get(str(item.get("section_title") or "").strip(), len(section_order) + 1),
            str(item.get("action_type") or ""),
            str(item.get("rid") or ""),
        ),
    )

    return (
        {
            "status": "completed",
            "mode": "llm",
            "overview": validated["overview"],
            "items": items,
            "groups_used": list(groups_payload.keys()),
        },
        calls_used,
    )


def _heuristic_suggestions(
    *,
    groups_payload: dict[str, dict[str, Any]],
    references_by_rid: dict[str, dict],
    section_order: list[str],
    section_anchors: dict[str, str],
    default_anchor: str,
) -> tuple[str, list[dict[str, Any]]]:
    section_order = [s for s in section_order if isinstance(s, str) and s.strip()]
    if not section_order:
        section_order = list(_DEFAULT_SECTION_ORDER)

    section_prefs = {
        "highly_connected": ["Introduction", "Literature Review", "Background", "Discussion"],
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

    def _priority_label(group_key: str, in_paper: bool) -> str:
        if group_key == "tangential_citations":
            return "high"
        return "low" if in_paper else "high"

    def _action_for(group_key: str, in_paper: bool) -> tuple[str, str, str]:
        if group_key == "tangential_citations":
            return (
                "reconsider",
                "Reconsider this citation and justify it explicitly in the surrounding sentence.",
                "This citation currently appears weakly connected to the claim and needs a clear rationale.",
            )
        if group_key == "bridge_papers":
            return (
                "strengthen" if in_paper else "add",
                "Use this work to make the transition between ideas explicit.",
                "Bridging evidence helps readers follow how concepts connect across sections.",
            )
        if group_key == "core_papers":
            return (
                "strengthen" if in_paper else "add",
                "State how this core work frames the problem and how your manuscript builds on it.",
                "Core references establish field context and strengthen the contribution claim.",
            )
        if group_key == "bibliographic_coupling":
            return (
                "add" if not in_paper else "strengthen",
                "Compare this work's framing with your own and explain overlap or contrast.",
                "This helps position your manuscript within adjacent literature using similar evidence bases.",
            )
        return (
            "add" if not in_paper else "strengthen",
            "Integrate this reference where you motivate the claim or justify the method.",
            "This reference can directly support a central claim in the section.",
        )

    items: list[dict[str, Any]] = []
    overview_bits: list[str] = []

    ordered_group_keys = [
        "highly_connected",
        "core_papers",
        "bridge_papers",
        "bibliographic_coupling",
        "tangential_citations",
    ]

    for group_key in ordered_group_keys:
        group = groups_payload.get(group_key)
        if not isinstance(group, dict):
            continue
        rows = group.get("items")
        if not isinstance(rows, list) or not rows:
            continue
        section_title = _pick_section(group_key)
        anchor = section_anchors.get(section_title) or default_anchor
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            rid = _normalize_rid(row.get("rid"))
            if not rid:
                continue
            ref = references_by_rid.get(rid) if isinstance(references_by_rid.get(rid), dict) else {}
            in_paper = bool(ref.get("in_paper"))
            action_type, action, why = _action_for(group_key, in_paper)
            priority = _priority_label(group_key, in_paper)
            items.append(
                {
                    "section_title": section_title,
                    "action_type": action_type,
                    "rid": rid,
                    "priority": priority,
                    "action": action,
                    "why": why,
                    "where": "Immediately after the sentence that makes the related claim.",
                    "anchor_quote": anchor,
                }
            )
            if idx == 0 and len(overview_bits) < 3:
                overview_bits.append(
                    f"Priority {len(overview_bits) + 1}: In {section_title}, {action} [{rid}]."
                )

    overview = (
        " ".join(overview_bits)
        if overview_bits
        else "No major deep-analysis priorities were generated for this run."
    )

    return overview, items


def _validate_llm_suggestions(
    payload: Any,
    *,
    allowed_rids: set[str],
    allowed_sections: set[str],
    excerpt: str,
    section_anchors: dict[str, str],
    default_anchor: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    overview = payload.get("overview")
    items = payload.get("items")
    if not isinstance(overview, str) or not isinstance(items, list):
        return None

    cleaned_items: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        section_title = _clean_text(item.get("section_title"))
        if not section_title:
            continue
        if allowed_sections and section_title not in allowed_sections:
            continue
        action_type = _clean_text(item.get("action_type")).lower()
        if action_type not in {"add", "strengthen", "justify", "reconsider"}:
            continue
        rid = _normalize_rid(item.get("rid"))
        if not rid:
            continue
        if allowed_rids and rid not in allowed_rids:
            continue
        priority = _clean_text(item.get("priority")).lower()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        action = _clean_text(item.get("action"))
        why = _clean_text(item.get("why"))
        where = _clean_text(item.get("where"))
        if not action or not why or not where:
            continue
        anchor = _normalize_anchor_quote(
            item.get("anchor_quote"),
            excerpt=excerpt,
            fallback=section_anchors.get(section_title) or default_anchor,
        )
        cleaned_items.append(
            {
                "section_title": section_title,
                "action_type": action_type,
                "rid": rid,
                "priority": priority,
                "action": action,
                "why": why,
                "where": where,
                "anchor_quote": anchor,
            }
        )

    if not cleaned_items:
        return None

    return {
        "overview": _clean_text(overview),
        "items": cleaned_items,
    }


def _build_section_anchor_map(text: str, section_order: list[str]) -> dict[str, str]:
    raw = str(text or "")
    lower = raw.lower()
    out: dict[str, str] = {}
    fallback = _extract_first_sentence(raw)
    for section in section_order:
        section_clean = _clean_text(section)
        if not section_clean:
            continue
        idx = lower.find(section_clean.lower())
        if idx < 0:
            out[section_clean] = fallback
            continue
        snippet = raw[idx : idx + 800]
        anchor = _extract_first_sentence(snippet) or fallback
        out[section_clean] = anchor
    return out


def _normalize_anchor_quote(value: Any, *, excerpt: str, fallback: str) -> str:
    quote = _clean_text(value)
    if quote and quote.lower() in excerpt.lower():
        return quote
    return fallback


def _extract_first_sentence(text: str) -> str:
    cleaned = _clean_text(text)
    if not cleaned:
        return ""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(cleaned) if p.strip()]
    if not parts:
        return ""
    sentence = parts[0]
    if len(sentence) > 180:
        sentence = sentence[:177].rstrip() + "..."
    return sentence


def _normalize_rid(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().upper()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1].strip()
    match = _RID_RE.search(text)
    if not match:
        return ""
    return match.group(0).upper()


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\u00a0", " ").split()).strip()

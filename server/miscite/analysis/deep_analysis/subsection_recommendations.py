from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from server.miscite.analysis.deep_analysis.subsections import Subsection
from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.prompts import get_prompt, render_prompt


_RID_RE = re.compile(r"R\d{1,4}", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def build_subsection_recommendations(
    *,
    settings: Settings,
    llm_client: OpenRouterClient,
    subsections: list[Subsection],
    subsection_graphs: list[dict],
    references_by_rid: dict[str, dict],
    rid_by_node_id: dict[str, str],
    llm_budget: int | None,
) -> tuple[dict, int]:
    if not subsections:
        return {"status": "skipped", "reason": "No sections available."}, 0

    subsection_by_id = {s.subsection_id: s for s in subsections}
    graph_by_id: dict[str, dict] = {}
    for graph in subsection_graphs or []:
        if not isinstance(graph, dict):
            continue
        sid = str(graph.get("subsection_id") or "").strip()
        if not sid or sid not in subsection_by_id or sid in graph_by_id:
            continue
        graph_by_id[sid] = graph

    items: list[dict[str, Any]] = []
    for subsection in subsections:
        sid = subsection.subsection_id
        graph = graph_by_id.get(sid)

        node_distances = (
            graph.get("node_distances")
            if isinstance(graph, dict) and isinstance(graph.get("node_distances"), dict)
            else {}
        )
        dist_by_rid: dict[str, int] = {}
        for node_id, dist in node_distances.items():
            if not isinstance(node_id, str):
                continue
            rid = rid_by_node_id.get(node_id)
            if not rid:
                continue
            try:
                d = int(dist)
            except Exception:
                continue
            prev = dist_by_rid.get(rid)
            dist_by_rid[rid] = d if prev is None else min(prev, d)

        ref_items: list[dict[str, Any]] = []
        for rid, distance in dist_by_rid.items():
            ref = references_by_rid.get(rid)
            if not isinstance(ref, dict):
                continue
            ref_items.append(
                {
                    "rid": rid,
                    "distance": distance,
                    "in_paper": bool(ref.get("in_paper")),
                    "cited_in_subsection": distance == 0,
                    "title": ref.get("title"),
                    "year": ref.get("year"),
                    "venue": ref.get("venue"),
                    "authors": ref.get("authors"),
                    "abstract": ref.get("abstract"),
                }
            )

        ref_items = _select_refs_for_prompt(
            ref_items,
            max_refs=max(10, int(settings.deep_analysis_subsection_prompt_max_refs)),
        )
        seed_count = sum(1 for rid, d in dist_by_rid.items() if d == 0 and rid)

        items.append(
            {
                "subsection_id": sid,
                "title": subsection.title,
                "level": subsection.level,
                "prompt_references": ref_items,
                "plan": None,
                "plan_mode": "skipped",
                "_seed_count": seed_count,
                "_node_count": len(dist_by_rid),
            }
        )

    if not items:
        return {"status": "skipped", "reason": "No usable sections were found."}, 0

    llm_enabled = bool(settings.enable_deep_analysis_llm_subsection_recommendations)
    remaining = None if llm_budget is None else max(0, int(llm_budget))
    max_calls = len(items) if remaining is None else min(len(items), remaining)

    calls_used = 0
    if llm_enabled and max_calls > 0:
        order_by_sid = {s.subsection_id: idx for idx, s in enumerate(subsections)}

        def _call_priority(item: dict[str, Any]) -> tuple[int, int, int]:
            sid = str(item.get("subsection_id") or "")
            order = int(order_by_sid.get(sid, 1_000_000))
            return (
                -int(item.get("_seed_count") or 0),
                -int(item.get("_node_count") or 0),
                order,
            )

        to_call = sorted(items, key=_call_priority)[:max_calls]
        calls_used = len(to_call)
        max_workers = min(max(1, int(settings.deep_analysis_max_workers)), len(to_call))

        def _call(item: dict[str, Any]) -> dict | None:
            sid = str(item.get("subsection_id") or "")
            section = subsection_by_id.get(sid)
            if not section:
                return None
            title = str(item.get("title") or "").strip()
            section_text_full = str(section.text or "")
            text_for_prompt = " ".join(section_text_full.split())
            if len(text_for_prompt) > int(settings.deep_analysis_subsection_text_max_chars):
                text_for_prompt = text_for_prompt[: int(settings.deep_analysis_subsection_text_max_chars)] + "..."

            refs_json = json.dumps(item.get("prompt_references") or [], ensure_ascii=False)
            payload = llm_client.chat_json(
                system=get_prompt("deep_analysis/subsection_plan/system"),
                user=render_prompt(
                    "deep_analysis/subsection_plan/user",
                    title=title,
                    text=text_for_prompt,
                    references_json=refs_json,
                ),
            )
            prompt_refs = item.get("prompt_references") or []
            allowed = {
                r.get("rid")
                for r in prompt_refs
                if isinstance(r, dict) and isinstance(r.get("rid"), str)
            }
            allowed_integrations = {
                r.get("rid")
                for r in prompt_refs
                if isinstance(r, dict)
                and isinstance(r.get("rid"), str)
                and (not bool(r.get("cited_in_subsection")))
                and int(r.get("distance") or 99) > 0
            }
            return _validate_plan(
                payload,
                allowed_rids=allowed,
                allowed_integration_rids=allowed_integrations,
                section_text=section_text_full,
            )

        plans: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_call, item): str(item.get("subsection_id") or "") for item in to_call}
            for fut in as_completed(futures):
                sid = futures[fut]
                try:
                    out = fut.result()
                except Exception as e:
                    out = None
                    fallback_anchor = ""
                    if sid in subsection_by_id:
                        candidates = _extract_anchor_candidates(str(subsection_by_id.get(sid).text or ""))
                        fallback_anchor = candidates[0] if candidates else ""
                    plans[sid] = {
                        "summary": "This section plan failed to generate and should be reviewed manually.",
                        "improvements": [],
                        "reference_integrations": [],
                        "questions": [str(e)[:200]],
                        "anchor_quote": fallback_anchor,
                    }
                if out:
                    plans[sid] = out

        for item in items:
            sid = str(item.get("subsection_id") or "")
            if sid in plans:
                item["plan"] = plans[sid]
                item["plan_mode"] = "llm"

    for item in items:
        if item.get("plan") is not None:
            continue
        sid = str(item.get("subsection_id") or "")
        section_text = str(subsection_by_id.get(sid).text or "") if sid in subsection_by_id else ""
        item["plan"] = _heuristic_plan(item.get("prompt_references") or [], section_text=section_text)
        item["plan_mode"] = "heuristic"

    for item in items:
        item.pop("prompt_references", None)
        item.pop("_seed_count", None)
        item.pop("_node_count", None)

    note = None
    if not llm_enabled:
        note = "Used heuristic section plans because LLM section planning is disabled."
    elif remaining is not None and remaining <= 0:
        note = "Used heuristic section plans because the call budget was exhausted."
    elif remaining is not None and remaining < len(items):
        note = "Used a mix of LLM and heuristic section plans due to call budget limits."

    return (
        {
            "status": "completed",
            "items": items,
            "note": note,
        },
        calls_used,
    )


def _select_refs_for_prompt(ref_items: list[dict[str, Any]], *, max_refs: int) -> list[dict[str, Any]]:
    def _year(item: dict[str, Any]) -> int:
        y = item.get("year")
        return int(y) if isinstance(y, int) else 0

    seeds = [r for r in ref_items if int(r.get("distance") or 99) == 0]
    in_paper_neighbors = [
        r
        for r in ref_items
        if bool(r.get("in_paper")) and int(r.get("distance") or 99) > 0
    ]
    new_neighbors = [
        r
        for r in ref_items
        if (not bool(r.get("in_paper"))) and int(r.get("distance") or 99) > 0
    ]

    seeds = sorted(seeds, key=lambda r: str(r.get("rid") or ""))
    in_paper_neighbors = sorted(
        in_paper_neighbors,
        key=lambda r: (
            int(r.get("distance") or 99),
            -_year(r),
            str(r.get("rid") or ""),
        ),
    )
    new_neighbors = sorted(
        new_neighbors,
        key=lambda r: (
            int(r.get("distance") or 99),
            -_year(r),
            str(r.get("rid") or ""),
        ),
    )

    ordered = seeds + in_paper_neighbors + new_neighbors
    if len(ordered) <= max_refs:
        return ordered
    if len(seeds) >= max_refs:
        return seeds[:max_refs]
    return ordered[:max_refs]


def _validate_plan(
    plan: Any,
    *,
    allowed_rids: set[str],
    allowed_integration_rids: set[str],
    section_text: str,
) -> dict[str, Any] | None:
    if not isinstance(plan, dict):
        return None
    summary = plan.get("summary")
    improvements = plan.get("improvements")
    integrations = plan.get("reference_integrations")
    questions = plan.get("questions")
    if (
        not isinstance(summary, str)
        or not isinstance(improvements, list)
        or not isinstance(integrations, list)
        or not isinstance(questions, list)
    ):
        return None

    anchor_candidates = _extract_anchor_candidates(section_text)
    default_anchor = anchor_candidates[0] if anchor_candidates else ""

    def _norm_rid(value: str) -> str | None:
        text = (value or "").strip()
        if not text:
            return None
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1].strip()
        m = _RID_RE.search(text)
        if not m:
            return None
        return m.group(0).upper()

    def _clean_rids(val: Any) -> list[str]:
        if not isinstance(val, list):
            return []
        out: list[str] = []
        seen: set[str] = set()
        for rid in val:
            if not isinstance(rid, str):
                continue
            rid_norm = _norm_rid(rid)
            if not rid_norm:
                continue
            if rid_norm in seen:
                continue
            if allowed_rids and rid_norm not in allowed_rids:
                continue
            seen.add(rid_norm)
            out.append(rid_norm)
        return out

    cleaned_improvements: list[dict[str, Any]] = []
    for item in improvements:
        if not isinstance(item, dict):
            continue
        try:
            priority = int(item.get("priority"))
        except Exception:
            continue
        action = _clean_text(item.get("action"))
        why = _clean_text(item.get("why"))
        where = _clean_text(item.get("where"))
        rids = _clean_rids(item.get("rids"))
        action_type = _clean_text(item.get("action_type")).lower()
        if action_type not in {"add", "strengthen", "justify", "reconsider"}:
            action_type = "strengthen"
        if not action or not why or not where:
            continue
        cleaned_improvements.append(
            {
                "priority": max(1, priority),
                "action_type": action_type,
                "action": action,
                "why": why,
                "where": where,
                "anchor_quote": _normalize_anchor_quote(
                    item.get("anchor_quote"),
                    section_text=section_text,
                    fallback=default_anchor,
                ),
                "rids": rids,
            }
        )
    cleaned_improvements.sort(key=lambda x: int(x.get("priority") or 999))

    cleaned_integrations: list[dict[str, Any]] = []
    for item in integrations:
        if not isinstance(item, dict):
            continue
        rid = _norm_rid(str(item.get("rid") or ""))
        if not rid:
            continue
        if allowed_rids and rid not in allowed_rids:
            continue
        if allowed_integration_rids and rid not in allowed_integration_rids:
            continue
        priority = _clean_text(item.get("priority")).lower()
        if priority not in {"high", "medium", "low"}:
            priority = "medium"
        action_type = _clean_text(item.get("action_type")).lower()
        if action_type not in {"add", "strengthen", "justify", "reconsider"}:
            action_type = "add"
        action = _clean_text(item.get("action")) or "Integrate this reference where the claim is introduced."
        why = _clean_text(item.get("why"))
        where = _clean_text(item.get("where"))
        example = _clean_text(item.get("example"))
        if not why or not where or not example:
            continue
        cleaned_integrations.append(
            {
                "rid": rid,
                "priority": priority,
                "action_type": action_type,
                "action": action,
                "why": why,
                "where": where,
                "anchor_quote": _normalize_anchor_quote(
                    item.get("anchor_quote"),
                    section_text=section_text,
                    fallback=default_anchor,
                ),
                "example": example,
            }
        )

    cleaned_questions = [
        _clean_text(q) for q in questions if isinstance(q, str) and _clean_text(q)
    ]

    return {
        "summary": _clean_text(summary),
        "improvements": cleaned_improvements,
        "reference_integrations": cleaned_integrations,
        "questions": cleaned_questions,
        "anchor_quote": default_anchor,
    }


def _heuristic_plan(ref_items: list[dict[str, Any]], *, section_text: str) -> dict[str, Any]:
    anchors = _extract_anchor_candidates(section_text)
    primary_anchor = anchors[0] if anchors else ""
    secondary_anchor = anchors[1] if len(anchors) > 1 else primary_anchor

    uncited = [
        row
        for row in ref_items
        if isinstance(row, dict)
        and (not bool(row.get("cited_in_subsection")))
        and int(row.get("distance") or 99) > 0
    ]
    try:
        uncited = sorted(
            uncited,
            key=lambda row: (
                0 if bool(row.get("in_paper")) else 1,
                int(row.get("distance") or 99),
                str(row.get("rid") or ""),
            ),
        )
    except Exception:
        pass
    top = [str(row.get("rid") or "").strip() for row in uncited[:8] if str(row.get("rid") or "").strip()]

    improvements = [
        {
            "priority": 1,
            "action_type": "strengthen",
            "action": "Clarify the section's main claim in one direct sentence.",
            "why": "Readers need the central claim to be explicit before evaluating the evidence.",
            "where": "At the first sentence that states the section's goal.",
            "anchor_quote": primary_anchor,
            "rids": [],
        },
        {
            "priority": 2,
            "action_type": "justify",
            "action": "Add one sentence explaining why each major citation supports the claim.",
            "why": "Explicit rationale prevents citation dumping and improves traceability.",
            "where": "Immediately after the sentence introducing each major citation.",
            "anchor_quote": secondary_anchor,
            "rids": [],
        },
    ]

    integrations: list[dict[str, Any]] = []
    for idx, rid in enumerate(top):
        anchor = anchors[idx % len(anchors)] if anchors else primary_anchor
        integrations.append(
            {
                "rid": rid,
                "priority": "medium",
                "action_type": "add",
                "action": "Integrate this reference to support the nearby claim.",
                "why": "This work can strengthen local support for the argument in this section.",
                "where": "After the sentence that introduces the related concept.",
                "anchor_quote": anchor,
                "example": f"This claim is also supported by related findings [{rid}].",
            }
        )

    questions = [
        "Which sentence in this section carries the core claim, and is it explicit enough?",
        "Where does the argument need one additional citation to avoid overgeneralizing?",
    ]

    return {
        "summary": "Tighten the core claim, then make each citation's contribution explicit where it appears in the section.",
        "improvements": improvements,
        "reference_integrations": integrations,
        "questions": questions,
        "anchor_quote": primary_anchor,
    }


def _normalize_anchor_quote(value: Any, *, section_text: str, fallback: str) -> str:
    quote = _clean_text(value)
    if quote and quote.lower() in section_text.lower():
        return quote
    return fallback


def _extract_anchor_candidates(section_text: str) -> list[str]:
    text = _clean_text(section_text)
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    out: list[str] = []
    for sentence in parts:
        if len(sentence) < 30:
            continue
        if len(sentence) > 220:
            sentence = sentence[:217].rstrip() + "..."
        out.append(sentence)
        if len(out) >= 5:
            break
    return out


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\u00a0", " ").split()).strip()

from __future__ import annotations

from typing import Any


_ACTION_WEIGHTS: dict[str, int] = {
    "reconsider": 95,
    "justify": 90,
    "add": 85,
    "strengthen": 80,
}


def build_recommendations(
    *,
    suggestions: dict[str, Any],
    subsection_recommendations: dict[str, Any],
    references_by_rid: dict[str, dict[str, Any]],
    max_global_actions: int = 5,
    max_actions_per_section: int = 3,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    notes: list[str] = []
    section_order: list[str] = []

    if isinstance(subsection_recommendations, dict):
        note = _clean_text(subsection_recommendations.get("note"))
        if note:
            notes.append(note)
        candidates.extend(_candidates_from_subsection_plans(subsection_recommendations))
        if _clean_text(subsection_recommendations.get("status")).lower() == "completed":
            raw_items = subsection_recommendations.get("items")
            if isinstance(raw_items, list):
                for row in raw_items:
                    if not isinstance(row, dict):
                        continue
                    section_title = _clean_text(row.get("title"))
                    if section_title and section_title not in section_order:
                        section_order.append(section_title)
    if isinstance(suggestions, dict):
        note = _clean_text(suggestions.get("note"))
        if note:
            notes.append(note)
        candidates.extend(_candidates_from_suggestions(suggestions))
        if _clean_text(suggestions.get("status")).lower() == "completed":
            raw_items = suggestions.get("items")
            if isinstance(raw_items, list):
                for row in raw_items:
                    if not isinstance(row, dict):
                        continue
                    section_title = _clean_text(row.get("section_title"))
                    if section_title and section_title not in section_order:
                        section_order.append(section_title)

    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...], str]] = set()
    for cand in candidates:
        normalized = _normalize_candidate(cand)
        if not normalized:
            continue
        key = (
            normalized["section_title"].lower(),
            normalized["action_type"],
            tuple(sorted(normalized["rids"])),
            normalized["action"].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(normalized)

    if not cleaned:
        return {
            "status": "skipped",
            "reason": "No recommendations were generated for this run.",
        }

    for cand in cleaned:
        cand["_score"] = _score_candidate(cand, references_by_rid=references_by_rid)

    cleaned.sort(
        key=lambda c: (
            -int(c.get("_score") or 0),
            c.get("section_title", "").lower(),
            c.get("action", "").lower(),
        )
    )

    max_global_actions = max(1, int(max_global_actions))
    max_actions_per_section = max(1, int(max_actions_per_section))

    global_actions = [_public_action(a) for a in cleaned[:max_global_actions]]

    section_buckets: dict[str, list[dict[str, Any]]] = {}
    for cand in cleaned:
        section_title = cand["section_title"]
        bucket = section_buckets.setdefault(section_title, [])
        if len(bucket) >= max_actions_per_section:
            continue
        bucket.append(_public_action(cand))

    sections = [
        {"title": title, "actions": actions}
        for title, actions in sorted(
            section_buckets.items(),
            key=lambda kv: (
                section_order.index(kv[0]) if kv[0] in section_order else len(section_order) + 1,
                kv[0].lower(),
            ),
        )
        if actions
    ]

    overview = _clean_text(suggestions.get("overview") if isinstance(suggestions, dict) else "")
    if not overview:
        overview = _build_default_overview(global_actions)

    return {
        "status": "completed",
        "overview": overview,
        "global_actions": global_actions,
        "sections": sections,
        "note": " ".join(dict.fromkeys(notes)) if notes else "",
    }


def _build_default_overview(actions: list[dict[str, Any]]) -> str:
    if not actions:
        return "No recommendations were generated for this run."
    top = actions[0]
    action = top.get("action") or "Review the manuscript claims and citations."
    section_title = top.get("section_title") or "the manuscript"
    return f"Start with {section_title}: {action}"


def _candidates_from_subsection_plans(payload: dict[str, Any]) -> list[dict[str, Any]]:
    status = _clean_text(payload.get("status")).lower()
    if status != "completed":
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        section_title = _clean_text(item.get("title")) or "Section"
        plan = item.get("plan")
        if not isinstance(plan, dict):
            continue
        plan_mode = _clean_text(item.get("plan_mode")).lower() or "unknown"

        improvements = plan.get("improvements")
        if isinstance(improvements, list):
            for imp in improvements:
                if not isinstance(imp, dict):
                    continue
                out.append(
                    {
                        "section_title": section_title,
                        "action_type": _clean_action_type(imp.get("action_type")) or "strengthen",
                        "action": _clean_text(imp.get("action")),
                        "why": _clean_text(imp.get("why")),
                        "where": _clean_text(imp.get("where")),
                        "anchor_quote": _clean_text(imp.get("anchor_quote")),
                        "rids": _clean_rids(imp.get("rids")),
                        "priority_hint": imp.get("priority"),
                        "source": f"section_plan_{plan_mode}",
                    }
                )

        integrations = plan.get("reference_integrations")
        if isinstance(integrations, list):
            for add in integrations:
                if not isinstance(add, dict):
                    continue
                rid = _clean_rids([add.get("rid")])
                out.append(
                    {
                        "section_title": section_title,
                        "action_type": _clean_action_type(add.get("action_type")) or "add",
                        "action": _clean_text(add.get("action")) or "Integrate this reference where the claim is introduced.",
                        "why": _clean_text(add.get("why")),
                        "where": _clean_text(add.get("where")),
                        "anchor_quote": _clean_text(add.get("anchor_quote")),
                        "rids": rid,
                        "priority_hint": add.get("priority"),
                        "source": f"section_plan_{plan_mode}",
                    }
                )
    return out


def _candidates_from_suggestions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    status = _clean_text(payload.get("status")).lower()
    if status != "completed":
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []

    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        section_title = _clean_text(item.get("section_title")) or "Section"
        rid = _clean_rids([item.get("rid")])
        out.append(
            {
                "section_title": section_title,
                "action_type": _clean_action_type(item.get("action_type")),
                "action": _clean_text(item.get("action")),
                "why": _clean_text(item.get("why")),
                "where": _clean_text(item.get("where")),
                "anchor_quote": _clean_text(item.get("anchor_quote")),
                "rids": rid,
                "priority_hint": item.get("priority"),
                "source": "group_suggestion",
            }
        )
    return out


def _normalize_candidate(raw: dict[str, Any]) -> dict[str, Any] | None:
    section_title = _clean_text(raw.get("section_title")) or "Section"
    action_type = _clean_action_type(raw.get("action_type")) or "strengthen"
    action = _clean_text(raw.get("action"))
    why = _clean_text(raw.get("why"))
    where = _clean_text(raw.get("where"))
    anchor_quote = _clean_text(raw.get("anchor_quote"))
    rids = _clean_rids(raw.get("rids"))
    source = _clean_text(raw.get("source")) or "recommendation"

    if not action:
        return None
    if not why:
        why = "This change improves how evidence supports the claim."
    if not where:
        where = "Near the sentence where the claim is made."

    return {
        "section_title": section_title,
        "action_type": action_type,
        "action": action,
        "why": why,
        "where": where,
        "anchor_quote": anchor_quote,
        "rids": rids,
        "priority_hint": raw.get("priority_hint"),
        "source": source,
    }


def _score_candidate(cand: dict[str, Any], *, references_by_rid: dict[str, dict[str, Any]]) -> int:
    action_type = str(cand.get("action_type") or "").lower()
    score = int(_ACTION_WEIGHTS.get(action_type, 75))

    hint = cand.get("priority_hint")
    if isinstance(hint, int):
        score += max(0, 25 - max(1, hint) * 5)
    elif isinstance(hint, str):
        h = hint.strip().lower()
        if h == "high":
            score += 18
        elif h == "medium":
            score += 9

    rids = cand.get("rids") if isinstance(cand.get("rids"), list) else []
    if any(not bool((references_by_rid.get(rid) or {}).get("in_paper")) for rid in rids):
        score += 8

    if cand.get("anchor_quote"):
        score += 6

    source = str(cand.get("source") or "")
    if source.endswith("_llm"):
        score += 2
    return score


def _public_action(cand: dict[str, Any]) -> dict[str, Any]:
    return {
        "section_title": cand.get("section_title"),
        "action_type": cand.get("action_type"),
        "action": cand.get("action"),
        "why": cand.get("why"),
        "where": cand.get("where"),
        "anchor_quote": cand.get("anchor_quote"),
        "rids": cand.get("rids") or [],
    }


def _clean_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.replace("\u00a0", " ").split()).strip()


def _clean_action_type(value: Any) -> str:
    text = _clean_text(value).lower()
    if text in {"add", "strengthen", "justify", "reconsider"}:
        return text
    return ""


def _clean_rids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for rid in value:
        if not isinstance(rid, str):
            continue
        text = rid.strip().upper().replace("[", "").replace("]", "")
        if not text or not text.startswith("R"):
            continue
        if text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out

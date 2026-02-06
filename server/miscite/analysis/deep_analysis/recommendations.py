from __future__ import annotations

import re
from typing import Any


_ACTION_WEIGHTS: dict[str, int] = {
    "reconsider": 95,
    "justify": 90,
    "add": 85,
    "strengthen": 80,
}

_ACTION_PRECEDENCE: dict[str, int] = {
    "reconsider": 4,
    "justify": 3,
    "add": 2,
    "strengthen": 1,
}

_DEFAULT_WHY = "This change improves how evidence supports the claim."
_DEFAULT_WHERE = "Near the sentence where the claim is made."
_WORD_RE = re.compile(r"[a-z0-9]+")
_HIDDEN_SECTION_KEYS = {"opening"}


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
    section_order_keys: list[str] = []
    section_titles_by_key: dict[str, str] = {}

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
                    _remember_section_title(
                        raw_title=row.get("title"),
                        section_order_keys=section_order_keys,
                        section_titles_by_key=section_titles_by_key,
                    )
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
                    _remember_section_title(
                        raw_title=row.get("section_title"),
                        section_order_keys=section_order_keys,
                        section_titles_by_key=section_titles_by_key,
                    )

    cleaned: list[dict[str, Any]] = []
    seen: set[tuple[str, str, tuple[str, ...], str]] = set()
    for cand in candidates:
        normalized = _normalize_candidate(cand, section_titles_by_key=section_titles_by_key)
        if not normalized:
            continue
        if normalized["section_key"] in _HIDDEN_SECTION_KEYS:
            continue
        key = (
            normalized["section_key"],
            normalized["action_type"],
            tuple(sorted(normalized["rids"])),
            normalized["action_key"],
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
            c.get("section_key", ""),
            c.get("action_key", ""),
        )
    )

    merged = _merge_redundant_candidates(cleaned)

    for cand in merged:
        cand["_score"] = _score_candidate(cand, references_by_rid=references_by_rid)

    merged.sort(
        key=lambda c: (
            -int(c.get("_score") or 0),
            c.get("section_key", ""),
            c.get("action_key", ""),
        )
    )

    max_global_actions = max(1, int(max_global_actions))
    max_actions_per_section = max(1, int(max_actions_per_section))

    top_candidates = merged[:max_global_actions]
    global_actions = [_public_action(a) for a in top_candidates]
    top_signatures = {_candidate_identity(c) for c in top_candidates}

    section_buckets: dict[str, list[dict[str, Any]]] = {}
    for cand in merged:
        if _candidate_identity(cand) in top_signatures:
            continue
        section_key = cand["section_key"]
        bucket = section_buckets.setdefault(section_key, [])
        if len(bucket) >= max_actions_per_section:
            continue
        bucket.append(_public_action(cand))

    sections = [
        {
            "title": section_titles_by_key.get(section_key, "Section"),
            "actions": actions,
        }
        for section_key, actions in sorted(
            section_buckets.items(),
            key=lambda kv: (
                (
                    section_order_keys.index(kv[0])
                    if kv[0] in section_order_keys
                    else len(section_order_keys) + 1
                ),
                kv[0],
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


def _remember_section_title(
    *,
    raw_title: Any,
    section_order_keys: list[str],
    section_titles_by_key: dict[str, str],
) -> None:
    title = _clean_section_title(raw_title)
    if not title:
        return
    key = _section_key(title)
    if key in _HIDDEN_SECTION_KEYS:
        return
    if key in section_titles_by_key:
        return
    section_titles_by_key[key] = title
    section_order_keys.append(key)


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
        section_title = _clean_section_title(item.get("title")) or "Section"
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
                        "action": _clean_text(add.get("action"))
                        or "Integrate this reference where the claim is introduced.",
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
        section_title = _clean_section_title(item.get("section_title")) or "Section"
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


def _normalize_candidate(
    raw: dict[str, Any],
    *,
    section_titles_by_key: dict[str, str],
) -> dict[str, Any] | None:
    section_title = _clean_section_title(raw.get("section_title")) or "Section"
    section_key = _section_key(section_title)
    section_title = section_titles_by_key.get(section_key, section_title)
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
        why = _DEFAULT_WHY
    if not where:
        where = _DEFAULT_WHERE

    return {
        "section_title": section_title,
        "section_key": section_key,
        "action_type": action_type,
        "action": action,
        "action_key": _text_key(action),
        "why": why,
        "why_key": _text_key(why),
        "where": where,
        "anchor_quote": anchor_quote,
        "anchor_key": _text_key(anchor_quote),
        "rids": rids,
        "priority_hint": raw.get("priority_hint"),
        "source": source,
    }


def _merge_redundant_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    for cand in candidates:
        merged_into_existing = False
        for existing in merged:
            if _is_redundant(cand, existing):
                _merge_candidate(existing, cand)
                merged_into_existing = True
                break
        if merged_into_existing:
            continue
        merged.append(dict(cand))
    return merged


def _is_redundant(left: dict[str, Any], right: dict[str, Any]) -> bool:
    if left.get("section_key") != right.get("section_key"):
        return False

    left_type = str(left.get("action_type") or "")
    right_type = str(right.get("action_type") or "")
    left_anchor = str(left.get("anchor_key") or "")
    right_anchor = str(right.get("anchor_key") or "")
    left_rids = left.get("rids") if isinstance(left.get("rids"), list) else []
    right_rids = right.get("rids") if isinstance(right.get("rids"), list) else []

    if left_type == right_type:
        if left_anchor and left_anchor == right_anchor:
            return True
        if _rid_overlap(left_rids, right_rids):
            if _text_similarity(left.get("action"), right.get("action")) >= 0.42:
                return True
            if _text_similarity(left.get("why"), right.get("why")) >= 0.38:
                return True
        if left_rids and right_rids and tuple(sorted(left_rids)) == tuple(sorted(right_rids)):
            if not left_anchor or not right_anchor:
                return True
            if _text_similarity(left.get("anchor_quote"), right.get("anchor_quote")) >= 0.45:
                return True
        return False

    if left_anchor and left_anchor == right_anchor:
        if _text_similarity(left.get("action"), right.get("action")) >= 0.8:
            return True
    if _rid_overlap(left_rids, right_rids):
        if _text_similarity(left.get("action"), right.get("action")) >= 0.9:
            return True
    return False


def _merge_candidate(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    target_type = str(target.get("action_type") or "")
    incoming_type = str(incoming.get("action_type") or "")
    target_precedence = int(_ACTION_PRECEDENCE.get(target_type, 0))
    incoming_precedence = int(_ACTION_PRECEDENCE.get(incoming_type, 0))
    incoming_is_stronger = incoming_precedence > target_precedence
    if incoming_is_stronger:
        target["action_type"] = incoming_type
        incoming_action = _clean_text(incoming.get("action"))
        if incoming_action:
            target["action"] = incoming_action

    target["section_title"] = _clean_section_title(target.get("section_title")) or "Section"
    target["section_key"] = _section_key(target.get("section_title"))
    target["rids"] = _clean_rids((target.get("rids") or []) + (incoming.get("rids") or []))
    target["why"] = _prefer_detail_text(
        target_text=target.get("why"),
        incoming_text=incoming.get("why"),
        default_text=_DEFAULT_WHY,
    )
    target["where"] = _prefer_detail_text(
        target_text=target.get("where"),
        incoming_text=incoming.get("where"),
        default_text=_DEFAULT_WHERE,
    )
    target["anchor_quote"] = _prefer_detail_text(
        target_text=target.get("anchor_quote"),
        incoming_text=incoming.get("anchor_quote"),
        default_text="",
    )
    target["priority_hint"] = _better_priority_hint(
        target_hint=target.get("priority_hint"),
        incoming_hint=incoming.get("priority_hint"),
    )
    target["source"] = (
        _clean_text(target.get("source"))
        or _clean_text(incoming.get("source"))
        or "recommendation"
    )
    target["action"] = _clean_text(target.get("action")) or _clean_text(incoming.get("action"))
    target["action_key"] = _text_key(target.get("action"))
    target["why_key"] = _text_key(target.get("why"))
    target["anchor_key"] = _text_key(target.get("anchor_quote"))


def _candidate_identity(cand: dict[str, Any]) -> tuple[str, str, tuple[str, ...], str, str]:
    return (
        str(cand.get("section_key") or ""),
        str(cand.get("action_type") or ""),
        tuple(sorted(_clean_rids(cand.get("rids")))),
        _text_key(cand.get("action")),
        _text_key(cand.get("anchor_quote")),
    )


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
    else:
        score -= 4
    if not rids:
        score -= 6

    source = str(cand.get("source") or "")
    if source.endswith("_llm"):
        score += 2
    if source.endswith("_heuristic") and not rids:
        score -= 3

    where = _clean_text(cand.get("where"))
    if not where or where == _DEFAULT_WHERE:
        score -= 3

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


def _clean_section_title(value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    text = re.sub(r"[*`_]+", "", text)
    text = re.sub(r"^#+\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" \t-:;,.")
    return text


def _section_key(value: Any) -> str:
    text = _clean_section_title(value).lower()
    if not text:
        return "section"
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or "section"


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


def _text_key(value: Any) -> str:
    text = _clean_text(value).lower()
    if not text:
        return ""
    tokens = _WORD_RE.findall(text)
    return " ".join(tokens)


def _token_set(value: Any) -> set[str]:
    key = _text_key(value)
    if not key:
        return set()
    return set(key.split())


def _text_similarity(left: Any, right: Any) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    denom = len(left_tokens | right_tokens)
    if denom == 0:
        return 0.0
    return len(left_tokens & right_tokens) / denom


def _rid_overlap(left: list[str], right: list[str]) -> bool:
    if not left or not right:
        return False
    return bool(set(left) & set(right))


def _prefer_detail_text(*, target_text: Any, incoming_text: Any, default_text: str) -> str:
    target = _clean_text(target_text)
    incoming = _clean_text(incoming_text)
    if not target:
        return incoming
    if not incoming:
        return target
    if default_text and target == default_text and incoming != default_text:
        return incoming
    if default_text and incoming == default_text and target != default_text:
        return target
    if _text_similarity(target, incoming) >= 0.82:
        return target if len(target) >= len(incoming) else incoming
    return incoming if len(incoming) > len(target) else target


def _priority_score(hint: Any) -> int:
    if isinstance(hint, int):
        return max(0, 100 - max(1, hint) * 10)
    if isinstance(hint, str):
        normalized = hint.strip().lower()
        if normalized == "high":
            return 30
        if normalized == "medium":
            return 20
        if normalized == "low":
            return 10
    return 0


def _better_priority_hint(*, target_hint: Any, incoming_hint: Any) -> Any:
    if _priority_score(incoming_hint) > _priority_score(target_hint):
        return incoming_hint
    return target_hint

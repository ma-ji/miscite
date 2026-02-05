from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from server.miscite.analysis.deep_analysis.subsections import Subsection
from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.prompts import get_prompt, render_prompt


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
    for g in subsection_graphs or []:
        if not isinstance(g, dict):
            continue
        sid = str(g.get("subsection_id") or "").strip()
        if not sid or sid not in subsection_by_id or sid in graph_by_id:
            continue
        graph_by_id[sid] = g

    items: list[dict[str, Any]] = []

    # Convert node-based graphs to rid-based (when available), and prepare a bounded reference payload for the LLM.
    for subsection in subsections:
        sid = subsection.subsection_id
        g = graph_by_id.get(sid)

        node_distances = g.get("node_distances") if isinstance(g, dict) and isinstance(g.get("node_distances"), dict) else {}
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
        seed_rids = sorted([rid for rid, d in dist_by_rid.items() if d == 0])
        rids_in_graph = set(dist_by_rid.keys())

        # Convert edges to rid pairs (bounded + de-duped).
        rid_edges: list[list[str]] = []
        seen_edges: set[tuple[str, str]] = set()
        edges = g.get("edges") if isinstance(g, dict) and isinstance(g.get("edges"), list) else []
        for edge in edges:
            if not (isinstance(edge, (list, tuple)) and len(edge) == 2):
                continue
            src, dst = edge
            if not isinstance(src, str) or not isinstance(dst, str):
                continue
            a = rid_by_node_id.get(src)
            b = rid_by_node_id.get(dst)
            if not a or not b or a == b:
                continue
            key = (a, b)
            if key in seen_edges:
                continue
            seen_edges.add(key)
            if a in rids_in_graph and b in rids_in_graph:
                rid_edges.append([a, b])
            if len(rid_edges) >= max(100, int(settings.deep_analysis_subsection_graph_max_edges)):
                break

        # Build a compact reference payload: always include all seed refs, then prioritize uncited nearby works.
        ref_items: list[dict[str, Any]] = []
        for rid, d in dist_by_rid.items():
            ref = references_by_rid.get(rid)
            if not isinstance(ref, dict):
                continue
            ref_items.append(
                {
                    "rid": rid,
                    "distance": d,
                    "in_paper": bool(ref.get("in_paper")),
                    "cited_in_subsection": d == 0,
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

        items.append(
            {
                "subsection_id": sid,
                "title": subsection.title,
                "level": subsection.level,
                "seed_rids": seed_rids,
                "graph": {
                    "hop_limit": 3,
                    "nodes": [
                        {"rid": rid, "distance": int(dist_by_rid[rid]), "in_paper": bool(references_by_rid.get(rid, {}).get("in_paper"))}
                        for rid in sorted(dist_by_rid.keys(), key=lambda r: (dist_by_rid.get(r, 99), r))
                    ],
                    "edges": rid_edges,
                    "truncation": g.get("truncation") if isinstance(g, dict) and isinstance(g.get("truncation"), dict) else {},
                },
                "prompt_references": ref_items,
                "plan": None,
                "plan_mode": "skipped",
            }
        )

    if not items:
        return {"status": "skipped", "reason": "No usable sections were found."}, 0

    # Decide how many LLM calls we can afford.
    llm_enabled = bool(settings.enable_deep_analysis_llm_subsection_recommendations)
    remaining = None if llm_budget is None else max(0, int(llm_budget))
    max_calls = len(items) if remaining is None else min(len(items), remaining)

    calls_used = 0

    if llm_enabled and max_calls > 0:
        order_by_sid = {s.subsection_id: idx for idx, s in enumerate(subsections)}

        def _call_priority(item: dict[str, Any]) -> tuple[int, int, int]:
            seeds = item.get("seed_rids") if isinstance(item.get("seed_rids"), list) else []
            graph = item.get("graph") if isinstance(item.get("graph"), dict) else {}
            nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
            sid = str(item.get("subsection_id") or "")
            order = int(order_by_sid.get(sid, 1_000_000))
            return (-len(seeds), -len(nodes), order)

        to_call = sorted(items, key=_call_priority)[:max_calls]
        calls_used = len(to_call)
        max_workers = min(max(1, int(settings.deep_analysis_max_workers)), len(to_call))

        def _call(item: dict[str, Any]) -> dict | None:
            title = str(item.get("title") or "").strip()
            text = str(subsection_by_id[item["subsection_id"]].text or "")
            text = " ".join(text.split())
            if len(text) > int(settings.deep_analysis_subsection_text_max_chars):
                text = text[: int(settings.deep_analysis_subsection_text_max_chars)] + "\u2026"

            refs_json = json.dumps(item.get("prompt_references") or [], ensure_ascii=False)
            payload = llm_client.chat_json(
                system=get_prompt("deep_analysis/subsection_plan/system"),
                user=render_prompt(
                    "deep_analysis/subsection_plan/user",
                    title=title,
                    text=text,
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
            cleaned = _validate_plan(
                payload, allowed_rids=allowed, allowed_integration_rids=allowed_integrations
            )
            return cleaned

        plans: dict[str, dict] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(_call, item): item["subsection_id"] for item in to_call}
            for fut in as_completed(futures):
                sid = futures[fut]
                try:
                    out = fut.result()
                except Exception as e:
                    out = None
                    plans[sid] = {
                        "summary": "LLM section plan failed; consider reviewing this section manually.",
                        "improvements": [],
                        "reference_integrations": [],
                        "questions": [str(e)[:200]],
                    }
                if out:
                    plans[sid] = out

        for item in items:
            sid = item["subsection_id"]
            if sid in plans:
                item["plan"] = plans[sid]
                item["plan_mode"] = "llm"

    # Heuristic fallback for anything left without a plan.
    for item in items:
        if item.get("plan") is not None:
            continue
        item["plan"] = _heuristic_plan(item.get("prompt_references") or [])
        item["plan_mode"] = "heuristic"

    # Remove prompt-only payload from the report.
    for item in items:
        item.pop("prompt_references", None)

    note = None
    if not llm_enabled:
        note = "LLM section recommendations disabled; used a heuristic fallback."
    elif remaining is not None and remaining <= 0:
        note = "LLM call budget exhausted; used a heuristic fallback for section recommendations."
    elif remaining is not None and remaining < len(items):
        note = "LLM call budget covered only a subset of sections; remaining sections used a heuristic fallback."

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
    # "Not cited" means not cited in this subsection (distance>0), regardless of whether the work
    # is cited elsewhere in the manuscript (in_paper).
    in_paper_neighbors = [r for r in ref_items if bool(r.get("in_paper")) and int(r.get("distance") or 99) > 0]
    new_neighbors = [r for r in ref_items if (not bool(r.get("in_paper"))) and int(r.get("distance") or 99) > 0]

    seeds = sorted(seeds, key=lambda r: str(r.get("rid") or ""))
    in_paper_neighbors = sorted(
        in_paper_neighbors, key=lambda r: (int(r.get("distance") or 99), -_year(r), str(r.get("rid") or "")))
    new_neighbors = sorted(
        new_neighbors, key=lambda r: (int(r.get("distance") or 99), -_year(r), str(r.get("rid") or "")))

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
) -> dict | None:
    if not isinstance(plan, dict):
        return None
    summary = plan.get("summary")
    improvements = plan.get("improvements")
    integrations = plan.get("reference_integrations")
    questions = plan.get("questions")
    if not isinstance(summary, str) or not isinstance(improvements, list) or not isinstance(integrations, list) or not isinstance(questions, list):
        return None

    _rid_re = re.compile(r"R\d{1,4}", re.IGNORECASE)

    def _norm_rid(value: str) -> str | None:
        text = (value or "").strip()
        if not text:
            return None
        if text.startswith("[") and text.endswith("]"):
            text = text[1:-1].strip()
        m = _rid_re.search(text)
        if not m:
            return None
        return m.group(0).upper()

    def _clean_rids(val: Any) -> list[str]:
        if not isinstance(val, list):
            return []
        out: list[str] = []
        for rid in val:
            if not isinstance(rid, str):
                continue
            rid_norm = _norm_rid(rid)
            if not rid_norm:
                continue
            if rid_norm and (not allowed_rids or rid_norm in allowed_rids):
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
        action = item.get("action")
        why = item.get("why")
        how = item.get("how")
        rids = item.get("rids")
        if not isinstance(action, str) or not isinstance(why, str) or not isinstance(how, list):
            continue
        how_clean = [str(h).strip() for h in how if isinstance(h, str) and str(h).strip()]
        cleaned_improvements.append(
            {
                "priority": max(1, priority),
                "action": action.strip(),
                "why": why.strip(),
                "how": how_clean,
                "rids": _clean_rids(rids),
            }
        )
    cleaned_improvements.sort(key=lambda x: int(x.get("priority") or 999))

    cleaned_integrations: list[dict[str, Any]] = []
    for item in integrations:
        if not isinstance(item, dict):
            continue
        rid = item.get("rid")
        priority = item.get("priority")
        why = item.get("why")
        where = item.get("where")
        example = item.get("example")
        if not isinstance(rid, str) or not isinstance(priority, str) or not isinstance(why, str) or not isinstance(where, str) or not isinstance(example, str):
            continue
        rid_clean = _norm_rid(rid)
        if not rid_clean:
            continue
        pr_clean = priority.strip().lower()
        if allowed_rids and rid_clean not in allowed_rids:
            continue
        if allowed_integration_rids and rid_clean not in allowed_integration_rids:
            continue
        if pr_clean not in {"high", "medium", "low"}:
            pr_clean = "medium"
        cleaned_integrations.append(
            {
                "rid": rid_clean,
                "priority": pr_clean,
                "why": why.strip(),
                "where": where.strip(),
                "example": example.strip(),
            }
        )

    cleaned_questions = [str(q).strip() for q in questions if isinstance(q, str) and str(q).strip()]

    return {
        "summary": " ".join(summary.split()).strip(),
        "improvements": cleaned_improvements,
        "reference_integrations": cleaned_integrations,
        "questions": cleaned_questions,
    }


def _heuristic_plan(ref_items: list[dict[str, Any]]) -> dict[str, Any]:
    uncited = [
        r
        for r in ref_items
        if isinstance(r, dict) and (not bool(r.get("cited_in_subsection"))) and int(r.get("distance") or 99) > 0
    ]
    try:
        uncited = sorted(
            uncited,
            key=lambda r: (
                0 if bool(r.get("in_paper")) else 1,
                int(r.get("distance") or 99),
                str(r.get("rid") or ""),
            ),
        )
    except Exception:
        pass
    top = [str(r.get("rid") or "").strip() for r in uncited[:8] if str(r.get("rid") or "").strip()]

    improvements = [
        {
            "priority": 1,
            "action": "Clarify the subsection’s main claim and scope",
            "why": "A clear claim helps readers understand why the cited work is relevant.",
            "how": [
                "Add a one-sentence thesis for the subsection near the start.",
                "Ensure each paragraph supports the thesis with evidence or reasoning.",
            ],
            "rids": [],
        },
        {
            "priority": 2,
            "action": "Strengthen transitions between ideas and evidence",
            "why": "Explicit transitions reduce citation dumping and make the argument traceable.",
            "how": [
                "Add a short bridge sentence when shifting topics.",
                "After each citation, state what it contributes (definition, evidence, contrast, method).",
            ],
            "rids": [],
        },
    ]

    integrations = []
    for rid in top:
        integrations.append(
            {
                "rid": rid,
                "priority": "medium",
                "why": "Potentially strengthens background, evidence, or contrast for the subsection’s claim.",
                "where": "Near the sentence where you introduce the relevant concept or justify the approach.",
                "example": f"This point aligns with prior work (see [{rid}]).",
            }
        )

    questions = [
        "What is the single most important claim this subsection must establish for the paper’s argument?",
        "Which concept(s) should be defined more explicitly to make the subsection self-contained?",
    ]

    return {
        "summary": "Refine the subsection’s claim and make the link between claims and citations explicit. Add a small number of high-value references where they directly support your key statements.",
        "improvements": improvements,
        "reference_integrations": integrations,
        "questions": questions,
    }

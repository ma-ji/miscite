from __future__ import annotations

import math
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from server.miscite.analysis.deep_analysis.network import compute_network_metrics
from server.miscite.analysis.deep_analysis.prep import (
    build_citation_stats,
    filter_verified_original_refs,
)
from server.miscite.analysis.deep_analysis.references import build_reference_master_list
from server.miscite.analysis.deep_analysis.suggestions import (
    build_suggestions,
    extract_section_order,
)
from server.miscite.analysis.deep_analysis.types import (
    DeepAnalysisResult,
    ProgressFn,
    ResolvedWorkLike,
)
from server.miscite.analysis.parse.citation_parsing import CitationInstance, ReferenceEntry
from server.miscite.analysis.shared.normalize import normalize_doi
from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.prompts import get_prompt, render_prompt
from server.miscite.sources.openalex import OpenAlexClient

def run_deep_analysis(
    *,
    settings: Settings,
    llm_client: OpenRouterClient,
    openalex: OpenAlexClient,
    references: list[ReferenceEntry],
    resolved_by_ref_id: dict[str, ResolvedWorkLike],
    citation_to_ref: list[tuple[CitationInstance, ReferenceEntry | None]],
    paper_excerpt: str,
    progress: ProgressFn | None = None,
    llm_budget: int | None = None,
) -> DeepAnalysisResult:
    started = time.time()
    used_sources: list[dict] = []
    limitations: list[str] = []

    if not settings.enable_deep_analysis:
        return DeepAnalysisResult(
            report={"status": "skipped", "reason": "Deep analysis disabled."},
            used_sources=used_sources,
            limitations=limitations,
        )

    def _p(message: str, frac: float) -> None:
        if progress:
            progress(message, max(0.0, min(1.0, float(frac))))

    # -------------------------
    # Original refs + contexts
    # -------------------------
    _p("Preparing verified reference set", 0.02)
    cite_counts, cite_contexts = build_citation_stats(citation_to_ref)
    verified_original_refs = filter_verified_original_refs(
        settings=settings,
        references=references,
        resolved_by_ref_id=resolved_by_ref_id,
    )

    if not verified_original_refs:
        return DeepAnalysisResult(
            report={"status": "skipped", "reason": "No verified references available for deep analysis."},
            used_sources=used_sources,
            limitations=limitations,
        )

    if len(verified_original_refs) > settings.deep_analysis_max_original_refs:
        return DeepAnalysisResult(
            report={
                "status": "skipped",
                "reason": "Too many verified references for deep analysis in this configuration.",
                "details": {
                    "verified_original_refs": len(verified_original_refs),
                    "max_original_refs": settings.deep_analysis_max_original_refs,
                },
            },
            used_sources=used_sources,
            limitations=limitations,
        )

    # -------------------------
    # Step 1: Key refs (LLM)
    # -------------------------
    _p("Selecting key references", 0.08)
    key_ref_target = max(1, int(math.ceil(len(verified_original_refs) / 2)))

    key_ref_ids: list[str] = []
    llm_calls_used = 0

    if settings.enable_deep_analysis_llm_key_selection and (llm_budget is None or llm_budget >= 1):
        llm_calls_used += 1
        used_sources.append(
            {
                "name": "OpenRouter (deep analysis)",
                "detail": f"Key-reference selection via {settings.llm_deep_analysis_model}.",
            }
        )

        items: list[str] = []
        for ref in verified_original_refs:
            work = resolved_by_ref_id.get(ref.ref_id)
            title = (work.title or "").strip() if work else ""
            year = work.year if work else None
            contexts = cite_contexts.get(ref.ref_id) or []
            example = contexts[0] if contexts else ""
            example = " ".join(example.split())
            if len(example) > 220:
                example = example[:220] + "…"
            title = " ".join(title.split())
            if len(title) > 140:
                title = title[:140] + "…"
            items.append(
                (
                    f"- ref_id={ref.ref_id} | cites_in_paper={cite_counts.get(ref.ref_id, 0)}"
                    f" | year={year or 'NA'} | title={title or 'NA'}"
                    f" | example_use={example or 'NA'}"
                )
            )

        excerpt = " ".join((paper_excerpt or "").split())
        if len(excerpt) > settings.deep_analysis_paper_excerpt_max_chars:
            excerpt = excerpt[: settings.deep_analysis_paper_excerpt_max_chars] + "…"

        payload = llm_client.chat_json(
            system=get_prompt("deep_analysis/key_refs/system"),
            user=render_prompt(
                "deep_analysis/key_refs/user",
                key_ref_target=key_ref_target,
                excerpt=excerpt,
                items="\n".join(items),
            ),
        )

        raw_ids = payload.get("key_ref_ids")
        if isinstance(raw_ids, list):
            allowed = {r.ref_id for r in verified_original_refs}
            cleaned: list[str] = []
            for rid in raw_ids:
                if not isinstance(rid, str):
                    continue
                rid = rid.strip()
                if rid in allowed and rid not in cleaned:
                    cleaned.append(rid)
            if len(cleaned) == key_ref_target:
                key_ref_ids = cleaned

        if not key_ref_ids:
            limitations.append("Deep analysis: key-reference selection fell back to a heuristic due to LLM output issues.")

    if not key_ref_ids:
        # Heuristic fallback: most-cited in the manuscript text, then newest.
        scored = []
        for ref in verified_original_refs:
            work = resolved_by_ref_id.get(ref.ref_id)
            year = work.year if work else None
            scored.append((cite_counts.get(ref.ref_id, 0), year or 0, ref.ref_id))
        scored.sort(reverse=True)
        key_ref_ids = [rid for _, _, rid in scored[:key_ref_target]]

    key_ref_set = set(key_ref_ids)

    # -------------------------
    # Step 2–6: Lit pool build
    # -------------------------
    _p("Collecting citation links (this can take a bit)", 0.18)
    used_sources.append(
        {
            "name": "OpenAlex API (deep analysis)",
            "detail": "Citation links (works cited by / citing key references).",
        }
    )

    # Node IDs: prefer OpenAlex IDs; fall back to DOI or ref_id for original refs.
    def _node_id_for_original(ref_id: str) -> str:
        work = resolved_by_ref_id.get(ref_id)
        openalex_id = (work.openalex_id or "").strip() if work else ""
        if openalex_id:
            return openalex_id
        doi = normalize_doi((work.doi or "").strip()) if work else None
        if doi:
            return f"doi:{doi}"
        return f"ref:{ref_id}"

    original_nodes: set[str] = {_node_id_for_original(ref.ref_id) for ref in verified_original_refs}
    key_nodes: set[str] = {_node_id_for_original(ref_id) for ref_id in key_ref_ids}

    # OpenAlex-only seeds for expansion.
    key_openalex_ids: list[str] = [nid for nid in key_nodes if nid.startswith("https://openalex.org/") or nid.startswith("W")]

    max_nodes = settings.deep_analysis_max_nodes
    max_edges = settings.deep_analysis_max_edges

    lit_nodes: set[str] = set(original_nodes)
    edges: list[tuple[str, str]] = []

    trunc = {
        "hit_max_nodes": False,
        "hit_max_edges": False,
        "skipped_key_refs_no_openalex": 0,
        "skipped_openalex_fetches": 0,
    }

    def _try_add_node(node_id: str) -> bool:
        if node_id in lit_nodes:
            return True
        if len(lit_nodes) >= max_nodes:
            trunc["hit_max_nodes"] = True
            return False
        lit_nodes.add(node_id)
        return True

    def _try_add_edge(src: str, dst: str) -> bool:
        if len(edges) >= max_edges:
            trunc["hit_max_edges"] = True
            return False
        edges.append((src, dst))
        return True

    def _safe_get_work(openalex_id: str) -> dict | None:
        try:
            return openalex.get_work_by_id(openalex_id)
        except Exception:
            return None

    def _extract_referenced_works(work: dict | None) -> list[str]:
        if not isinstance(work, dict):
            return []
        refs = work.get("referenced_works")
        if not isinstance(refs, list):
            return []
        out: list[str] = []
        for rid in refs:
            if not isinstance(rid, str):
                continue
            rid = rid.strip()
            if not rid:
                continue
            out.append(rid)
            if len(out) >= settings.deep_analysis_max_references_per_work:
                break
        return out

    # Step 2: works cited by key refs (Cited Refs)
    key_to_refs: dict[str, list[str]] = {}
    if not key_openalex_ids:
        trunc["skipped_key_refs_no_openalex"] = len(key_ref_ids)
    else:
        with ThreadPoolExecutor(max_workers=settings.deep_analysis_max_workers) as ex:
            futures = {ex.submit(_safe_get_work, kid): kid for kid in key_openalex_ids}
            for fut in as_completed(futures):
                kid = futures[fut]
                work = fut.result()
                if not work:
                    trunc["skipped_openalex_fetches"] += 1
                    continue
                refs = _extract_referenced_works(work)
                key_to_refs[kid] = refs
                for rid in refs:
                    if not _try_add_node(rid):
                        break
                    _try_add_edge(kid, rid)
                if trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                    break

    cited_refs: set[str] = set()
    for refs in key_to_refs.values():
        cited_refs.update(refs)

    _p("Collecting second-hop citations", 0.34)

    # Step 3: works cited by cited refs (Cited Refs2)
    cited2_refs: set[str] = set()
    if cited_refs and not (trunc["hit_max_nodes"] or trunc["hit_max_edges"]):
        seeds = list(cited_refs)
        if len(seeds) > settings.deep_analysis_max_second_hop_seeds:
            seeds = seeds[: settings.deep_analysis_max_second_hop_seeds]
            limitations.append(
                "Deep analysis: second-hop expansion was limited to keep the run fast and memory-safe."
            )

        with ThreadPoolExecutor(max_workers=settings.deep_analysis_max_workers) as ex:
            futures = {ex.submit(_safe_get_work, sid): sid for sid in seeds}
            for fut in as_completed(futures):
                sid = futures[fut]
                work = fut.result()
                if not work:
                    trunc["skipped_openalex_fetches"] += 1
                    continue
                refs2 = _extract_referenced_works(work)
                for rid in refs2:
                    if not _try_add_node(rid):
                        break
                    cited2_refs.add(rid)
                    _try_add_edge(sid, rid)
                if trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                    break

    # Step 4: works citing key refs (Citing Refs), capped at 100 per key ref.
    _p("Collecting recent papers that cite your key references", 0.50)
    citing_refs: set[str] = set()
    if key_openalex_ids and not (trunc["hit_max_nodes"] or trunc["hit_max_edges"]):
        total_budget = max(0, settings.deep_analysis_max_total_citing_refs)
        for kid in key_openalex_ids:
            if total_budget <= 0 or trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                break
            try:
                citing = openalex.list_citing_works(kid, rows=min(100, total_budget))
            except Exception:
                trunc["skipped_openalex_fetches"] += 1
                continue
            for w in citing:
                if not isinstance(w, dict):
                    continue
                wid = w.get("id")
                if not isinstance(wid, str) or not wid.strip():
                    continue
                wid = wid.strip()
                if not _try_add_node(wid):
                    break
                if wid not in citing_refs:
                    citing_refs.add(wid)
                    total_budget -= 1
                _try_add_edge(wid, kid)
                if total_budget <= 0 or trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                    break

    # Step 5: works cited by citing refs (Citing Refs2).
    _p("Collecting references from those recent papers", 0.62)
    citing2_refs: set[str] = set()
    if citing_refs and not (trunc["hit_max_nodes"] or trunc["hit_max_edges"]):
        seeds = list(citing_refs)
        if len(seeds) > settings.deep_analysis_max_citing_refs_for_second_hop:
            seeds = seeds[: settings.deep_analysis_max_citing_refs_for_second_hop]
            limitations.append(
                "Deep analysis: expansion from citing papers was limited to keep the run fast and memory-safe."
            )
        with ThreadPoolExecutor(max_workers=settings.deep_analysis_max_workers) as ex:
            futures = {ex.submit(_safe_get_work, sid): sid for sid in seeds}
            for fut in as_completed(futures):
                sid = futures[fut]
                work = fut.result()
                if not work:
                    trunc["skipped_openalex_fetches"] += 1
                    continue
                refs2 = _extract_referenced_works(work)
                for rid in refs2:
                    if not _try_add_node(rid):
                        break
                    citing2_refs.add(rid)
                    _try_add_edge(sid, rid)
                if trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                    break

    # Step 6: Lit pool assembled.
    lit_pool = {
        "original_refs": len(original_nodes),
        "verified_original_refs": len(verified_original_refs),
        "key_refs": len(key_ref_ids),
        "cited_refs": len(cited_refs),
        "cited_refs2": len(cited2_refs),
        "citing_refs": len(citing_refs),
        "citing_refs2": len(citing2_refs),
        "total_nodes": len(lit_nodes),
        "total_edges": len(edges),
    }

    # -------------------------
    # Step 7–8: Network + ranks
    # -------------------------
    _p("Scoring the literature pool", 0.74)
    metrics = compute_network_metrics(
        nodes=lit_nodes,
        edges=edges,
        key_nodes=key_nodes,
        original_nodes=original_nodes,
        original_ref_id_by_node={_node_id_for_original(r.ref_id): r.ref_id for r in verified_original_refs},
        cite_counts_by_ref_id=dict(cite_counts),
    )

    _p("Preparing a clean reference list for this section", 0.84)
    references_by_rid, reference_groups, citation_groups, ref_truncation = build_reference_master_list(
        settings=settings,
        openalex=openalex,
        metrics=metrics,
        key_ref_ids=key_ref_ids,
        verified_original_refs=verified_original_refs,
        resolved_by_ref_id=resolved_by_ref_id,
        node_id_for_original_ref=_node_id_for_original,
    )
    trunc.update(ref_truncation)

    _p("Drafting improvement suggestions", 0.90)
    section_order = extract_section_order(paper_excerpt)
    suggestion_payload, suggestion_calls = build_suggestions(
        settings=settings,
        llm_client=llm_client,
        paper_excerpt=paper_excerpt,
        llm_budget=(None if llm_budget is None else max(0, llm_budget - llm_calls_used)),
        citation_groups=citation_groups,
        references_by_rid=references_by_rid,
        section_order=section_order,
    )
    llm_calls_used += suggestion_calls

    _p("Deep analysis complete", 1.0)

    report = {
        "status": "completed",
        "timing": {"seconds": round(time.time() - started, 3)},
        "lit_pool": lit_pool,
        "key_ref_ids": key_ref_ids,
        "network": metrics.get("network", {}),
        "categories": metrics.get("categories", {}),
        "reference_groups": reference_groups,
        "citation_groups": citation_groups,
        "references": references_by_rid,
        "suggestions": suggestion_payload,
        "truncation": trunc,
        "llm_calls_used": llm_calls_used,
    }
    return DeepAnalysisResult(report=report, used_sources=used_sources, limitations=limitations)

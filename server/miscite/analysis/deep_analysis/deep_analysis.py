from __future__ import annotations

import math
import time
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from server.miscite.analysis.deep_analysis.network import compute_network_metrics
from server.miscite.analysis.deep_analysis.prep import (
    build_citation_stats,
    filter_verified_original_refs,
)
from server.miscite.analysis.deep_analysis.references import build_reference_master_list
from server.miscite.analysis.deep_analysis.reviewers import build_potential_reviewers_from_coupling
from server.miscite.analysis.deep_analysis.subsections import (
    build_weak_adjacency,
    collapse_to_top_level_sections,
    extract_cited_ref_ids_by_subsection,
    extract_subsections,
    subnetwork_nodes_by_distance,
)
from server.miscite.analysis.deep_analysis.structure import extract_subsections_with_llm
from server.miscite.analysis.deep_analysis.subsection_recommendations import build_subsection_recommendations
from server.miscite.analysis.deep_analysis.suggestions import (
    build_suggestions,
    extract_section_order,
)
from server.miscite.analysis.deep_analysis.types import (
    DeepAnalysisResult,
    ProgressFn,
    ResolvedWorkLike,
)
from server.miscite.analysis.match.types import CitationMatch
from server.miscite.analysis.parse.citation_parsing import ReferenceEntry
from server.miscite.analysis.shared.normalize import normalize_doi
from server.miscite.analysis.shared.excluded_sources import load_excluded_sources, matches_excluded_source
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
    reference_records: dict[str, dict],
    resolved_by_ref_id: dict[str, ResolvedWorkLike],
    citation_matches: list[CitationMatch],
    paper_excerpt: str,
    progress: ProgressFn | None = None,
    llm_budget: int | None = None,
) -> DeepAnalysisResult:
    started = time.time()
    used_sources: list[dict] = []
    limitations: list[str] = []
    excluded_sources = load_excluded_sources()
    excluded_nodes: set[str] = set()
    excluded_nodes_lock = threading.Lock()

    if not settings.enable_deep_analysis:
        return DeepAnalysisResult(
            report={"status": "skipped", "reason": "Deep analysis disabled."},
            used_sources=used_sources,
            limitations=limitations,
        )

    def _p(message: str, frac: float) -> None:
        if progress:
            progress(message, max(0.0, min(1.0, float(frac))))

    def _work_is_excluded(work: dict | None) -> bool:
        if not excluded_sources or not isinstance(work, dict):
            return False
        host = work.get("host_venue")
        if isinstance(host, dict):
            for key in ("display_name", "publisher"):
                val = host.get(key)
                if isinstance(val, str) and matches_excluded_source(val, excluded_sources):
                    return True
        for loc_key in ("primary_location", "best_oa_location"):
            loc = work.get(loc_key)
            if not isinstance(loc, dict):
                continue
            src = loc.get("source")
            if not isinstance(src, dict):
                continue
            val = src.get("display_name")
            if isinstance(val, str) and matches_excluded_source(val, excluded_sources):
                return True
        return False

    # -------------------------
    # Original refs + contexts
    # -------------------------
    _p("Preparing verified reference set", 0.02)
    cite_counts, cite_contexts = build_citation_stats(citation_matches)
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

    def _key_ref_rank(ref: ReferenceEntry) -> tuple[int, int, str]:
        work = resolved_by_ref_id.get(ref.ref_id)
        year = work.year if work else None
        return (int(cite_counts.get(ref.ref_id, 0)), int(year or 0), ref.ref_id)

    ranked_verified_refs = sorted(verified_original_refs, key=_key_ref_rank, reverse=True)

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
        for ref in ranked_verified_refs:
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
        key_ref_ids = [ref.ref_id for ref in ranked_verified_refs[:key_ref_target]]

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

    def _is_openalex_node_id(node_id: str) -> bool:
        if not node_id:
            return False
        node_id = node_id.strip()
        return bool(node_id) and (
            node_id.startswith("https://openalex.org/")
            or node_id.startswith("https://api.openalex.org/works/")
            or node_id.startswith("W")
        )

    original_nodes: set[str] = {_node_id_for_original(ref.ref_id) for ref in verified_original_refs}
    key_node_ids: list[str] = []
    seen_key_nodes: set[str] = set()
    for ref_id in key_ref_ids:
        nid = _node_id_for_original(ref_id)
        if nid in seen_key_nodes:
            continue
        seen_key_nodes.add(nid)
        key_node_ids.append(nid)
    key_nodes: set[str] = set(key_node_ids)

    # OpenAlex-only seeds for expansion (stable order).
    key_openalex_ids: list[str] = []
    seen_openalex_ids: set[str] = set()
    for nid in key_node_ids:
        if not _is_openalex_node_id(nid):
            continue
        if nid in seen_openalex_ids:
            continue
        seen_openalex_ids.add(nid)
        key_openalex_ids.append(nid)

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
        # Hard exclusion: don't admit excluded venues into the network.
        if excluded_sources and _is_openalex_node_id(node_id):
            if node_id in excluded_nodes:
                return False
            if not _safe_get_work(node_id):
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
            work = openalex.get_work_by_id(openalex_id)
        except Exception:
            return None
        if _work_is_excluded(work):
            node_id = None
            if isinstance(work, dict):
                node_id = work.get("id")
            node_id = str(node_id or openalex_id).strip()
            if node_id:
                with excluded_nodes_lock:
                    excluded_nodes.add(node_id)
                    if node_id.startswith("https://openalex.org/") or node_id.startswith("https://api.openalex.org/works/"):
                        suffix = node_id.rstrip("/").split("/")[-1]
                        if suffix:
                            excluded_nodes.add(suffix)
            return None
        return work

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
    cited_refs: set[str] = set()
    cited_refs_ordered: list[str] = []
    if not key_openalex_ids:
        trunc["skipped_key_refs_no_openalex"] = len(key_ref_ids)
    else:
        with ThreadPoolExecutor(max_workers=settings.deep_analysis_max_workers) as ex:
            for kid, work in zip(key_openalex_ids, ex.map(_safe_get_work, key_openalex_ids)):
                if not work:
                    trunc["skipped_openalex_fetches"] += 1
                    continue
                refs = _extract_referenced_works(work)
                for rid in refs:
                    if rid in excluded_nodes:
                        continue
                    if not _try_add_node(rid):
                        if trunc["hit_max_nodes"]:
                            break
                        continue
                    if rid not in cited_refs:
                        cited_refs.add(rid)
                        cited_refs_ordered.append(rid)
                    _try_add_edge(kid, rid)
                if trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                    break

    cited2_refs: set[str] = set()

    # Step 3: works citing key refs (Citing Refs), capped at 100 per key ref.
    _p("Collecting recent papers that cite your key references", 0.34)
    citing_refs: set[str] = set()
    citing_refs_ordered: list[str] = []
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
                if _work_is_excluded(w):
                    wid_ex = w.get("id")
                    wid_ex = str(wid_ex or "").strip()
                    if wid_ex:
                        with excluded_nodes_lock:
                            excluded_nodes.add(wid_ex)
                            if wid_ex.startswith("https://openalex.org/") or wid_ex.startswith("https://api.openalex.org/works/"):
                                suffix = wid_ex.rstrip("/").split("/")[-1]
                                if suffix:
                                    excluded_nodes.add(suffix)
                    continue
                wid = w.get("id")
                if not isinstance(wid, str) or not wid.strip():
                    continue
                wid = wid.strip()
                if excluded_sources and not (
                    isinstance(w.get("host_venue"), dict)
                    or isinstance(w.get("primary_location"), dict)
                    or isinstance(w.get("best_oa_location"), dict)
                ):
                    # Ensure excluded venues are still caught even if list results omit venue/source fields.
                    if not _safe_get_work(wid):
                        continue
                if wid in excluded_nodes:
                    continue
                if not _try_add_node(wid):
                    if trunc["hit_max_nodes"]:
                        break
                    continue
                if wid not in citing_refs:
                    citing_refs.add(wid)
                    citing_refs_ordered.append(wid)
                    total_budget -= 1
                _try_add_edge(wid, kid)
                if total_budget <= 0 or trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                    break

    # Step 4: works cited by citing refs (Citing Refs2).
    _p("Collecting references from those recent papers", 0.50)
    citing2_refs: set[str] = set()
    if citing_refs and not (trunc["hit_max_nodes"] or trunc["hit_max_edges"]):
        seeds = citing_refs_ordered
        if len(seeds) > settings.deep_analysis_max_citing_refs_for_second_hop:
            seeds = seeds[: settings.deep_analysis_max_citing_refs_for_second_hop]
            limitations.append(
                "Deep analysis: expansion from citing papers was limited to keep the run fast and memory-safe."
            )
        with ThreadPoolExecutor(max_workers=settings.deep_analysis_max_workers) as ex:
            for sid, work in zip(seeds, ex.map(_safe_get_work, seeds)):
                if not work:
                    trunc["skipped_openalex_fetches"] += 1
                    continue
                refs2 = _extract_referenced_works(work)
                for rid in refs2:
                    if rid in excluded_nodes:
                        continue
                    if not _try_add_node(rid):
                        if trunc["hit_max_nodes"]:
                            break
                        continue
                    citing2_refs.add(rid)
                    _try_add_edge(sid, rid)
                if trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                    break

    _p("Collecting second-hop citations", 0.62)

    # Step 5: works cited by cited refs (Cited Refs2)
    if cited_refs and not (trunc["hit_max_nodes"] or trunc["hit_max_edges"]):
        seeds = cited_refs_ordered
        if len(seeds) > settings.deep_analysis_max_second_hop_seeds:
            seeds = seeds[: settings.deep_analysis_max_second_hop_seeds]
            limitations.append(
                "Deep analysis: second-hop expansion was limited to keep the run fast and memory-safe."
            )

        with ThreadPoolExecutor(max_workers=settings.deep_analysis_max_workers) as ex:
            for sid, work in zip(seeds, ex.map(_safe_get_work, seeds)):
                if not work:
                    trunc["skipped_openalex_fetches"] += 1
                    continue
                refs2 = _extract_referenced_works(work)
                for rid in refs2:
                    if rid in excluded_nodes:
                        continue
                    if not _try_add_node(rid):
                        if trunc["hit_max_nodes"]:
                            break
                        continue
                    cited2_refs.add(rid)
                    _try_add_edge(sid, rid)
                if trunc["hit_max_nodes"] or trunc["hit_max_edges"]:
                    break

    if excluded_nodes:
        cited_refs.difference_update(excluded_nodes)
        cited2_refs.difference_update(excluded_nodes)
        citing_refs.difference_update(excluded_nodes)
        citing2_refs.difference_update(excluded_nodes)
        key_nodes.difference_update(excluded_nodes)
        original_nodes.difference_update(excluded_nodes)
        lit_nodes.difference_update(excluded_nodes)
        edges = [(src, dst) for src, dst in edges if src not in excluded_nodes and dst not in excluded_nodes]
        limitations.append(
            f"Deep analysis: excluded {len(excluded_nodes)} works from the citation network based on excluded sources."
        )

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
    # Step 6.5: Subsection graphs
    # -------------------------
    _p("Preparing section citation graphs", 0.68)
    structure_report: dict[str, Any] = {"mode": "heuristic", "status": "completed", "subsections": [], "notes": []}
    raw_subsections = extract_subsections(paper_excerpt)
    structure_report["subsections"] = [
        {"subsection_id": s.subsection_id, "title": s.title, "level": s.level, "chars": len(s.text or "")}
        for s in raw_subsections
    ]

    if settings.enable_deep_analysis_llm_structure and (llm_budget is None or (llm_budget - llm_calls_used) >= 1):
        llm_calls_used += 1
        used_sources.append(
            {
                "name": "OpenRouter (deep analysis)",
                "detail": f"Manuscript structure extraction via {settings.llm_deep_analysis_model}.",
            }
        )
        try:
            llm_subsections, llm_structure_report, _notes = extract_subsections_with_llm(
                settings=settings,
                llm_client=llm_client,
                text=paper_excerpt,
            )
            if llm_subsections:
                raw_subsections = llm_subsections
                structure_report = llm_structure_report
            else:
                structure_report = llm_structure_report
                limitations.append(
                    "Deep analysis: manuscript structure extraction did not identify subsections; used a heuristic splitter."
                )
        except Exception as e:
            msg = str(e).strip()
            if len(msg) > 240:
                msg = msg[:240] + "…"
            structure_report = {"mode": "llm", "status": "failed", "reason": msg}
            limitations.append("Deep analysis: manuscript structure extraction failed; used a heuristic splitter.")

    # Recommendations run at the highest-level (combine all sublevels).
    subsections = collapse_to_top_level_sections(raw_subsections)
    structure_report["top_level_only"] = True
    structure_report["sections"] = [
        {"subsection_id": s.subsection_id, "title": s.title, "level": s.level, "chars": len(s.text or "")}
        for s in subsections
    ]
    cited_ref_ids_by_subsection_id = extract_cited_ref_ids_by_subsection(
        subsections=subsections,
        references=references,
        reference_records=reference_records,
    )
    verified_ref_ids = {r.ref_id for r in verified_original_refs}
    adjacency = build_weak_adjacency(lit_nodes, edges)

    candidate_graphs: list[dict] = []
    for subsection in subsections:
        cited_ref_ids = cited_ref_ids_by_subsection_id.get(subsection.subsection_id) or set()
        cited_ref_ids = {rid for rid in cited_ref_ids if rid in verified_ref_ids}
        if not cited_ref_ids:
            continue
        seed_nodes = {_node_id_for_original(rid) for rid in cited_ref_ids}
        seed_nodes = {nid for nid in seed_nodes if nid in lit_nodes}
        if not seed_nodes:
            continue
        dist_by_node, hit_max_nodes = subnetwork_nodes_by_distance(
            adjacency=adjacency,
            seed_nodes=seed_nodes,
            max_hops=3,
            max_nodes=max(50, int(settings.deep_analysis_subsection_graph_max_nodes)),
        )
        if not dist_by_node:
            continue
        nodes_in_subnet = set(dist_by_node.keys())
        subnet_edges: list[tuple[str, str]] = []
        hit_max_edges = False
        max_edges = max(100, int(settings.deep_analysis_subsection_graph_max_edges))
        for src, dst in edges:
            if src not in nodes_in_subnet or dst not in nodes_in_subnet:
                continue
            subnet_edges.append((src, dst))
            if len(subnet_edges) >= max_edges:
                hit_max_edges = True
                break
        candidate_graphs.append(
            {
                "subsection_id": subsection.subsection_id,
                "title": subsection.title,
                "level": subsection.level,
                "seed_ref_ids": sorted(cited_ref_ids),
                "seed_nodes": sorted(seed_nodes),
                "seed_ref_count": len(cited_ref_ids),
                "node_distances": dist_by_node,
                "edges": subnet_edges,
                "truncation": {"hit_max_nodes": hit_max_nodes, "hit_max_edges": hit_max_edges},
            }
        )

    max_sections = int(settings.deep_analysis_subsection_max_subsections)
    if max_sections <= 0:
        subsection_graphs = candidate_graphs
    elif len(candidate_graphs) <= max_sections:
        subsection_graphs = candidate_graphs
    else:
        # Keep the output bounded and prioritize the most citation-dense sections.
        try:
            subsection_graphs = sorted(
                candidate_graphs,
                key=lambda g: (int(g.get("seed_ref_count") or 0), str(g.get("title") or "")),
                reverse=True,
            )[:max_sections]
        except Exception:
            subsection_graphs = candidate_graphs[:max_sections]

    extra_nodes: set[str] = set()
    for g in subsection_graphs:
        node_distances = g.get("node_distances")
        if isinstance(node_distances, dict):
            extra_nodes.update([nid for nid in node_distances.keys() if isinstance(nid, str)])

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
    references_by_rid, reference_groups, citation_groups, ref_truncation, rid_by_node_id = build_reference_master_list(
        settings=settings,
        openalex=openalex,
        metrics=metrics,
        key_ref_ids=key_ref_ids,
        verified_original_refs=verified_original_refs,
        resolved_by_ref_id=resolved_by_ref_id,
        node_id_for_original_ref=_node_id_for_original,
        extra_node_ids=sorted(extra_nodes),
    )
    trunc.update(ref_truncation)

    def _normalize_source_label(value: str | None) -> str:
        if not isinstance(value, str):
            return ""
        return " ".join(value.replace("\u00a0", " ").split()).strip().lower()

    def _extract_sources_from_openalex(record: dict | None) -> set[str]:
        out: set[str] = set()
        if not isinstance(record, dict):
            return out
        hv = record.get("host_venue")
        if isinstance(hv, dict):
            for key in ("display_name", "publisher"):
                norm = _normalize_source_label(hv.get(key))
                if norm:
                    out.add(norm)
        for key in ("primary_location", "best_oa_location"):
            loc = record.get(key)
            if not isinstance(loc, dict):
                continue
            src = loc.get("source")
            if not isinstance(src, dict):
                continue
            norm = _normalize_source_label(src.get("display_name"))
            if norm:
                out.add(norm)
        return out

    cited_sources_override: set[str] = set()
    cited_sources_refs_total = 0
    cited_sources_refs_with_source = 0
    for ref in verified_original_refs:
        cited_sources_refs_total += 1
        resolved = resolved_by_ref_id.get(ref.ref_id)
        if not resolved:
            continue
        labels: set[str] = set()
        if isinstance(resolved.journal, str):
            norm = _normalize_source_label(resolved.journal)
            if norm:
                labels.add(norm)
        if isinstance(resolved.source, str):
            norm = _normalize_source_label(resolved.source)
            if norm:
                labels.add(norm)
        if isinstance(resolved.openalex_record, dict):
            labels.update(_extract_sources_from_openalex(resolved.openalex_record))
        if labels:
            cited_sources_refs_with_source += 1
            cited_sources_override.update(labels)

    coupling_rids: list[str] = []
    categories = metrics.get("categories") if isinstance(metrics.get("categories"), dict) else {}
    raw_coupling = categories.get("bibliographic_coupling")
    if isinstance(raw_coupling, list):
        for node_id in raw_coupling:
            if not isinstance(node_id, str) or not node_id.strip():
                continue
            rid = rid_by_node_id.get(node_id)
            coupling_rids.append(rid or node_id.strip())
    if not coupling_rids:
        for group in citation_groups:
            if not isinstance(group, dict):
                continue
            if str(group.get("key") or "") != "bibliographic_coupling":
                continue
            rids = group.get("rids")
            if isinstance(rids, list):
                coupling_rids = [rid for rid in rids if isinstance(rid, str) and rid.strip()]
            break
    if not coupling_rids:
        for group in reference_groups:
            if not isinstance(group, dict):
                continue
            if str(group.get("key") or "") != "bibliographic_coupling":
                continue
            rids = group.get("rids")
            if isinstance(rids, list):
                coupling_rids = [rid for rid in rids if isinstance(rid, str) and rid.strip()]
            break

    if coupling_rids:
        coupling_rids = list(dict.fromkeys(coupling_rids))

    reviewer_debug: dict[str, Any] = {}
    reviewer_debug["cited_sources_override_refs_total"] = cited_sources_refs_total
    reviewer_debug["cited_sources_override_refs_with_source"] = cited_sources_refs_with_source
    potential_reviewers = build_potential_reviewers_from_coupling(
        coupling_rids=coupling_rids,
        references_by_rid=references_by_rid,
        recent_years=settings.deep_analysis_reviewer_recent_years,
        openalex=openalex,
        author_works_max=settings.deep_analysis_reviewer_author_works_max,
        order_rule=settings.deep_analysis_reviewer_order,
        cited_sources_override=cited_sources_override or None,
        debug=reviewer_debug,
    )
    for ref in references_by_rid.values():
        if isinstance(ref, dict):
            ref.pop("authors_detailed", None)

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

    _p("Drafting section-by-section revision plans", 0.94)
    subrec_payload, subrec_calls = build_subsection_recommendations(
        settings=settings,
        llm_client=llm_client,
        subsections=subsections,
        subsection_graphs=subsection_graphs,
        references_by_rid=references_by_rid,
        rid_by_node_id=rid_by_node_id,
        llm_budget=(None if llm_budget is None else max(0, llm_budget - llm_calls_used)),
    )
    llm_calls_used += subrec_calls
    if suggestion_calls > 0 or subrec_calls > 0:
        used_sources.append(
            {
                "name": "OpenRouter (deep analysis)",
                "detail": f"Section revision plans and/or recommendations via {settings.llm_deep_analysis_model}.",
            }
        )

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
        "potential_reviewers": potential_reviewers,
        "reviewer_debug": reviewer_debug,
        "manuscript_structure": structure_report,
        "suggestions": suggestion_payload,
        "subsection_recommendations": subrec_payload,
        "truncation": trunc,
        "llm_calls_used": llm_calls_used,
    }
    return DeepAnalysisResult(report=report, used_sources=used_sources, limitations=limitations)

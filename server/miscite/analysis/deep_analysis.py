from __future__ import annotations

import math
import re
import time
from collections import Counter, defaultdict, deque
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any, Protocol

from server.miscite.analysis.citation_parsing import CitationInstance, ReferenceEntry
from server.miscite.analysis.normalize import normalize_doi
from server.miscite.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient
from server.miscite.prompts import get_prompt, render_prompt
from server.miscite.sources.openalex import OpenAlexClient


class ResolvedWorkLike(Protocol):
    doi: str | None
    title: str | None
    year: int | None
    openalex_id: str | None
    openalex_record: dict | None
    source: str | None
    confidence: float


ProgressFn = Callable[[str, float], None]


@dataclass(frozen=True)
class DeepAnalysisResult:
    report: dict
    used_sources: list[dict]
    limitations: list[str]


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
    cite_counts: Counter[str] = Counter()
    cite_contexts: dict[str, list[str]] = defaultdict(list)
    for cit, ref in citation_to_ref:
        if not ref:
            continue
        cite_counts[ref.ref_id] += 1
        if cit.context:
            cite_contexts[ref.ref_id].append(cit.context.strip())

    verified_original_refs: list[ReferenceEntry] = []
    for ref in references:
        work = resolved_by_ref_id.get(ref.ref_id)
        if not work:
            continue
        if not work.source:
            continue
        if work.confidence < settings.deep_analysis_min_confidence:
            continue
        verified_original_refs.append(ref)

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
    metrics = _compute_network_metrics(
        nodes=lit_nodes,
        edges=edges,
        key_nodes=key_nodes,
        original_nodes=original_nodes,
        original_ref_id_by_node={_node_id_for_original(r.ref_id): r.ref_id for r in verified_original_refs},
        cite_counts_by_ref_id=dict(cite_counts),
    )

    _p("Preparing a clean reference list for this section", 0.84)
    references_by_rid, reference_groups, citation_groups, ref_truncation = _build_reference_master_list(
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
    section_order = _extract_section_order(paper_excerpt)
    suggestion_payload, suggestion_calls = _build_suggestions(
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


def _compute_network_metrics(
    *,
    nodes: set[str],
    edges: list[tuple[str, str]],
    key_nodes: set[str],
    original_nodes: set[str],
    original_ref_id_by_node: dict[str, str],
    cite_counts_by_ref_id: dict[str, int],
) -> dict[str, Any]:
    node_list = list(nodes)
    out_adj: dict[str, set[str]] = {n: set() for n in node_list}
    in_adj: dict[str, set[str]] = {n: set() for n in node_list}

    for src, dst in edges:
        if src not in out_adj or dst not in out_adj:
            continue
        if dst not in out_adj[src]:
            out_adj[src].add(dst)
            in_adj[dst].add(src)

    in_degree: dict[str, int] = {n: len(in_adj[n]) for n in node_list}
    weak_adj: dict[str, set[str]] = {n: set() for n in node_list}
    for n in node_list:
        weak_adj[n].update(out_adj.get(n, set()))
        weak_adj[n].update(in_adj.get(n, set()))

    # Weakly connected components (ignore direction for component size).
    component_id: dict[str, int] = {}
    component_sizes: dict[int, int] = {}
    cid = 0
    for n in node_list:
        if n in component_id:
            continue
        cid += 1
        size = 0
        q = deque([n])
        component_id[n] = cid
        while q:
            cur = q.popleft()
            size += 1
            for nb in weak_adj.get(cur, ()):
                if nb in component_id:
                    continue
                component_id[nb] = cid
                q.append(nb)
        component_sizes[cid] = size

    largest_component = max(component_sizes.values(), default=0)

    # Multi-source BFS from key nodes for directed distance-to-keys.
    dist_from_key_out = _multi_source_bfs(out_adj, key_nodes)
    dist_from_key_in = _multi_source_bfs(in_adj, key_nodes)
    dist_to_key: dict[str, int] = {}
    if key_nodes:
        for n in node_list:
            a = dist_from_key_out.get(n)
            b = dist_from_key_in.get(n)
            if a is None and b is None:
                continue
            if a is None:
                dist_to_key[n] = b  # type: ignore[assignment]
            elif b is None:
                dist_to_key[n] = a
            else:
                dist_to_key[n] = min(a, b)

    betweenness = _betweenness_centrality_directed(out_adj)
    closeness = _closeness_centrality_directed(out_adj)

    top_n = max(1, int(math.ceil(len(node_list) * 0.10)))

    def _top(items: Iterable[tuple[str, float | int]], *, reverse: bool = True) -> list[str]:
        return [k for k, _ in sorted(items, key=lambda kv: kv[1], reverse=reverse)[:top_n]]

    coupling_counts: dict[str, int] = {}
    for n in node_list:
        coupling_counts[n] = len(out_adj.get(n, set()) & original_nodes)
    coupling_items = [(n, c) for n, c in coupling_counts.items() if c > 0]
    coupling_top = _top(coupling_items) if coupling_items else []

    top_inward = _top(in_degree.items())
    top_bridge = _top(betweenness.items())
    top_core = _top(closeness.items())

    # Tangential citations: only among the paper's original refs.
    max_in_deg = max(in_degree.values(), default=0) or 1
    max_cites = max(cite_counts_by_ref_id.values(), default=0) or 1
    tangential_scores: dict[str, float] = {}
    for node_id in original_nodes:
        ref_id = original_ref_id_by_node.get(node_id)
        cite_ct = cite_counts_by_ref_id.get(ref_id or "", 0)
        comp_size = component_sizes.get(component_id.get(node_id, -1), 1)
        comp_ratio = comp_size / max(1, largest_component)
        dist = dist_to_key.get(node_id)
        if dist is None:
            dist_score = 1.0
        else:
            dist_score = min(6, dist) / 6.0
        score = 0.60 * dist_score + 0.25 * (1.0 - comp_ratio) + 0.10 * (1.0 - (in_degree[node_id] / max_in_deg)) + 0.05 * (
            1.0 - (cite_ct / max_cites)
        )
        tangential_scores[node_id] = score

    # pick top 10% "most tangential" among original refs with score
    tangential_sorted = sorted(tangential_scores.items(), key=lambda kv: kv[1], reverse=True)
    tangential_top = [nid for nid, _ in tangential_sorted[: max(1, int(math.ceil(len(tangential_sorted) * 0.10)))]]

    return {
        "network": {
            "node_count": len(node_list),
            "edge_count": len(edges),
            "largest_cluster_size": largest_component,
        },
        "categories": {
            "highly_connected": top_inward,
            "bridge_papers": top_bridge,
            "core_papers": top_core,
            "bibliographic_coupling": coupling_top,
            "tangential_citations": tangential_top,
        },
    }


def _betweenness_centrality_undirected(adj: dict[str, set[str]]) -> dict[str, float]:
    """
    Brandes betweenness centrality for an unweighted, undirected graph.
    Returns raw (not normalized) scores.
    """
    betw: dict[str, float] = {v: 0.0 for v in adj}
    for s in adj:
        stack: list[str] = []
        pred: dict[str, list[str]] = defaultdict(list)
        sigma: dict[str, float] = defaultdict(float)
        sigma[s] = 1.0
        dist: dict[str, int] = {s: 0}

        q: deque[str] = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj.get(v, ()):
                if w not in dist:
                    q.append(w)
                    dist[w] = dist[v] + 1
                if dist.get(w) == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        delta: dict[str, float] = defaultdict(float)
        while stack:
            w = stack.pop()
            for v in pred.get(w, ()):
                if sigma[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                betw[w] += delta[w]

    # Undirected graphs count each pair twice.
    for v in betw:
        betw[v] *= 0.5
    return betw


def _closeness_centrality_undirected(adj: dict[str, set[str]]) -> dict[str, float]:
    closeness: dict[str, float] = {}
    n = len(adj)
    for s in adj:
        dist: dict[str, int] = {s: 0}
        q: deque[str] = deque([s])
        while q:
            v = q.popleft()
            for w in adj.get(v, ()):
                if w in dist:
                    continue
                dist[w] = dist[v] + 1
                q.append(w)
        reachable = len(dist)
        if reachable <= 1:
            closeness[s] = 0.0
            continue
        total_dist = sum(dist.values())
        if total_dist <= 0:
            closeness[s] = 0.0
            continue
        # Standard closeness with a connectivity penalty.
        base = (reachable - 1) / total_dist
        closeness[s] = base * ((reachable - 1) / max(1, n - 1))
    return closeness


def _multi_source_bfs(adj: dict[str, set[str]], sources: set[str]) -> dict[str, int]:
    dist: dict[str, int] = {}
    if not sources:
        return dist
    dq: deque[str] = deque()
    for s in sources:
        if s not in adj:
            continue
        dist[s] = 0
        dq.append(s)
    while dq:
        cur = dq.popleft()
        for nb in adj.get(cur, ()):
            if nb in dist:
                continue
            dist[nb] = dist[cur] + 1
            dq.append(nb)
    return dist


def _betweenness_centrality_directed(adj: dict[str, set[str]]) -> dict[str, float]:
    """
    Brandes betweenness centrality for an unweighted, directed graph.
    Returns raw (not normalized) scores.
    """
    betw: dict[str, float] = {v: 0.0 for v in adj}
    for s in adj:
        stack: list[str] = []
        pred: dict[str, list[str]] = defaultdict(list)
        sigma: dict[str, float] = defaultdict(float)
        sigma[s] = 1.0
        dist: dict[str, int] = {s: 0}

        q: deque[str] = deque([s])
        while q:
            v = q.popleft()
            stack.append(v)
            for w in adj.get(v, ()):
                if w not in dist:
                    q.append(w)
                    dist[w] = dist[v] + 1
                if dist.get(w) == dist[v] + 1:
                    sigma[w] += sigma[v]
                    pred[w].append(v)

        delta: dict[str, float] = defaultdict(float)
        while stack:
            w = stack.pop()
            for v in pred.get(w, ()):
                if sigma[w]:
                    delta[v] += (sigma[v] / sigma[w]) * (1.0 + delta[w])
            if w != s:
                betw[w] += delta[w]

    return betw


def _closeness_centrality_directed(adj: dict[str, set[str]]) -> dict[str, float]:
    closeness: dict[str, float] = {}
    n = len(adj)
    for s in adj:
        dist: dict[str, int] = {s: 0}
        q: deque[str] = deque([s])
        while q:
            v = q.popleft()
            for w in adj.get(v, ()):
                if w in dist:
                    continue
                dist[w] = dist[v] + 1
                q.append(w)
        reachable = len(dist)
        if reachable <= 1:
            closeness[s] = 0.0
            continue
        total_dist = sum(dist.values())
        if total_dist <= 0:
            closeness[s] = 0.0
            continue
        base = (reachable - 1) / total_dist
        closeness[s] = base * ((reachable - 1) / max(1, n - 1))
    return closeness


def _is_openalex_id(val: str) -> bool:
    return bool(val) and (val.startswith("https://openalex.org/") or val.startswith("https://api.openalex.org/works/") or val.startswith("W"))


def _doi_url(doi: str) -> str:
    doi_norm = normalize_doi(doi) or doi
    return f"https://doi.org/{doi_norm}"


def _nested_str(obj: dict | None, *keys: str) -> str | None:
    cur: Any = obj
    for k in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    if isinstance(cur, str) and cur.strip():
        return cur.strip()
    return None


def _extract_openalex_authors(record: dict | None, *, max_authors: int = 25) -> list[str]:
    if not isinstance(record, dict):
        return []
    raw = record.get("authorships")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        dn = item.get("display_name")
        if isinstance(dn, str) and dn.strip():
            out.append(dn.strip())
        else:
            author = item.get("author")
            if isinstance(author, dict):
                adn = author.get("display_name")
                if isinstance(adn, str) and adn.strip():
                    out.append(adn.strip())
                    continue
            ran = item.get("raw_author_name")
            if isinstance(ran, str) and ran.strip():
                out.append(ran.strip())
        if len(out) >= max_authors:
            break
    return out


def _extract_openalex_venue(record: dict | None) -> str | None:
    hv = record.get("host_venue") if isinstance(record, dict) else None
    if isinstance(hv, dict):
        dn = hv.get("display_name")
        if isinstance(dn, str) and dn.strip():
            return dn.strip()
    return None


def _extract_openalex_biblio(record: dict | None) -> dict[str, str | None]:
    biblio = record.get("biblio") if isinstance(record, dict) else None
    if not isinstance(biblio, dict):
        return {"volume": None, "issue": None, "pages": None}
    volume = str(biblio.get("volume") or "").strip() or None
    issue = str(biblio.get("issue") or "").strip() or None
    first_page = str(biblio.get("first_page") or "").strip() or None
    last_page = str(biblio.get("last_page") or "").strip() or None
    pages = None
    if first_page and last_page and first_page != last_page:
        pages = f"{first_page}–{last_page}"
    elif first_page:
        pages = first_page
    return {"volume": volume, "issue": issue, "pages": pages}


def _pick_official_url(*, doi: str | None, record: dict | None) -> str | None:
    doi_norm = normalize_doi(doi or "")
    if doi_norm:
        return _doi_url(doi_norm)
    # Prefer publisher landing pages when DOI is missing.
    url = _nested_str(record, "primary_location", "landing_page_url") or _nested_str(record, "best_oa_location", "landing_page_url")
    if url:
        return url
    oa_url = _nested_str(record, "open_access", "oa_url")
    return oa_url


def _pick_open_access_pdf(*, record: dict | None) -> str | None:
    url = _nested_str(record, "best_oa_location", "pdf_url") or _nested_str(record, "primary_location", "pdf_url")
    if url:
        return url
    oa_url = _nested_str(record, "open_access", "oa_url")
    if oa_url and oa_url.lower().endswith(".pdf"):
        return oa_url
    return None


def _apa_author_name(name: str) -> str:
    cleaned = " ".join((name or "").replace("\u00a0", " ").split()).strip()
    if not cleaned:
        return ""
    if "," in cleaned:
        last, rest = cleaned.split(",", 1)
        last = last.strip()
        given = [p for p in rest.strip().split() if p]
        initials = [f"{p[0].upper()}." for p in given if p and p[0].isalpha()]
        return f"{last}, {' '.join(initials)}".strip()
    parts = cleaned.split()
    if len(parts) == 1:
        return cleaned
    last = parts[-1]
    given = parts[:-1]
    initials = [f"{p[0].upper()}." for p in given if p and p[0].isalpha()]
    return f"{last}, {' '.join(initials)}".strip()


def _apa_author_list(names: list[str]) -> str | None:
    formatted = [a for a in (_apa_author_name(n) for n in names) if a]
    if not formatted:
        return None
    if len(formatted) == 1:
        return formatted[0]
    if len(formatted) == 2:
        return f"{formatted[0]} & {formatted[1]}"
    if len(formatted) <= 6:
        return ", ".join(formatted[:-1]) + f", & {formatted[-1]}"
    return ", ".join(formatted[:5]) + ", et al."


def _format_apa_base(meta: dict[str, Any]) -> str:
    authors = meta.get("authors") if isinstance(meta.get("authors"), list) else []
    author_str = _apa_author_list([str(a) for a in authors if isinstance(a, str)]) or "Unknown author"
    year = meta.get("year")
    year_str = str(year) if isinstance(year, int) and year > 0 else "n.d."
    title = str(meta.get("title") or "").strip() or "Untitled"
    venue = str(meta.get("venue") or "").strip()
    volume = str(meta.get("volume") or "").strip()
    issue = str(meta.get("issue") or "").strip()
    pages = str(meta.get("pages") or "").strip()

    parts: list[str] = [f"{author_str} ({year_str}). {title}."]
    if venue:
        ven = venue
        if volume:
            ven += f", {volume}"
            if issue:
                ven += f"({issue})"
            if pages:
                ven += f", {pages}"
        elif pages:
            ven += f", {pages}"
        parts.append(f"{ven}.")
    return " ".join(parts).replace("..", ".").strip()


def _build_reference_master_list(
    *,
    settings: Settings,
    openalex: OpenAlexClient,
    metrics: dict[str, Any],
    key_ref_ids: list[str],
    verified_original_refs: list[ReferenceEntry],
    resolved_by_ref_id: dict[str, ResolvedWorkLike],
    node_id_for_original_ref: Callable[[str], str],
) -> tuple[dict[str, dict], list[dict], list[dict], dict[str, Any]]:
    trunc: dict[str, Any] = {
        "skipped_openalex_meta_fetches": 0,
        "key_refs_total": len(key_ref_ids),
        "key_refs_shown": 0,
    }

    categories = metrics.get("categories") if isinstance(metrics.get("categories"), dict) else {}

    def _take(ids: Any, *, limit: int) -> list[str]:
        if not isinstance(ids, list):
            return []
        out: list[str] = []
        for item in ids:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
            if len(out) >= limit:
                break
        return out

    # Clip category lists to keep the report readable and bounded.
    cat_nodes = {
        "highly_connected": _take(categories.get("highly_connected"), limit=settings.deep_analysis_display_max_per_category),
        "bridge_papers": _take(categories.get("bridge_papers"), limit=settings.deep_analysis_display_max_per_category),
        "core_papers": _take(categories.get("core_papers"), limit=settings.deep_analysis_display_max_per_category),
        "bibliographic_coupling": _take(
            categories.get("bibliographic_coupling"), limit=settings.deep_analysis_display_max_per_category
        ),
        "tangential_citations": _take(categories.get("tangential_citations"), limit=settings.deep_analysis_display_max_per_category),
    }

    original_node_by_ref_id = {ref.ref_id: node_id_for_original_ref(ref.ref_id) for ref in verified_original_refs}
    original_ref_id_by_node = {v: k for k, v in original_node_by_ref_id.items()}
    original_ref_entry_by_ref_id = {ref.ref_id: ref for ref in verified_original_refs}

    key_nodes_all = [original_node_by_ref_id[rid] for rid in key_ref_ids if rid in original_node_by_ref_id]
    key_nodes = key_nodes_all[: settings.deep_analysis_display_max_key_refs]
    trunc["key_refs_shown"] = len(key_nodes)

    selected_node_ids: list[str] = []
    selected_node_ids.extend(key_nodes)
    for group_ids in cat_nodes.values():
        selected_node_ids.extend(group_ids)

    # Unique while preserving order.
    seen_nodes: set[str] = set()
    ordered_nodes: list[str] = []
    for nid in selected_node_ids:
        if nid in seen_nodes:
            continue
        seen_nodes.add(nid)
        ordered_nodes.append(nid)

    needed_openalex_ids = sorted({nid for nid in ordered_nodes if _is_openalex_id(nid) and nid not in original_ref_id_by_node})
    openalex_summaries = _fetch_openalex_summaries(
        openalex=openalex,
        openalex_ids=needed_openalex_ids,
        max_workers=settings.deep_analysis_max_workers,
        max_items=settings.deep_analysis_display_max_openalex_fetches,
    )
    if len(openalex_summaries) < len(needed_openalex_ids):
        trunc["skipped_openalex_meta_fetches"] = len(needed_openalex_ids) - len(openalex_summaries)

    # Build a canonical reference set (dedupe by DOI when available).
    node_id_to_key: dict[str, str] = {}
    meta_by_key: dict[str, dict[str, Any]] = {}

    def _canonical_key(*, doi: str | None, openalex_id: str | None, node_id: str) -> str:
        doi_norm = normalize_doi(doi or "")
        if doi_norm:
            return f"doi:{doi_norm}"
        if openalex_id:
            return f"oa:{openalex_id.strip()}"
        return f"node:{node_id}"

    def _merge_meta(dst: dict[str, Any], src: dict[str, Any]) -> dict[str, Any]:
        for field in ["doi", "title", "venue", "official_url", "oa_pdf_url", "openalex_id", "volume", "issue", "pages"]:
            if not dst.get(field) and src.get(field):
                dst[field] = src.get(field)
        # Prefer a concrete year if missing.
        if not dst.get("year") and src.get("year"):
            dst["year"] = src.get("year")
        # Prefer fuller author lists.
        dst_auth = dst.get("authors") if isinstance(dst.get("authors"), list) else []
        src_auth = src.get("authors") if isinstance(src.get("authors"), list) else []
        if (not dst_auth) and src_auth:
            dst["authors"] = src_auth
        dst["in_paper"] = bool(dst.get("in_paper")) or bool(src.get("in_paper"))
        dst["is_key"] = bool(dst.get("is_key")) or bool(src.get("is_key"))
        if src.get("ref_id") and not dst.get("ref_id"):
            dst["ref_id"] = src.get("ref_id")
        return dst

    for node_id in ordered_nodes:
        ref_id = original_ref_id_by_node.get(node_id)
        meta: dict[str, Any] = {
            "node_id": node_id,
            "openalex_id": node_id if _is_openalex_id(node_id) else None,
            "doi": None,
            "title": None,
            "year": None,
            "venue": None,
            "authors": [],
            "volume": None,
            "issue": None,
            "pages": None,
            "official_url": None,
            "oa_pdf_url": None,
            "in_paper": bool(ref_id),
            "is_key": bool(ref_id) and (ref_id in set(key_ref_ids)),
            "ref_id": ref_id,
        }

        if ref_id:
            w = resolved_by_ref_id.get(ref_id)
            record = w.openalex_record if w and isinstance(w.openalex_record, dict) else None
            if w:
                meta["doi"] = normalize_doi(w.doi or "") or meta["doi"]
                meta["title"] = (w.title or "").strip() or meta["title"]
                meta["year"] = w.year or meta["year"]
                journal = getattr(w, "journal", None)
                if isinstance(journal, str) and journal.strip():
                    meta["venue"] = journal.strip()
                if isinstance(w.openalex_id, str) and w.openalex_id.strip():
                    meta["openalex_id"] = w.openalex_id.strip()
            if record:
                meta["doi"] = normalize_doi(str(record.get("doi") or "")) or meta["doi"]
                meta["title"] = str(record.get("title") or record.get("display_name") or meta["title"] or "").strip() or meta["title"]
                meta["year"] = record.get("publication_year") if isinstance(record.get("publication_year"), int) else meta["year"]
                meta["venue"] = _extract_openalex_venue(record) or meta["venue"]
                meta["authors"] = _extract_openalex_authors(record) or meta["authors"]
                b = _extract_openalex_biblio(record)
                meta["volume"] = b.get("volume") or meta["volume"]
                meta["issue"] = b.get("issue") or meta["issue"]
                meta["pages"] = b.get("pages") or meta["pages"]
                meta["official_url"] = _pick_official_url(doi=meta.get("doi"), record=record) or meta["official_url"]
                meta["oa_pdf_url"] = _pick_open_access_pdf(record=record) or meta["oa_pdf_url"]

            # If we still have no author list, fall back to the parsed first author.
            if not meta["authors"]:
                entry = original_ref_entry_by_ref_id.get(ref_id)
                if entry and entry.first_author:
                    meta["authors"] = [entry.first_author.title()]

        else:
            # Non-paper nodes: prefer OpenAlex metadata when available.
            summ = openalex_summaries.get(node_id)
            if isinstance(summ, dict):
                meta["openalex_id"] = str(summ.get("openalex_id") or node_id).strip() or meta["openalex_id"]
                meta["doi"] = normalize_doi(str(summ.get("doi") or "")) or meta["doi"]
                meta["title"] = str(summ.get("title") or "").strip() or meta["title"]
                meta["year"] = summ.get("year") if isinstance(summ.get("year"), int) else meta["year"]
                meta["venue"] = str(summ.get("venue") or "").strip() or meta["venue"]
                if isinstance(summ.get("authors"), list):
                    meta["authors"] = [str(a).strip() for a in summ.get("authors") if isinstance(a, str) and a.strip()]
                meta["volume"] = str(summ.get("volume") or "").strip() or meta["volume"]
                meta["issue"] = str(summ.get("issue") or "").strip() or meta["issue"]
                meta["pages"] = str(summ.get("pages") or "").strip() or meta["pages"]
                meta["official_url"] = str(summ.get("official_url") or "").strip() or meta["official_url"]
                meta["oa_pdf_url"] = str(summ.get("oa_pdf_url") or "").strip() or meta["oa_pdf_url"]

        key = _canonical_key(doi=meta.get("doi"), openalex_id=meta.get("openalex_id"), node_id=node_id)
        node_id_to_key[node_id] = key
        if key in meta_by_key:
            meta_by_key[key] = _merge_meta(meta_by_key[key], meta)
        else:
            meta_by_key[key] = meta

    def _keys_for_node_list(nodes: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for nid in nodes:
            key = node_id_to_key.get(nid)
            if not key or key in seen:
                continue
            seen.add(key)
            out.append(key)
        return out

    key_keys = _keys_for_node_list(key_nodes)
    tangential_keys = _keys_for_node_list(cat_nodes.get("tangential_citations") or [])
    important_keys = _keys_for_node_list(cat_nodes.get("highly_connected") or [])
    bridge_keys = _keys_for_node_list(cat_nodes.get("bridge_papers") or [])
    core_keys = _keys_for_node_list(cat_nodes.get("core_papers") or [])
    coupling_keys = _keys_for_node_list(cat_nodes.get("bibliographic_coupling") or [])

    # Build disjoint master reference groups (no duplicates in the full list).
    assigned: set[str] = set()

    def _assign_group(keys_in: list[str]) -> list[str]:
        out: list[str] = []
        for k in keys_in:
            if k in assigned:
                continue
            assigned.add(k)
            out.append(k)
        return out

    master_group_defs: list[dict[str, Any]] = []
    master_group_defs.append(
        {"key": "key_refs", "title": "Key references (from your paper)", "keys": _assign_group(key_keys)}
    )
    master_group_defs.append(
        {
            "key": "tangential_citations",
            "title": "Citations to revisit",
            "keys": _assign_group([k for k in tangential_keys if meta_by_key.get(k, {}).get("in_paper")]),
        }
    )
    master_group_defs.append(
        {
            "key": "in_paper_supporting",
            "title": "Strong supporting works you already cite",
            "keys": _assign_group(
                [k for k in (important_keys + bridge_keys + core_keys) if meta_by_key.get(k, {}).get("in_paper")]
            ),
        }
    )
    master_group_defs.append(
        {
            "key": "suggested_important",
            "title": "Suggested additions: important works",
            "keys": _assign_group([k for k in important_keys if not meta_by_key.get(k, {}).get("in_paper")]),
        }
    )
    master_group_defs.append(
        {
            "key": "suggested_connectors",
            "title": "Suggested additions: works that connect ideas",
            "keys": _assign_group([k for k in bridge_keys if not meta_by_key.get(k, {}).get("in_paper")]),
        }
    )
    master_group_defs.append(
        {
            "key": "suggested_core",
            "title": "Suggested additions: core background",
            "keys": _assign_group([k for k in core_keys if not meta_by_key.get(k, {}).get("in_paper")]),
        }
    )
    master_group_defs.append(
        {
            "key": "bibliographic_coupling",
            "title": "Works that cite many of your references",
            "keys": _assign_group(coupling_keys),
        }
    )

    leftovers = [k for k in meta_by_key.keys() if k not in assigned]
    if leftovers:
        master_group_defs.append({"key": "other", "title": "Other relevant works", "keys": _assign_group(leftovers)})

    # Assign stable, compact in-text ids.
    rid_by_key: dict[str, str] = {}
    n = 0
    for group in master_group_defs:
        for k in group["keys"]:
            if k in rid_by_key:
                continue
            n += 1
            rid_by_key[k] = f"R{n}"

    references_by_rid: dict[str, dict] = {}
    for key, meta in meta_by_key.items():
        rid = rid_by_key.get(key)
        if not rid:
            continue
        official_url = meta.get("official_url")
        if not official_url and meta.get("doi"):
            official_url = _doi_url(str(meta.get("doi")))
        references_by_rid[rid] = {
            "rid": rid,
            "ref_id": meta.get("ref_id"),
            "in_paper": bool(meta.get("in_paper")),
            "is_key": bool(meta.get("is_key")),
            "title": meta.get("title"),
            "year": meta.get("year"),
            "venue": meta.get("venue"),
            "authors": meta.get("authors"),
            "volume": meta.get("volume"),
            "issue": meta.get("issue"),
            "pages": meta.get("pages"),
            "doi": meta.get("doi"),
            "official_url": official_url,
            "oa_pdf_url": meta.get("oa_pdf_url"),
        }
        references_by_rid[rid]["apa_base"] = _format_apa_base(references_by_rid[rid])

    reference_groups: list[dict] = []
    for group in master_group_defs:
        rids = [rid_by_key[k] for k in group["keys"] if k in rid_by_key]
        if not rids:
            continue
        reference_groups.append({"key": group["key"], "title": group["title"], "rids": rids})

    # Category-facing groups (may overlap), referenced via [R#] only.
    citation_groups: list[dict] = []
    citation_groups.append(
        {
            "key": "highly_connected",
            "title": "Important works to consider",
            "rids": [rid_by_key[k] for k in important_keys if k in rid_by_key],
        }
    )
    citation_groups.append(
        {
            "key": "bridge_papers",
            "title": "Works that can connect ideas",
            "rids": [rid_by_key[k] for k in bridge_keys if k in rid_by_key],
        }
    )
    citation_groups.append(
        {
            "key": "core_papers",
            "title": "Core background to strengthen",
            "rids": [rid_by_key[k] for k in core_keys if k in rid_by_key],
        }
    )
    citation_groups.append(
        {
            "key": "bibliographic_coupling",
            "title": "Works that cite many of your references",
            "rids": [rid_by_key[k] for k in coupling_keys if k in rid_by_key],
        }
    )
    citation_groups.append(
        {
            "key": "tangential_citations",
            "title": "Citations to revisit",
            "rids": [rid_by_key[k] for k in tangential_keys if k in rid_by_key],
        }
    )

    # Optionally show which key refs were used (keep short).
    if key_keys:
        citation_groups.insert(
            0,
            {
                "key": "key_refs",
                "title": "Key references used to build the pool",
                "rids": [rid_by_key[k] for k in key_keys if k in rid_by_key],
            },
        )

    # Drop empty groups for cleanliness.
    citation_groups = [g for g in citation_groups if g.get("rids")]

    def _ref_sort_key(rid: str) -> str:
        ref = references_by_rid.get(rid) if isinstance(references_by_rid.get(rid), dict) else {}
        apa = str(ref.get("apa_base") or "").strip()
        if apa:
            return apa.lower()
        title = str(ref.get("title") or "").strip()
        return title.lower()

    def _sort_rids(rids: list[str]) -> list[str]:
        return sorted(rids, key=_ref_sort_key)

    for group in reference_groups:
        if isinstance(group.get("rids"), list):
            group["rids"] = _sort_rids([rid for rid in group["rids"] if isinstance(rid, str)])

    return references_by_rid, reference_groups, citation_groups, trunc


def _fetch_openalex_summaries(
    *,
    openalex: OpenAlexClient,
    openalex_ids: list[str],
    max_workers: int,
    max_items: int,
) -> dict[str, dict]:
    if not openalex_ids:
        return {}
    if max_items > 0:
        openalex_ids = openalex_ids[:max_items]

    def _safe_get(openalex_id: str) -> dict | None:
        try:
            return openalex.get_work_by_id(openalex_id)
        except Exception:
            return None

    def _summarize(work: dict) -> dict:
        title = work.get("display_name") or work.get("title") or ""
        title = " ".join(str(title).split()) if isinstance(title, str) else ""
        doi = normalize_doi(str(work.get("doi") or ""))
        year = work.get("publication_year") if isinstance(work.get("publication_year"), int) else None
        venue = _extract_openalex_venue(work)
        authors = _extract_openalex_authors(work)
        b = _extract_openalex_biblio(work)
        official_url = _pick_official_url(doi=doi, record=work)
        oa_pdf_url = _pick_open_access_pdf(record=work)
        return {
            "openalex_id": work.get("id"),
            "title": title or None,
            "doi": doi,
            "year": year,
            "venue": venue,
            "authors": authors,
            "volume": b.get("volume"),
            "issue": b.get("issue"),
            "pages": b.get("pages"),
            "official_url": official_url,
            "oa_pdf_url": oa_pdf_url,
        }

    out: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, int(max_workers))) as ex:
        futures = {ex.submit(_safe_get, oid): oid for oid in openalex_ids}
        for fut in as_completed(futures):
            oid = futures[fut]
            work = fut.result()
            if not isinstance(work, dict):
                continue
            out[oid] = _summarize(work)
    return out


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


def _extract_section_order(text: str) -> list[str]:
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


def _build_suggestions(
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
        excerpt = excerpt[: settings.deep_analysis_paper_excerpt_max_chars] + "…"

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
            note = note[:240] + "…"
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

from __future__ import annotations

import math
from collections import defaultdict, deque
from collections.abc import Iterable
from typing import Any


def compute_network_metrics(
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
        score = (
            0.60 * dist_score
            + 0.25 * (1.0 - comp_ratio)
            + 0.10 * (1.0 - (in_degree[node_id] / max_in_deg))
            + 0.05 * (1.0 - (cite_ct / max_cites))
        )
        tangential_scores[node_id] = score

    # pick top 10% "most tangential" among original refs with score
    tangential_sorted = sorted(tangential_scores.items(), key=lambda kv: kv[1], reverse=True)
    tangential_top = [
        nid
        for nid, _ in tangential_sorted[: max(1, int(math.ceil(len(tangential_sorted) * 0.10)))]
    ]

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
    """Brandes betweenness centrality for an unweighted, directed graph."""
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

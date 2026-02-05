from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any
from urllib.parse import quote_plus

from server.miscite.sources.openalex import OpenAlexClient


def _collapse_ws(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split()).strip()


def _coerce_year(value: Any) -> int:
    if isinstance(value, int):
        return value if value > 0 else 0
    if isinstance(value, str):
        raw = value.strip()
        if raw.isdigit():
            year = int(raw)
            return year if year > 0 else 0
    return 0


def _normalize_source(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return _collapse_ws(value).lower()


def _iter_source_labels(ref: dict[str, Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for key in ("source", "venue"):
        norm = _normalize_source(ref.get(key))
        if not norm or norm in seen:
            continue
        seen.add(norm)
        out.append(norm)
    return out


def _extract_openalex_work_sources(work: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    if not isinstance(work, dict):
        return out
    hv = work.get("host_venue")
    if isinstance(hv, dict):
        hv_name = _normalize_source(hv.get("display_name"))
        if hv_name:
            out.add(hv_name)
    for key in ("primary_location", "best_oa_location"):
        loc = work.get(key)
        if not isinstance(loc, dict):
            continue
        src = loc.get("source")
        if not isinstance(src, dict):
            continue
        src_name = _normalize_source(src.get("display_name"))
        if src_name:
            out.add(src_name)
    return out


def _is_openalex_id(value: str) -> bool:
    return bool(value) and (
        value.startswith("https://openalex.org/")
        or value.startswith("https://api.openalex.org/works/")
        or value.startswith("W")
    )


def _extract_openalex_authors_detailed(
    record: dict[str, Any],
    *,
    max_authors: int = 25,
    max_institutions: int = 2,
    max_affiliation_chars: int = 120,
) -> list[dict[str, str | None]]:
    raw = record.get("authorships")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str | None]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("display_name") if isinstance(item.get("display_name"), str) else None
        if not name:
            author = item.get("author")
            if isinstance(author, dict):
                name = author.get("display_name") if isinstance(author.get("display_name"), str) else None
        if not name and isinstance(item.get("raw_author_name"), str):
            name = item.get("raw_author_name")
        name = _collapse_ws(str(name or ""))
        if not name:
            continue

        author_id = None
        if isinstance(item.get("author"), dict):
            author_id = _collapse_ws(str(item["author"].get("id") or ""))
        if not author_id:
            author_id = None

        affiliation = None
        institutions = item.get("institutions")
        inst_names: list[str] = []
        if isinstance(institutions, list):
            for inst in institutions:
                if not isinstance(inst, dict):
                    continue
                dn = inst.get("display_name")
                if isinstance(dn, str) and dn.strip():
                    inst_names.append(_collapse_ws(dn))
                if len(inst_names) >= max_institutions:
                    break
        if inst_names:
            uniq: list[str] = []
            seen: set[str] = set()
            for n in inst_names:
                key = n.lower()
                if key in seen:
                    continue
                seen.add(key)
                uniq.append(n)
            affiliation = "; ".join(uniq)
        else:
            raw_affs = item.get("raw_affiliation_strings")
            if isinstance(raw_affs, list):
                for raw_aff in raw_affs:
                    if isinstance(raw_aff, str) and raw_aff.strip():
                        affiliation = _collapse_ws(raw_aff)
                        break

        if affiliation:
            if max_affiliation_chars > 0 and len(affiliation) > max_affiliation_chars:
                affiliation = affiliation[:max_affiliation_chars].rstrip() + "\u2026"
        else:
            affiliation = None

        out.append({"name": name, "affiliation": affiliation, "author_id": author_id})
        if len(out) >= max_authors:
            break
    return out


def _author_key(author: dict[str, Any]) -> str:
    if not isinstance(author, dict):
        return ""
    name = _collapse_ws(str(author.get("name") or ""))
    if not name:
        return ""
    raw_author_id = author.get("author_id")
    author_id = _collapse_ws(str(raw_author_id or "")) if raw_author_id else ""
    return author_id or name.lower()


def _degree_centrality(adj: dict[str, set[str]]) -> dict[str, float]:
    return {node: float(len(neigh)) for node, neigh in adj.items()}


def _closeness_centrality(adj: dict[str, set[str]]) -> dict[str, float]:
    from collections import deque

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


def _betweenness_centrality(adj: dict[str, set[str]]) -> dict[str, float]:
    from collections import defaultdict, deque

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


def _select_top_coupling_rids(
    *,
    coupling_rids: list[str],
    max_coupling_works: int,
    debug: dict[str, Any] | None = None,
) -> list[str]:
    if max_coupling_works <= 0:
        if isinstance(debug, dict):
            debug["coupling_rids_deduped"] = 0
            debug["coupling_rids_top"] = 0
        return []

    deduped_rids: list[str] = []
    seen: set[str] = set()
    for rid in coupling_rids:
        rid_norm = rid.strip() if isinstance(rid, str) else ""
        if not rid_norm or rid_norm in seen:
            continue
        seen.add(rid_norm)
        deduped_rids.append(rid_norm)
        if len(deduped_rids) >= max_coupling_works:
            break
    if isinstance(debug, dict):
        debug["coupling_rids_deduped"] = len(deduped_rids)
        debug["coupling_rids_top"] = len(deduped_rids)
    return deduped_rids


def _select_recent_rids(
    *,
    candidate_rids: list[str],
    references_by_rid: dict[str, dict],
    recent_years: int,
    current_year: int,
) -> list[str]:
    if recent_years <= 0:
        return list(candidate_rids)
    cutoff_year = current_year - recent_years + 1
    out: list[str] = []
    for rid in candidate_rids:
        ref = references_by_rid.get(rid)
        if not isinstance(ref, dict):
            continue
        year = _coerce_year(ref.get("year"))
        if year >= cutoff_year:
            out.append(rid)
    return out


def _cited_source_set(*, references_by_rid: dict[str, dict]) -> set[str]:
    out: set[str] = set()
    for ref in references_by_rid.values():
        if not isinstance(ref, dict):
            continue
        if not bool(ref.get("in_paper")):
            continue
        out.update(_iter_source_labels(ref))
    return out


def build_potential_reviewers_from_coupling(
    *,
    coupling_rids: list[str],
    references_by_rid: dict[str, dict],
    max_coupling_works: int = 50,
    recent_years: int = 10,
    current_year: int | None = None,
    openalex: OpenAlexClient | None = None,
    author_works_max: int = 100,
    cited_sources_override: set[str] | None = None,
    order_rule: str = "degree",
    debug: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    if not coupling_rids or not references_by_rid:
        return []

    order_rule = (order_rule or "degree").strip().lower()
    if order_rule not in {"degree", "closeness", "betweenness"}:
        order_rule = "degree"

    if isinstance(debug, dict):
        debug["coupling_rids_total"] = len([rid for rid in coupling_rids if isinstance(rid, str) and rid.strip()])
        debug["order_rule"] = order_rule

    top_coupling_rids = _select_top_coupling_rids(
        coupling_rids=coupling_rids,
        max_coupling_works=max_coupling_works,
        debug=debug,
    )
    if not top_coupling_rids:
        return []

    year_now = _coerce_year(current_year)
    if year_now <= 0:
        year_now = date.today().year

    cutoff_year = year_now - recent_years + 1 if recent_years > 0 else 0
    if isinstance(debug, dict):
        debug["recent_years"] = recent_years
        debug["current_year"] = year_now
        debug["cutoff_year"] = cutoff_year

    recent_rids = _select_recent_rids(
        candidate_rids=top_coupling_rids,
        references_by_rid=references_by_rid,
        recent_years=recent_years,
        current_year=year_now,
    )
    if not recent_rids:
        if isinstance(debug, dict):
            debug["recent_rids"] = 0
        return []
    if isinstance(debug, dict):
        debug["recent_rids"] = len(recent_rids)

    cited_sources = cited_sources_override or _cited_source_set(references_by_rid=references_by_rid)
    if isinstance(debug, dict):
        debug["cited_sources_count"] = len(cited_sources)
        if cited_sources:
            sample = sorted(cited_sources)[:10]
            debug["cited_sources_sample"] = sample
    if not cited_sources:
        return []

    if openalex is None:
        if isinstance(debug, dict):
            debug["author_work_lookups"] = 0
            debug["authors_with_cited_source"] = 0
            debug["reviewers"] = 0
        return []

    people: dict[str, dict[str, Any]] = {}
    works_missing_authors = 0

    coupling_openalex_lookups = 0
    coupling_openalex_results = 0
    work_author_cache: dict[str, list[dict[str, Any]]] = {}
    work_record_cache: dict[str, dict[str, Any] | None] = {}

    def _candidate_openalex_id(rid: str, ref: dict[str, Any] | None) -> str | None:
        if isinstance(ref, dict):
            oa = ref.get("openalex_id")
            if isinstance(oa, str) and _is_openalex_id(oa):
                return oa
        if _is_openalex_id(rid):
            return rid
        return None

    def _get_work_record(oa_id: str) -> dict[str, Any] | None:
        if oa_id in work_record_cache:
            return work_record_cache[oa_id]
        if not openalex:
            work_record_cache[oa_id] = None
            return None
        nonlocal coupling_openalex_lookups, coupling_openalex_results
        coupling_openalex_lookups += 1
        work = openalex.get_work_by_id(oa_id)
        if isinstance(work, dict):
            coupling_openalex_results += 1
            work_record_cache[oa_id] = work
            return work
        work_record_cache[oa_id] = None
        return None

    def _get_work_authors(rid: str) -> list[dict[str, Any]]:
        if rid in work_author_cache:
            return work_author_cache[rid]
        ref = references_by_rid.get(rid)
        authors = ref.get("authors_detailed") if isinstance(ref, dict) else None
        if not isinstance(authors, list) or not authors:
            authors = []
            oa_id = _candidate_openalex_id(rid, ref if isinstance(ref, dict) else None)
            if oa_id:
                work = _get_work_record(oa_id)
                if isinstance(work, dict):
                    authors = _extract_openalex_authors_detailed(work)
                    if isinstance(ref, dict) and authors:
                        ref["authors_detailed"] = authors
        work_author_cache[rid] = authors if isinstance(authors, list) else []
        return work_author_cache[rid]

    coauthor_adj: dict[str, set[str]] = {}
    for rid in top_coupling_rids:
        if not isinstance(rid, str):
            continue
        authors = _get_work_authors(rid)
        if not authors:
            continue
        keys: list[str] = []
        seen_keys: set[str] = set()
        for author in authors:
            key = _author_key(author)
            if not key or key in seen_keys:
                continue
            seen_keys.add(key)
            keys.append(key)
            coauthor_adj.setdefault(key, set())
        for i, a in enumerate(keys):
            for b in keys[i + 1 :]:
                coauthor_adj.setdefault(a, set()).add(b)
                coauthor_adj.setdefault(b, set()).add(a)

    degree_scores = _degree_centrality(coauthor_adj)
    closeness_scores = _closeness_centrality(coauthor_adj)
    betweenness_scores = _betweenness_centrality(coauthor_adj)
    score_map = {
        "degree": degree_scores,
        "closeness": closeness_scores,
        "betweenness": betweenness_scores,
    }
    selected_scores = score_map.get(order_rule, degree_scores)

    for rid in recent_rids:
        if not isinstance(rid, str):
            continue
        ref = references_by_rid.get(rid) if isinstance(references_by_rid.get(rid), dict) else None
        year = _coerce_year(ref.get("year")) if isinstance(ref, dict) else 0
        authors = ref.get("authors_detailed") if isinstance(ref, dict) else None
        if not isinstance(authors, list) or not authors or year <= 0:
            oa_id = _candidate_openalex_id(rid, ref if isinstance(ref, dict) else None)
            if oa_id:
                work = _get_work_record(oa_id)
                if isinstance(work, dict):
                    if year <= 0 and isinstance(work.get("publication_year"), int):
                        year = int(work.get("publication_year"))
                        if isinstance(ref, dict):
                            ref["year"] = year
                    if not isinstance(authors, list) or not authors:
                        authors = _extract_openalex_authors_detailed(work)
                        if isinstance(ref, dict) and authors:
                            ref["authors_detailed"] = authors
        if not isinstance(authors, list) or not authors:
            works_missing_authors += 1
            continue
        for author in authors:
            if not isinstance(author, dict):
                continue
            name = _collapse_ws(str(author.get("name") or ""))
            if not name:
                continue
            raw_author_id = author.get("author_id")
            author_id = _collapse_ws(str(raw_author_id or "")) if raw_author_id else ""
            key = author_id or name.lower()

            affiliation = _collapse_ws(str(author.get("affiliation") or ""))
            if not affiliation:
                affiliation = ""

            entry = people.get(key)
            if not entry:
                entry = {
                    "name": name,
                    "affiliations": Counter(),
                    "latest_year": year,
                    "has_cited_source_publication": False,
                    "author_id": author_id,
                    "author_key": key,
                }
                people[key] = entry
            if len(name) > len(str(entry.get("name") or "")):
                entry["name"] = name
            if affiliation:
                entry["affiliations"][affiliation] += 1
            if year and int(entry.get("latest_year") or 0) < year:
                entry["latest_year"] = year

    sortable: list[tuple[float, int, str, str, dict[str, str]]] = []
    authors_with_cited_source = 0
    author_work_lookups = 0
    author_work_results = 0
    authors_missing_id = 0
    total_author_works = 0
    if isinstance(debug, dict):
        debug["authors_seen"] = len(people)

    for entry in people.values():
        author_id = _collapse_ws(str(entry.get("author_id") or ""))
        if not author_id:
            authors_missing_id += 1
            continue
        author_work_lookups += 1
        works = openalex.list_author_works(author_id, rows=author_works_max)
        if works:
            author_work_results += 1
            total_author_works += len(works)
        has_overlap = False
        for work in works:
            if not isinstance(work, dict):
                continue
            if _extract_openalex_work_sources(work) & cited_sources:
                has_overlap = True
                break
        if not has_overlap:
            continue
        entry["has_cited_source_publication"] = True
        authors_with_cited_source += 1
        name = _collapse_ws(str(entry.get("name") or ""))
        if not name:
            continue
        affiliations = entry.get("affiliations")
        affiliation = ""
        if isinstance(affiliations, Counter) and affiliations:
            affiliation = affiliations.most_common(1)[0][0]
        year = int(entry.get("latest_year") or 0)
        q = f"{name} {affiliation}".strip() if affiliation else name
        author_key = str(entry.get("author_key") or "")
        score = float(selected_scores.get(author_key, 0.0))
        sortable.append(
            (
                score,
                year,
                name.lower(),
                affiliation.lower(),
                {
                    "name": name,
                    "affiliation": affiliation,
                    "google_search_url": f"https://www.google.com/search?q={quote_plus(q)}",
                },
            )
        )

    sortable.sort(key=lambda item: (-item[0], -item[1], item[2], item[3]))
    reviewers = [item[4] for item in sortable]
    if isinstance(debug, dict):
        debug["works_missing_authors"] = works_missing_authors
        debug["authors_seen"] = len(people)
        debug["authors_missing_id"] = authors_missing_id
        debug["author_work_lookups"] = author_work_lookups
        debug["author_work_results"] = author_work_results
        debug["author_work_total"] = total_author_works
        debug["coupling_work_lookups"] = coupling_openalex_lookups
        debug["coupling_work_results"] = coupling_openalex_results
        debug["authors_with_cited_source"] = authors_with_cited_source
        debug["reviewers"] = len(reviewers)
    return reviewers

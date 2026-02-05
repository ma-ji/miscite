from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from server.miscite.analysis.deep_analysis.secondary import is_secondary_reference
from server.miscite.analysis.shared.excluded_sources import load_excluded_sources, matches_excluded_source
from server.miscite.analysis.deep_analysis.types import ResolvedWorkLike
from server.miscite.analysis.parse.citation_parsing import ReferenceEntry
from server.miscite.analysis.shared.normalize import normalize_doi
from server.miscite.core.config import Settings
from server.miscite.sources.openalex import OpenAlexClient


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


def _collapse_ws(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split()).strip()


def _clip_text(text: str | None, *, max_chars: int) -> str | None:
    if text is None:
        return None
    cleaned = _collapse_ws(text)
    if not cleaned:
        return None
    if max_chars <= 0:
        return None
    if len(cleaned) > max_chars:
        return cleaned[:max_chars] + "\u2026"
    return cleaned


def _extract_openalex_abstract(record: dict | None) -> str | None:
    if not isinstance(record, dict):
        return None
    inv = record.get("abstract_inverted_index")
    if not isinstance(inv, dict) or not inv:
        return None
    pos_to_word: dict[int, str] = {}
    max_pos = -1
    for word, positions in inv.items():
        if not isinstance(positions, list):
            continue
        for p in positions:
            if not isinstance(p, int):
                continue
            pos_to_word[p] = str(word)
            max_pos = max(max_pos, p)
    if max_pos < 0:
        return None
    words = [pos_to_word.get(i, "") for i in range(max_pos + 1)]
    abstract = " ".join(w for w in words if w)
    return abstract.strip() or None


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


def _extract_openalex_authors_detailed(
    record: dict | None,
    *,
    max_authors: int = 25,
    max_institutions: int = 2,
    max_affiliation_chars: int = 120,
) -> list[dict[str, str | None]]:
    if not isinstance(record, dict):
        return []
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


def _extract_openalex_venue(record: dict | None) -> str | None:
    hv = record.get("host_venue") if isinstance(record, dict) else None
    if isinstance(hv, dict):
        dn = hv.get("display_name")
        if isinstance(dn, str) and dn.strip():
            return dn.strip()
    return None


def _extract_openalex_publisher(record: dict | None) -> str | None:
    hv = record.get("host_venue") if isinstance(record, dict) else None
    if isinstance(hv, dict):
        pub = hv.get("publisher")
        if isinstance(pub, str) and pub.strip():
            return pub.strip()
    return None


def _extract_openalex_source_name(record: dict | None) -> str | None:
    if not isinstance(record, dict):
        return None
    for key in ("primary_location", "best_oa_location"):
        loc = record.get(key)
        if not isinstance(loc, dict):
            continue
        src = loc.get("source")
        if not isinstance(src, dict):
            continue
        dn = src.get("display_name")
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
        pages = f"{first_page}\u2013{last_page}"
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


def _is_meaningful_meta(meta: dict[str, Any]) -> bool:
    title = _collapse_ws(str(meta.get("title") or ""))
    if not title:
        return False
    if title.lower() in {"untitled", "unknown title", "title unknown", "n/a", "na"}:
        return False
    authors = meta.get("authors") if isinstance(meta.get("authors"), list) else []
    has_authors = any(_collapse_ws(str(a)) for a in authors if isinstance(a, str))
    year = meta.get("year")
    has_year = isinstance(year, int) and year > 0
    venue = _collapse_ws(str(meta.get("venue") or ""))
    has_venue = bool(venue)
    doi = _collapse_ws(str(meta.get("doi") or ""))
    has_doi = bool(doi)
    return has_authors or has_year or has_venue or has_doi


def build_reference_master_list(
    *,
    settings: Settings,
    openalex: OpenAlexClient,
    metrics: dict[str, Any],
    key_ref_ids: list[str],
    verified_original_refs: list[ReferenceEntry],
    resolved_by_ref_id: dict[str, ResolvedWorkLike],
    node_id_for_original_ref: Callable[[str], str],
    extra_node_ids: list[str] | None = None,
) -> tuple[dict[str, dict], list[dict], list[dict], dict[str, Any], dict[str, str]]:
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
    # Always include the paper's verified references so subsection graphs can refer to them.
    selected_node_ids.extend([node_id_for_original_ref(ref.ref_id) for ref in verified_original_refs])
    selected_node_ids.extend(key_nodes)
    for group_ids in cat_nodes.values():
        selected_node_ids.extend(group_ids)
    if extra_node_ids:
        selected_node_ids.extend([nid for nid in extra_node_ids if isinstance(nid, str) and nid.strip()])

    # Unique while preserving order.
    seen_nodes: set[str] = set()
    ordered_nodes: list[str] = []
    for nid in selected_node_ids:
        if nid in seen_nodes:
            continue
        seen_nodes.add(nid)
        ordered_nodes.append(nid)

    needed_openalex_ids: list[str] = []
    seen_openalex_ids: set[str] = set()
    for nid in ordered_nodes:
        if not isinstance(nid, str):
            continue
        nid = nid.strip()
        if not nid:
            continue
        if nid in original_ref_id_by_node:
            continue
        if not _is_openalex_id(nid):
            continue
        if nid in seen_openalex_ids:
            continue
        seen_openalex_ids.add(nid)
        needed_openalex_ids.append(nid)
    openalex_summaries = _fetch_openalex_summaries(
        openalex=openalex,
        openalex_ids=needed_openalex_ids,
        max_workers=settings.deep_analysis_max_workers,
        max_items=settings.deep_analysis_display_max_openalex_fetches,
        abstract_max_chars=settings.deep_analysis_abstract_max_chars,
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
        for field in [
            "doi",
            "title",
            "venue",
            "publisher",
            "source",
            "official_url",
            "oa_pdf_url",
            "openalex_id",
            "volume",
            "issue",
            "pages",
            "abstract",
            "type",
            "type_crossref",
            "genre",
        ]:
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
        dst_auth_d = dst.get("authors_detailed") if isinstance(dst.get("authors_detailed"), list) else []
        src_auth_d = src.get("authors_detailed") if isinstance(src.get("authors_detailed"), list) else []
        if (not dst_auth_d) and src_auth_d:
            dst["authors_detailed"] = src_auth_d
        dst["in_paper"] = bool(dst.get("in_paper")) or bool(src.get("in_paper"))
        dst["is_key"] = bool(dst.get("is_key")) or bool(src.get("is_key"))
        if src.get("ref_id") and not dst.get("ref_id"):
            dst["ref_id"] = src.get("ref_id")
        return dst

    key_ref_id_set = set(key_ref_ids)

    for node_id in ordered_nodes:
        ref_id = original_ref_id_by_node.get(node_id)
        meta: dict[str, Any] = {
            "node_id": node_id,
            "openalex_id": node_id if _is_openalex_id(node_id) else None,
            "doi": None,
            "title": None,
            "year": None,
            "venue": None,
            "publisher": None,
            "source": None,
            "authors": [],
            "authors_detailed": [],
            "volume": None,
            "issue": None,
            "pages": None,
            "abstract": None,
            "official_url": None,
            "oa_pdf_url": None,
            "type": None,
            "type_crossref": None,
            "genre": None,
            "in_paper": bool(ref_id),
            "is_key": bool(ref_id) and (ref_id in key_ref_id_set),
            "ref_id": ref_id,
        }

        if ref_id:
            w = resolved_by_ref_id.get(ref_id)
            record = w.openalex_record if w and isinstance(w.openalex_record, dict) else None
            if w:
                meta["doi"] = normalize_doi(w.doi or "") or meta["doi"]
                meta["title"] = (w.title or "").strip() or meta["title"]
                meta["year"] = w.year or meta["year"]
                meta["abstract"] = _clip_text(getattr(w, "abstract", None), max_chars=settings.deep_analysis_abstract_max_chars) or meta["abstract"]
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
                meta["publisher"] = _extract_openalex_publisher(record) or meta["publisher"]
                meta["source"] = _extract_openalex_source_name(record) or meta["source"]
                meta["authors"] = _extract_openalex_authors(record) or meta["authors"]
                meta["authors_detailed"] = _extract_openalex_authors_detailed(record) or meta["authors_detailed"]
                meta["type"] = record.get("type") or meta["type"]
                meta["type_crossref"] = record.get("type_crossref") or meta["type_crossref"]
                meta["genre"] = record.get("genre") or meta["genre"]
                if not meta.get("abstract"):
                    meta["abstract"] = _clip_text(_extract_openalex_abstract(record), max_chars=settings.deep_analysis_abstract_max_chars)
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
                meta["publisher"] = str(summ.get("publisher") or "").strip() or meta["publisher"]
                meta["source"] = str(summ.get("source") or "").strip() or meta["source"]
                if isinstance(summ.get("authors"), list):
                    meta["authors"] = [str(a).strip() for a in summ.get("authors") if isinstance(a, str) and a.strip()]
                if isinstance(summ.get("authors_detailed"), list):
                    meta["authors_detailed"] = [
                        a for a in summ.get("authors_detailed") if isinstance(a, dict) and isinstance(a.get("name"), str)
                    ]
                meta["volume"] = str(summ.get("volume") or "").strip() or meta["volume"]
                meta["issue"] = str(summ.get("issue") or "").strip() or meta["issue"]
                meta["pages"] = str(summ.get("pages") or "").strip() or meta["pages"]
                meta["abstract"] = str(summ.get("abstract") or "").strip() or meta["abstract"]
                meta["official_url"] = str(summ.get("official_url") or "").strip() or meta["official_url"]
                meta["oa_pdf_url"] = str(summ.get("oa_pdf_url") or "").strip() or meta["oa_pdf_url"]
                meta["type"] = summ.get("type") or meta["type"]
                meta["type_crossref"] = summ.get("type_crossref") or meta["type_crossref"]
                meta["genre"] = summ.get("genre") or meta["genre"]

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
            if key not in allowed_keys:
                continue
            seen.add(key)
            out.append(key)
        return out

    def _is_secondary_meta(meta: dict[str, Any]) -> bool:
        return is_secondary_reference(
            title=meta.get("title"),
            work_type=meta.get("type"),
            type_crossref=meta.get("type_crossref"),
            genre=meta.get("genre"),
        )

    excluded_sources = load_excluded_sources()

    def _is_excluded_meta(meta: dict[str, Any]) -> bool:
        if not excluded_sources:
            return False
        candidates = [
            meta.get("venue"),
            meta.get("publisher"),
            meta.get("source"),
        ]
        for val in candidates:
            if isinstance(val, str) and matches_excluded_source(val, excluded_sources):
                return True
        return False

    allowed_keys = {
        k
        for k, meta in meta_by_key.items()
        if _is_meaningful_meta(meta) and not _is_secondary_meta(meta) and not _is_excluded_meta(meta)
    }

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

    leftovers = [k for k in meta_by_key.keys() if k not in assigned and k in allowed_keys]
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
        if key not in allowed_keys:
            continue
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
            "authors_detailed": meta.get("authors_detailed"),
            "volume": meta.get("volume"),
            "issue": meta.get("issue"),
            "pages": meta.get("pages"),
            "abstract": meta.get("abstract"),
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

    rid_by_node_id: dict[str, str] = {}
    for node_id, key in node_id_to_key.items():
        rid = rid_by_key.get(key)
        if rid:
            rid_by_node_id[node_id] = rid

    return references_by_rid, reference_groups, citation_groups, trunc, rid_by_node_id


def _fetch_openalex_summaries(
    *,
    openalex: OpenAlexClient,
    openalex_ids: list[str],
    max_workers: int,
    max_items: int,
    abstract_max_chars: int,
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
        publisher = _extract_openalex_publisher(work)
        source = _extract_openalex_source_name(work)
        authors = _extract_openalex_authors(work)
        authors_detailed = _extract_openalex_authors_detailed(work)
        abstract = _clip_text(_extract_openalex_abstract(work), max_chars=int(abstract_max_chars))
        b = _extract_openalex_biblio(work)
        official_url = _pick_official_url(doi=doi, record=work)
        oa_pdf_url = _pick_open_access_pdf(record=work)
        return {
            "openalex_id": work.get("id"),
            "title": title or None,
            "doi": doi,
            "year": year,
            "venue": venue,
            "publisher": publisher,
            "source": source,
            "authors": authors,
            "authors_detailed": authors_detailed,
            "volume": b.get("volume"),
            "issue": b.get("issue"),
            "pages": b.get("pages"),
            "abstract": abstract,
            "official_url": official_url,
            "oa_pdf_url": oa_pdf_url,
            "type": work.get("type"),
            "type_crossref": work.get("type_crossref"),
            "genre": work.get("genre"),
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

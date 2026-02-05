from __future__ import annotations

from collections import Counter
from typing import Any
from urllib.parse import quote_plus


def _collapse_ws(text: str) -> str:
    return " ".join((text or "").replace("\u00a0", " ").split()).strip()


def build_potential_reviewers_from_coupling(
    *,
    coupling_rids: list[str],
    references_by_rid: dict[str, dict],
) -> list[dict[str, str]]:
    if not coupling_rids or not references_by_rid:
        return []

    people: dict[str, dict[str, Any]] = {}

    for rid in coupling_rids:
        if not isinstance(rid, str) or not rid.strip():
            continue
        ref = references_by_rid.get(rid.strip())
        if not isinstance(ref, dict):
            continue
        year = ref.get("year") if isinstance(ref.get("year"), int) else 0
        authors = ref.get("authors_detailed")
        if not isinstance(authors, list):
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
                entry = {"name": name, "affiliations": Counter(), "latest_year": year}
                people[key] = entry
            if len(name) > len(str(entry.get("name") or "")):
                entry["name"] = name
            if affiliation:
                entry["affiliations"][affiliation] += 1
            if year and int(entry.get("latest_year") or 0) < year:
                entry["latest_year"] = year

    sortable: list[tuple[int, str, str, dict[str, str]]] = []
    for entry in people.values():
        name = _collapse_ws(str(entry.get("name") or ""))
        if not name:
            continue
        affiliations = entry.get("affiliations")
        affiliation = ""
        if isinstance(affiliations, Counter) and affiliations:
            affiliation = affiliations.most_common(1)[0][0]
        year = int(entry.get("latest_year") or 0)
        q = f"{name} {affiliation}".strip() if affiliation else name
        sortable.append(
            (
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

    sortable.sort(key=lambda item: (-item[0], item[1], item[2]))
    return [item[3] for item in sortable]

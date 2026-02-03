from __future__ import annotations

import re

from server.miscite.analysis.match.index import build_reference_index
from server.miscite.analysis.match.types import CitationMatch, CitationMatchCandidate
from server.miscite.analysis.parse.citation_parsing import CitationInstance, ReferenceEntry
from server.miscite.analysis.shared.normalize import normalize_author_name, normalize_author_year_locator, normalize_year_token

_SURNAME_RE = re.compile(r"[A-Z][A-Za-z'’\\-]+")

_CITATION_NAME_STOPWORDS = {
    "see",
    "also",
    "cf",
    "eg",
    "e",
    "g",
    "al",
    "et",
}


def _parse_author_year_locator(locator: str | None) -> tuple[str | None, str | None]:
    norm = normalize_author_year_locator(locator) or ""
    if not norm:
        return None, None
    if "-" in norm:
        author, year = norm.rsplit("-", 1)
        return normalize_author_name(author), normalize_year_token(year)
    return normalize_author_name(norm), None


def _extract_surnames_from_citation(raw: str) -> set[str]:
    if not raw:
        return set()
    hits = _SURNAME_RE.findall(raw)
    out: set[str] = set()
    for hit in hits:
        token = hit.strip().lower()
        if not token or token in _CITATION_NAME_STOPWORDS:
            continue
        norm = normalize_author_name(token)
        if norm:
            out.add(norm)
    return out


def _ref_year_int(ref: ReferenceEntry, *, year_token_by_ref_id: dict[str, str | None]) -> int | None:
    if ref.year:
        return int(ref.year)
    yt = year_token_by_ref_id.get(ref.ref_id)
    if yt and len(yt) >= 4 and yt[:4].isdigit():
        try:
            return int(yt[:4])
        except Exception:
            return None
    return None


def match_citations_to_references(
    citations: list[CitationInstance],
    references: list[ReferenceEntry],
    *,
    reference_records: dict[str, dict],
) -> list[CitationMatch]:
    index = build_reference_index(references, reference_records=reference_records)
    matches: list[CitationMatch] = []

    for cit in citations:
        if cit.kind == "numeric":
            ref = index.by_number.get((cit.locator or "").strip())
            if ref is None:
                matches.append(
                    CitationMatch(
                        citation=cit,
                        ref=None,
                        status="unmatched",
                        confidence=0.0,
                        method="number_direct",
                        candidates=[],
                        notes=["No bibliography item with that reference number."],
                    )
                )
                continue
            matches.append(
                CitationMatch(
                    citation=cit,
                    ref=ref,
                    status="matched",
                    confidence=1.0,
                    method="number_direct",
                    candidates=[CitationMatchCandidate(ref_id=ref.ref_id, score=1.0, reasons=["ref_number match"])],
                    notes=[],
                )
            )
            continue

        if cit.kind != "author_year":
            matches.append(
                CitationMatch(
                    citation=cit,
                    ref=None,
                    status="unmatched",
                    confidence=0.0,
                    method="unknown",
                    candidates=[],
                    notes=["Unsupported citation kind."],
                )
            )
            continue

        author_norm, year_token = _parse_author_year_locator(cit.locator)
        if not author_norm:
            matches.append(
                CitationMatch(
                    citation=cit,
                    ref=None,
                    status="unmatched",
                    confidence=0.0,
                    method="author_year_unparsed",
                    candidates=[],
                    notes=["Could not parse author/year locator."],
                )
            )
            continue

        key_full = f"{author_norm}-{year_token}" if year_token else None
        candidates = list(index.by_author_year.get(key_full, [])) if key_full else []
        method = "author_year_exact"
        notes: list[str] = []

        if not candidates and year_token and len(year_token) >= 5 and year_token[:4].isdigit():
            # Handle cases where suffix letters were lost in bibliography parsing.
            key_unsuffixed = f"{author_norm}-{year_token[:4]}"
            candidates = list(index.by_author_year.get(key_unsuffixed, []))
            method = "author_year_suffix_ignored"
            if candidates:
                notes.append("Citation year suffix ignored for bibliography match.")

        # Relaxed fallback: same author, near-year candidates (±1), then unique-author fallback.
        if not candidates:
            author_refs = list(index.by_author.get(author_norm, []))
            year_int = int(year_token[:4]) if year_token and year_token[:4].isdigit() else None
            if year_int is not None:
                near = []
                for ref in author_refs:
                    ry = _ref_year_int(ref, year_token_by_ref_id=index.year_token_by_ref_id)
                    if ry is None:
                        continue
                    if abs(ry - year_int) <= 1:
                        near.append(ref)
                if near:
                    candidates = near
                    method = "author_year_nearby"
                    notes.append("Matched by author with year tolerance (±1).")
            if not candidates and len(author_refs) == 1:
                candidates = author_refs
                method = "author_only_unique"
                notes.append("Matched by author only (unique author in bibliography); year mismatch possible.")

        if not candidates:
            matches.append(
                CitationMatch(
                    citation=cit,
                    ref=None,
                    status="unmatched",
                    confidence=0.0,
                    method=method,
                    candidates=[],
                    notes=["No bibliography candidates found."] + notes,
                )
            )
            continue

        cit_surnames = _extract_surnames_from_citation(cit.raw)

        scored: list[tuple[float, ReferenceEntry, list[str]]] = []
        year_int = int(year_token[:4]) if year_token and year_token[:4].isdigit() else None
        for ref in candidates:
            reasons: list[str] = []
            score = 0.55

            # Author agreement (always true for these candidates, but keep evidence explicit).
            score += 0.10
            reasons.append("first_author match")

            # Year similarity
            ref_year_token = index.year_token_by_ref_id.get(ref.ref_id)
            if year_token and ref_year_token and year_token == ref_year_token:
                score += 0.18
                reasons.append("year token match")
            else:
                ry = _ref_year_int(ref, year_token_by_ref_id=index.year_token_by_ref_id)
                if year_int is not None and ry is not None:
                    diff = abs(ry - year_int)
                    if diff == 0:
                        score += 0.14
                        reasons.append("year match")
                    elif diff <= 1:
                        score += 0.07
                        reasons.append("year within ±1")
                    else:
                        reasons.append(f"year differs by {diff}")

            # Coauthor hints from in-text raw (when present).
            ref_surnames = index.author_surnames_by_ref_id.get(ref.ref_id) or set()
            overlap = (cit_surnames & ref_surnames) - {author_norm}
            if overlap:
                bump = min(0.12, 0.04 * len(overlap))
                score += bump
                reasons.append(f"coauthor overlap: {sorted(overlap)[:3]}")

            scored.append((min(1.0, score), ref, reasons))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_score, top_ref, top_reasons = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0
        margin = top_score - second_score

        status = "ambiguous" if len(scored) > 1 and margin < 0.08 else "matched"
        if top_score < 0.65:
            status = "ambiguous" if candidates else "unmatched"

        cand_out = [
            CitationMatchCandidate(ref_id=ref.ref_id, score=score, reasons=reasons)
            for score, ref, reasons in scored[:5]
        ]

        matches.append(
            CitationMatch(
                citation=cit,
                ref=top_ref,
                status=status,
                confidence=float(top_score),
                method=method,
                candidates=cand_out,
                notes=notes,
            )
        )

    return matches

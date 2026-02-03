from __future__ import annotations

import logging

from server.miscite.analysis.match.types import CitationMatch
from server.miscite.analysis.parse.citation_parsing import ReferenceEntry
from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient, LlmOutputError
from server.miscite.prompts import get_prompt, render_prompt

logger = logging.getLogger(__name__)

_SYSTEM_BIB_CANDIDATE = get_prompt("matching/bibliography_candidate/system")


def _csl_title(csl: dict | None) -> str | None:
    if not isinstance(csl, dict):
        return None
    title = csl.get("title")
    if isinstance(title, str) and title.strip():
        return title.strip()
    if isinstance(title, list) and title:
        first = title[0]
        if isinstance(first, str) and first.strip():
            return first.strip()
    return None


def disambiguate_citation_matches_with_llm(
    *,
    settings: Settings,
    llm_client: OpenRouterClient,
    matches: list[CitationMatch],
    references: list[ReferenceEntry],
    reference_records: dict[str, dict],
    max_calls: int,
) -> tuple[list[CitationMatch], int]:
    """Use the LLM to resolve ambiguous citation↔bibliography matches.

    - Only operates on matches whose status is "ambiguous" and have >=2 candidates.
    - Memoizes decisions by (citation raw + context snippet + candidate id set) to avoid repeated calls.
    """

    if max_calls <= 0:
        return matches, 0

    ref_by_id = {ref.ref_id: ref for ref in references}
    calls_used = 0
    memo: dict[tuple[str, str, tuple[str, ...]], tuple[str | None, float, str]] = {}

    out: list[CitationMatch] = []

    for match in matches:
        if match.status != "ambiguous" or not match.candidates or len(match.candidates) < 2:
            out.append(match)
            continue

        raw_key = (match.citation.raw or "").strip()
        context_key = " ".join((match.citation.context or "").split())[:240]
        cand_ids = tuple(sorted({c.ref_id for c in match.candidates if c.ref_id}))
        memo_key = (raw_key, context_key, cand_ids)

        cached = memo.get(memo_key)
        if cached is None:
            if calls_used >= max_calls:
                out.append(
                    CitationMatch(
                        citation=match.citation,
                        ref=match.ref,
                        status=match.status,
                        confidence=match.confidence,
                        method=match.method,
                        candidates=match.candidates,
                        notes=match.notes + ["LLM disambiguation skipped: match-call budget exhausted."],
                    )
                )
                continue

            candidates_payload: list[dict] = []
            for cand in match.candidates:
                ref = ref_by_id.get(cand.ref_id)
                if not ref:
                    continue
                csl = reference_records.get(ref.ref_id)
                candidates_payload.append(
                    {
                        "id": ref.ref_id,
                        "raw": ref.raw,
                        "title": _csl_title(csl),
                        "first_author": ref.first_author,
                        "year": ref.year,
                        "doi": ref.doi,
                        "score_hint": cand.score,
                        "reasons": cand.reasons,
                    }
                )

            if len(candidates_payload) < 2:
                out.append(match)
                continue

            calls_used += 1
            try:
                payload = llm_client.chat_json(
                    system=_SYSTEM_BIB_CANDIDATE,
                    user=render_prompt(
                        "matching/bibliography_candidate/user",
                        citation_raw=match.citation.raw,
                        citation_locator=match.citation.locator,
                        citation_context=match.citation.context,
                        candidates=candidates_payload,
                    ),
                )

                best_id = payload.get("best_id")
                conf = payload.get("confidence")
                rationale = str(payload.get("rationale") or "").strip()

                if best_id is not None and not isinstance(best_id, str):
                    raise LlmOutputError("LLM best_id must be string or null.")
                try:
                    conf_f = float(conf)
                except Exception as e:
                    raise LlmOutputError("LLM confidence must be a number 0..1.") from e
                if conf_f < 0.0 or conf_f > 1.0:
                    raise LlmOutputError("LLM confidence out of range.")

                allowed = {str(c.get("id")) for c in candidates_payload if c.get("id")}
                if best_id is not None and best_id not in allowed:
                    raise LlmOutputError("LLM returned an id not in candidate set.")

                memo[memo_key] = (best_id, conf_f, rationale)
                cached = memo[memo_key]
            except LlmOutputError as e:
                logger.exception(
                    "LLM citation↔bibliography disambiguation output invalid; keeping ambiguous (locator=%s).",
                    match.citation.locator,
                )
                out.append(
                    CitationMatch(
                        citation=match.citation,
                        ref=match.ref,
                        status=match.status,
                        confidence=match.confidence,
                        method=match.method,
                        candidates=match.candidates,
                        notes=match.notes + [f"LLM disambiguation failed: {str(e).strip()}"],
                    )
                )
                continue
            except Exception as e:
                logger.exception(
                    "LLM citation↔bibliography disambiguation failed; keeping ambiguous (locator=%s).",
                    match.citation.locator,
                )
                note = str(e).strip() or "Unknown error."
                if len(note) > 200:
                    note = note[:200] + "..."
                out.append(
                    CitationMatch(
                        citation=match.citation,
                        ref=match.ref,
                        status=match.status,
                        confidence=match.confidence,
                        method=match.method,
                        candidates=match.candidates,
                        notes=match.notes + [f"LLM disambiguation failed: {note}"],
                    )
                )
                continue

        best_id, conf_f, rationale = cached
        if best_id is None:
            out.append(
                CitationMatch(
                    citation=match.citation,
                    ref=match.ref,
                    status="ambiguous",
                    confidence=min(match.confidence, float(conf_f)),
                    method=f"{match.method}_llm",
                    candidates=match.candidates,
                    notes=match.notes + ["LLM could not choose a single best bibliography match."] + ([rationale] if rationale else []),
                )
            )
            continue

        chosen = ref_by_id.get(best_id)
        if not chosen:
            out.append(match)
            continue

        status = "matched" if conf_f >= 0.65 else "ambiguous"
        out.append(
            CitationMatch(
                citation=match.citation,
                ref=chosen,
                status=status,
                confidence=float(conf_f),
                method=f"{match.method}_llm",
                candidates=match.candidates,
                notes=match.notes + ([f"LLM disambiguation ({conf_f:.2f}): {rationale}"] if rationale else [f"LLM disambiguation ({conf_f:.2f})."]),
            )
        )

    return out, calls_used

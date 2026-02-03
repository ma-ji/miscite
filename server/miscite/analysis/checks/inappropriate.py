from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from server.miscite.analysis.checks.local_nli import LocalNliModel
from server.miscite.analysis.match.types import CitationMatch
from server.miscite.analysis.parse.citation_parsing import CitationInstance, ReferenceEntry
from server.miscite.analysis.pipeline.types import ResolvedWork
from server.miscite.analysis.shared.normalize import content_tokens
from server.miscite.core.config import Settings
from server.miscite.llm.openrouter import OpenRouterClient, LlmOutputError
from server.miscite.prompts import get_prompt, render_prompt


_INAPPROPRIATE_SYSTEM = get_prompt("checks/inappropriate/system")

logger = logging.getLogger(__name__)


def token_overlap_score(a: str, b: str) -> float:
    ta = content_tokens(a)
    tb = content_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    return inter / max(1, len(ta))


def build_inappropriate_prompt(cit: CitationInstance, ref: ReferenceEntry, work: ResolvedWork) -> str:
    abstract = (work.abstract or "").strip()
    if len(abstract) > 1500:
        abstract = abstract[:1500] + "\u2026"
    return render_prompt(
        "checks/inappropriate/user",
        context=cit.context,
        ref_raw=ref.raw,
        doi=work.doi,
        title=work.title,
        year=work.year,
        journal=work.journal,
        abstract=abstract,
    )


def check_inappropriate_citations(
    *,
    settings: Settings,
    llm_client: OpenRouterClient,
    local_nli: LocalNliModel | None,
    citation_matches: list[CitationMatch],
    resolved_by_ref_id: dict[str, ResolvedWork],
    progress: Callable[[str, float], None] | None = None,
) -> tuple[list[dict], int, int, bool]:
    """Run heuristic/NLI/LLM inappropriate-citation checks.

    Returns (issues, potential_issue_count, llm_calls_used, llm_used).
    """

    if progress:
        progress("Checking citation-context alignment", 0.0)

    llm_max_calls = int(settings.llm_max_calls)
    llm_calls = 0
    llm_calls_lock = threading.Lock()

    local_nli_lock = threading.Lock() if local_nli else None

    def _check_one(cit: CitationInstance, ref: ReferenceEntry, work: ResolvedWork) -> tuple[list[dict], bool]:
        nonlocal llm_calls

        if local_nli and local_nli_lock and work.abstract:
            with local_nli_lock:
                nli_verdict = local_nli.classify(premise=work.abstract, hypothesis=cit.context)
            if nli_verdict.label == "entailment" and nli_verdict.confidence >= 0.85:
                return [], False
            if nli_verdict.label == "contradiction" and nli_verdict.confidence >= 0.85:
                return (
                    [
                        {
                            "type": "potentially_inappropriate",
                            "title": f"NLI contradiction against abstract ({nli_verdict.confidence:.2f})",
                            "severity": "high",
                            "details": {
                                "citation": cit.__dict__,
                                "ref_id": ref.ref_id,
                                "resolution": work.__dict__,
                                "nli": nli_verdict.__dict__,
                            },
                        }
                    ],
                    False,
                )

        with llm_calls_lock:
            if llm_calls >= llm_max_calls:
                raise RuntimeError("LLM call limit exceeded; increase MISCITE_LLM_MAX_CALLS.")
            llm_calls += 1

        try:
            verdict = llm_client.chat_json(
                system=_INAPPROPRIATE_SYSTEM,
                user=build_inappropriate_prompt(cit, ref, work),
            )

            label = str(verdict.get("label") or "").strip().lower()
            if label not in {"appropriate", "inappropriate", "uncertain"}:
                raise LlmOutputError(f"Invalid LLM label: {label!r}")
            try:
                conf_f = float(verdict.get("confidence"))
            except Exception as e:
                raise LlmOutputError("Invalid LLM confidence (expected number 0..1).") from e
            if conf_f < 0.0 or conf_f > 1.0:
                raise LlmOutputError("Invalid LLM confidence out of range.")
        except LlmOutputError as e:
            logger.exception(
                "LLM inappropriate check output invalid; marking for manual review (ref_id=%s).",
                ref.ref_id,
            )
            return (
                [
                    {
                        "type": "needs_manual_review",
                        "title": "LLM inappropriate-check output invalid",
                        "severity": "low",
                        "details": {
                            "citation": cit.__dict__,
                            "ref_id": ref.ref_id,
                            "resolution": work.__dict__,
                            "error": str(e),
                        },
                    }
                ],
                True,
            )

        if label == "inappropriate" and conf_f >= 0.6:
            return (
                [
                    {
                        "type": "potentially_inappropriate",
                        "title": f"Inappropriate citation ({conf_f:.2f})",
                        "severity": "medium",
                        "details": {
                            "citation": cit.__dict__,
                            "ref_id": ref.ref_id,
                            "resolution": work.__dict__,
                            "llm": verdict,
                        },
                    }
                ],
                True,
            )

        if label == "uncertain":
            return (
                [
                    {
                        "type": "needs_manual_review",
                        "title": "Could not verify citation",
                        "severity": "low",
                        "details": {
                            "citation": cit.__dict__,
                            "ref_id": ref.ref_id,
                            "resolution": work.__dict__,
                            "llm": verdict,
                        },
                    }
                ],
                True,
            )

        return [], True

    checks: list[tuple[CitationInstance, ReferenceEntry, ResolvedWork]] = []

    for match in citation_matches:
        if match.ref is None:
            continue
        # Avoid running downstream checks on ambiguous/low-confidence matches.
        if match.status != "matched" or match.confidence < 0.75:
            continue
        cit = match.citation
        ref = match.ref
        work = resolved_by_ref_id.get(ref.ref_id)
        if not work or not work.title:
            continue
        evidence_text = (work.title or "") + "\n" + (work.abstract or "")
        if token_overlap_score(cit.context, evidence_text) >= 0.06:
            continue
        checks.append((cit, ref, work))

    issues: list[dict] = []
    if not checks:
        return issues, 0, llm_calls, False

    total_checks = len(checks)
    step_checks = max(1, total_checks // 10)
    inappropriate_workers = max(1, int(settings.inappropriate_max_workers))

    llm_used = False

    if inappropriate_workers == 1 or total_checks <= 1:
        for idx, (cit, ref, work) in enumerate(checks, start=1):
            new_issues, used_llm = _check_one(cit, ref, work)
            llm_used = llm_used or used_llm
            issues.extend(new_issues)
            if progress and (idx == 1 or idx % step_checks == 0 or idx == total_checks):
                progress(f"Checked {idx}/{total_checks} citations", idx / total_checks)
    else:
        with ThreadPoolExecutor(max_workers=inappropriate_workers) as ex:
            futures = {
                ex.submit(_check_one, cit, ref, work): (cit, ref)
                for cit, ref, work in checks
            }
            completed = 0
            try:
                for fut in as_completed(futures):
                    new_issues, used_llm = fut.result()
                    llm_used = llm_used or used_llm
                    issues.extend(new_issues)
                    completed += 1
                    if progress and (
                        completed == 1 or completed % step_checks == 0 or completed == total_checks
                    ):
                        progress(f"Checked {completed}/{total_checks} citations", completed / total_checks)
            except Exception:
                for fut in futures:
                    fut.cancel()
                raise

    return issues, len(issues), llm_calls, llm_used

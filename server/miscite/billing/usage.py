from __future__ import annotations

from dataclasses import dataclass
from threading import Lock


@dataclass
class UsageTotals:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    requests: int = 0


class UsageTracker:
    def __init__(self) -> None:
        self._lock = Lock()
        self._models: dict[str, UsageTotals] = {}

    def record(
        self,
        *,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
    ) -> None:
        model = (model or "").strip()
        if not model:
            return
        if prompt_tokens < 0 or completion_tokens < 0 or total_tokens < 0:
            return
        if total_tokens == 0 and (prompt_tokens or completion_tokens):
            total_tokens = prompt_tokens + completion_tokens
        if total_tokens == 0:
            return

        with self._lock:
            totals = self._models.get(model)
            if totals is None:
                totals = UsageTotals()
                self._models[model] = totals
            totals.prompt_tokens += int(prompt_tokens)
            totals.completion_tokens += int(completion_tokens)
            totals.total_tokens += int(total_tokens)
            totals.requests += 1

    def summary(self) -> dict:
        with self._lock:
            models = {
                model: {
                    "prompt_tokens": totals.prompt_tokens,
                    "completion_tokens": totals.completion_tokens,
                    "total_tokens": totals.total_tokens,
                    "requests": totals.requests,
                }
                for model, totals in self._models.items()
            }

        total_prompt = sum(v["prompt_tokens"] for v in models.values())
        total_completion = sum(v["completion_tokens"] for v in models.values())
        total_tokens = sum(v["total_tokens"] for v in models.values())
        total_requests = sum(v["requests"] for v in models.values())

        return {
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "total_requests": total_requests,
            "models": models,
        }

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from server.miscite.billing.pricing import PricingSnapshot


@dataclass(frozen=True)
class CostResult:
    currency: str
    raw_cost_cents: int
    final_cost_cents: int
    raw_cost_usd: str
    final_cost_usd: str
    multiplier: float
    missing_models: list[str]
    per_model: list[dict]
    pricing_source: str
    pricing_fetched_at: str


def _format_usd(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)}"


def compute_cost(
    *,
    usage_summary: dict,
    pricing: PricingSnapshot,
    multiplier: float,
    currency: str,
) -> CostResult:
    models_usage = usage_summary.get("models") or {}
    missing: list[str] = []
    per_model: list[dict] = []
    raw_cost = Decimal("0")

    for model_id, usage in models_usage.items():
        if not isinstance(usage, dict):
            continue
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        requests = int(usage.get("requests") or 0)
        pricing_row = pricing.models.get(model_id)
        if pricing_row is None:
            missing.append(model_id)
            continue
        prompt_rate = pricing_row.get("prompt") or Decimal("0")
        completion_rate = pricing_row.get("completion") or Decimal("0")
        request_rate = pricing_row.get("request") or Decimal("0")

        # OpenRouter pricing is USD per token/request/unit (not per 1M tokens).
        prompt_cost = Decimal(prompt_tokens) * prompt_rate
        completion_cost = Decimal(completion_tokens) * completion_rate
        request_cost = Decimal(requests) * request_rate
        model_cost = prompt_cost + completion_cost + request_cost
        raw_cost += model_cost
        per_model.append(
            {
                "model": model_id,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "requests": requests,
                "raw_cost_usd": _format_usd(model_cost),
            }
        )

    multiplier_dec = Decimal(str(multiplier))
    final_cost = raw_cost * multiplier_dec

    raw_cents = int((raw_cost * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    final_cents = int((final_cost * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    return CostResult(
        currency=currency,
        raw_cost_cents=raw_cents,
        final_cost_cents=final_cents,
        raw_cost_usd=_format_usd(raw_cost),
        final_cost_usd=_format_usd(final_cost),
        multiplier=multiplier,
        missing_models=missing,
        per_model=per_model,
        pricing_source=pricing.source,
        pricing_fetched_at=pricing.fetched_at.isoformat(),
    )

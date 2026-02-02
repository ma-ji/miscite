from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

import requests

from server.miscite.core.cache import Cache
from server.miscite.core.config import Settings
from server.miscite.sources.http import backoff_sleep


@dataclass(frozen=True)
class PricingSnapshot:
    fetched_at: dt.datetime
    models: dict[str, dict[str, Decimal]]
    source: str


def _parse_decimal(value) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _fetch_openrouter_pricing(settings: Settings) -> PricingSnapshot:
    url = settings.openrouter_pricing_url
    headers = {}
    if settings.openrouter_api_key:
        headers["Authorization"] = f"Bearer {settings.openrouter_api_key}"

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=headers, timeout=settings.api_timeout_seconds)
            resp.raise_for_status()
            payload = resp.json() or {}
            items = payload.get("data") or payload.get("models") or []
            models: dict[str, dict[str, Decimal]] = {}
            for item in items:
                if not isinstance(item, dict):
                    continue
                model_id = str(item.get("id") or "").strip()
                pricing = item.get("pricing") or {}
                if not model_id or not isinstance(pricing, dict):
                    continue
                prompt = _parse_decimal(pricing.get("prompt"))
                completion = _parse_decimal(pricing.get("completion"))
                if prompt is None or completion is None:
                    continue
                models[model_id] = {"prompt": prompt, "completion": completion}
            return PricingSnapshot(fetched_at=_now_utc(), models=models, source="openrouter")
        except Exception as e:
            last_err = e
            backoff_sleep(attempt)
    raise RuntimeError("Failed to fetch OpenRouter pricing") from last_err


def _serialize_snapshot(snapshot: PricingSnapshot) -> dict:
    return {
        "fetched_at": snapshot.fetched_at.isoformat(),
        "source": snapshot.source,
        "models": {
            model: {"prompt": str(pricing["prompt"]), "completion": str(pricing["completion"])}
            for model, pricing in snapshot.models.items()
        },
    }


def _deserialize_snapshot(payload: dict) -> PricingSnapshot | None:
    try:
        fetched_raw = payload.get("fetched_at")
        fetched_at = dt.datetime.fromisoformat(str(fetched_raw))
    except Exception:
        return None

    models_raw = payload.get("models")
    if not isinstance(models_raw, dict):
        return None

    models: dict[str, dict[str, Decimal]] = {}
    for model, pricing in models_raw.items():
        if not isinstance(pricing, dict):
            continue
        prompt = _parse_decimal(pricing.get("prompt"))
        completion = _parse_decimal(pricing.get("completion"))
        if prompt is None or completion is None:
            continue
        models[str(model)] = {"prompt": prompt, "completion": completion}

    source = str(payload.get("source") or "cache")
    return PricingSnapshot(fetched_at=fetched_at, models=models, source=source)


def get_openrouter_pricing(
    settings: Settings,
    *,
    cache: Cache | None = None,
    force_refresh: bool = False,
    allow_stale: bool = True,
) -> PricingSnapshot | None:
    cache = cache or Cache(settings=settings)
    ttl_seconds = float(settings.openrouter_pricing_refresh_minutes) * 60.0
    cache_key = ["v1"]

    cached_snapshot: PricingSnapshot | None = None
    if settings.cache_enabled:
        hit, cached = cache.get_json("openrouter.pricing", cache_key)
        if hit and isinstance(cached, dict):
            cached_snapshot = _deserialize_snapshot(cached)

    if cached_snapshot and not force_refresh:
        age = (_now_utc() - cached_snapshot.fetched_at).total_seconds()
        if age <= ttl_seconds:
            return cached_snapshot

    try:
        fresh = _fetch_openrouter_pricing(settings)
        if settings.cache_enabled:
            cache.set_json(
                "openrouter.pricing",
                cache_key,
                _serialize_snapshot(fresh),
                ttl_seconds=max(ttl_seconds, 300.0),
            )
        return fresh
    except Exception:
        if cached_snapshot and allow_stale:
            return PricingSnapshot(
                fetched_at=cached_snapshot.fetched_at,
                models=cached_snapshot.models,
                source="cache-stale",
            )
        return None

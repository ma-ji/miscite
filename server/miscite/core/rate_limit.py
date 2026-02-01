from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from server.miscite.core.config import Settings


@dataclass
class _Bucket:
    tokens: float
    updated_at: float


class RateLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, _Bucket] = {}
        self._active: dict[str, int] = {}

    def allow(self, key: str, *, limit: int, window_seconds: int) -> bool:
        now = time.monotonic()
        rate = limit / max(1.0, float(window_seconds))
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=float(limit), updated_at=now)
                self._buckets[key] = bucket
            else:
                elapsed = max(0.0, now - bucket.updated_at)
                bucket.tokens = min(float(limit), bucket.tokens + elapsed * rate)
                bucket.updated_at = now

            if bucket.tokens < 1.0:
                return False
            bucket.tokens -= 1.0
            return True

    def acquire_slot(self, key: str, *, max_active: int) -> bool:
        with self._lock:
            active = self._active.get(key, 0)
            if active >= max_active:
                return False
            self._active[key] = active + 1
            return True

    def release_slot(self, key: str) -> None:
        with self._lock:
            active = self._active.get(key, 0)
            if active <= 1:
                self._active.pop(key, None)
            else:
                self._active[key] = active - 1


_limiter = RateLimiter()


def _client_ip(request: Request, settings: Settings) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    client = request.client
    return client.host if client else "unknown"


def enforce_rate_limit(
    request: Request,
    *,
    settings: Settings,
    key: str,
    limit: int,
    window_seconds: int,
) -> None:
    if not settings.rate_limit_enabled:
        return
    if limit <= 0:
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")
    client_id = _client_ip(request, settings)
    bucket_key = f"{key}:{client_id}"
    if not _limiter.allow(bucket_key, limit=limit, window_seconds=window_seconds):
        raise HTTPException(status_code=429, detail="Rate limit exceeded.")


def acquire_stream_slot(
    request: Request,
    *,
    settings: Settings,
    key: str,
    max_active: int,
) -> str | None:
    if not settings.rate_limit_enabled:
        return None
    client_id = _client_ip(request, settings)
    bucket_key = f"{key}:{client_id}"
    if not _limiter.acquire_slot(bucket_key, max_active=max_active):
        raise HTTPException(status_code=429, detail="Too many active streams.")
    return bucket_key


def release_stream_slot(bucket_key: str | None) -> None:
    if not bucket_key:
        return
    _limiter.release_slot(bucket_key)

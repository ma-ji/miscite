from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager

_SOURCE_LIMITERS_LOCK = threading.Lock()
_SOURCE_LIMITERS: dict[tuple[str, int], threading.BoundedSemaphore] = {}


def _global_source_limiter(source: str, *, limit: int) -> threading.BoundedSemaphore | None:
    limit = int(limit)
    if limit <= 0:
        return None
    key = (str(source or "").strip().lower(), limit)
    with _SOURCE_LIMITERS_LOCK:
        limiter = _SOURCE_LIMITERS.get(key)
        if limiter is None:
            limiter = threading.BoundedSemaphore(limit)
            _SOURCE_LIMITERS[key] = limiter
    return limiter


@contextmanager
def acquire_api_slot(
    *,
    source: str,
    job_limiter: threading.Semaphore | None,
    source_limit: int,
) -> Iterator[None]:
    source_limiter = _global_source_limiter(source, limit=source_limit)
    if job_limiter is not None:
        job_limiter.acquire()
    if source_limiter is not None:
        source_limiter.acquire()
    try:
        yield
    finally:
        if source_limiter is not None:
            source_limiter.release()
        if job_limiter is not None:
            job_limiter.release()

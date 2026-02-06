from __future__ import annotations

import json
from dataclasses import dataclass, field
import threading

import requests

from server.miscite.core.cache import Cache
from server.miscite.analysis.shared.normalize import normalize_doi
from server.miscite.sources.concurrency import acquire_api_slot
from server.miscite.sources.http import backoff_sleep, record_http_request


@dataclass
class RetractionApiClient:
    """Optional API client for retraction lookups.

    This is intentionally generic: different organizations expose different schemas.

    Supported response shapes:
    - {"match": true, "record": {...}}
    - {"records": [{...}, ...]}
    - [{...}, ...]

    The lookup request is GET `${url}?doi=<doi>`.
    """

    url: str
    token: str = ""
    mode: str = "lookup"  # "lookup" | "list"
    timeout_seconds: float = 20.0
    cache: Cache | None = None
    job_limiter: threading.Semaphore | None = None
    source_global_limit: int = 2

    _list_cache: list[dict] | None = None
    _list_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _session_local: threading.local = field(default_factory=threading.local, init=False, repr=False)

    def _client(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        return session

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _ttl_seconds(self, suggested_days: int) -> float:
        cache = self.cache
        if not cache:
            return 0.0
        days = min(int(suggested_days), int(cache.settings.cache_http_ttl_days))
        return float(max(0, days)) * 86400.0

    def _request_slot(self):
        return acquire_api_slot(
            source="retraction_api",
            job_limiter=self.job_limiter,
            source_limit=self.source_global_limit,
        )

    def lookup_by_doi(self, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm or not self.url:
            return None
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("retraction_api.lookup_by_doi", [self.mode, self.url, doi_norm])
            if hit:
                return cached

        if self.mode == "list":
            return self._lookup_from_list(doi_norm)
        return self._lookup_via_http(doi_norm)

    def _lookup_via_http(self, doi_norm: str) -> dict | None:
        cache = self.cache
        for attempt in range(3):
            try:
                record_http_request(cache, "retraction_api.lookup_by_doi")
                with self._request_slot():
                    resp = self._client().get(
                        self.url,
                        params={"doi": doi_norm},
                        headers=self._headers(),
                        timeout=self.timeout_seconds,
                    )
                if resp.status_code == 404:
                    if cache and cache.settings.cache_enabled:
                        cache.set_json(
                            "retraction_api.lookup_by_doi",
                            [self.mode, self.url, doi_norm],
                            None,
                            ttl_seconds=self._ttl_seconds(1),
                        )
                    return None
                resp.raise_for_status()
                record = _parse_retraction_lookup_response(resp.json(), doi_norm)
                if cache and cache.settings.cache_enabled:
                    cache.set_json(
                        "retraction_api.lookup_by_doi",
                        [self.mode, self.url, doi_norm],
                        record,
                        ttl_seconds=self._ttl_seconds(30),
                    )
                return record
            except requests.RequestException:
                backoff_sleep(attempt)
            except Exception:
                return None
        return None

    def _lookup_from_list(self, doi_norm: str) -> dict | None:
        if self._list_cache is None:
            with self._list_lock:
                if self._list_cache is None:
                    self._list_cache = self._fetch_list() or []
        for rec in self._list_cache:
            rec_doi = normalize_doi(str(rec.get("doi") or ""))
            if rec_doi and rec_doi == doi_norm:
                return rec
        return None

    def _fetch_list(self) -> list[dict] | None:
        cache = self.cache
        cache_parts = [self.mode, self.url, self.token or ""]
        if cache and cache.settings.cache_enabled:
            ttl_days = min(1, int(cache.settings.cache_http_ttl_days))
            hit, cached_text = cache.get_text_file("retraction_api.list", cache_parts, ttl_days=ttl_days)
            if hit:
                try:
                    cached = json.loads(cached_text)
                except Exception:
                    cached = None
                if isinstance(cached, list):
                    return [d for d in cached if isinstance(d, dict)]

        for attempt in range(3):
            try:
                record_http_request(cache, "retraction_api.list")
                with self._request_slot():
                    resp = self._client().get(
                        self.url,
                        headers=self._headers(),
                        timeout=self.timeout_seconds,
                    )
                resp.raise_for_status()
                data = resp.json()
                records: list[dict] | None = None
                if isinstance(data, list):
                    records = [d for d in data if isinstance(d, dict)]
                elif isinstance(data, dict):
                    raw_records = data.get("records") or data.get("items") or data.get("data")
                    if isinstance(raw_records, list):
                        records = [d for d in raw_records if isinstance(d, dict)]

                if records is None:
                    return None
                if cache and cache.settings.cache_enabled:
                    try:
                        cache.set_text_file(
                            "retraction_api.list",
                            cache_parts,
                            json.dumps(records, ensure_ascii=False),
                        )
                    except Exception:
                        pass
                return records
            except requests.RequestException:
                backoff_sleep(attempt)
            except Exception:
                return None
        return None


def _parse_retraction_lookup_response(payload: object, doi_norm: str) -> dict | None:
    if isinstance(payload, dict):
        if payload.get("match") is True and isinstance(payload.get("record"), dict):
            return payload["record"]
        if isinstance(payload.get("record"), dict) and normalize_doi(str(payload["record"].get("doi") or "")) == doi_norm:
            return payload["record"]
        records = payload.get("records") or payload.get("items") or payload.get("data")
        if isinstance(records, list):
            for item in records:
                if not isinstance(item, dict):
                    continue
                if normalize_doi(str(item.get("doi") or "")) == doi_norm:
                    return item
        # Sometimes APIs return a single record object directly.
        if normalize_doi(str(payload.get("doi") or "")) == doi_norm:
            return payload
        if payload.get("is_retracted") is True:
            return {"doi": doi_norm, "is_retracted": True}
        return None

    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            if normalize_doi(str(item.get("doi") or "")) == doi_norm:
                return item
    return None

from __future__ import annotations

from dataclasses import dataclass, field
import threading

import requests

from server.miscite.cache import Cache
from server.miscite.analysis.normalize import normalize_doi
from server.miscite.sources.http import backoff_sleep


@dataclass
class CrossrefClient:
    user_agent: str
    mailto: str = ""
    timeout_seconds: float = 20.0
    cache: Cache | None = None
    _session_local: threading.local = field(default_factory=threading.local, init=False, repr=False)

    def _client(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        return session

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent}

    def _ttl_seconds(self, suggested_days: int) -> float:
        cache = self.cache
        if not cache:
            return 0.0
        days = min(int(suggested_days), int(cache.settings.cache_http_ttl_days))
        return float(max(0, days)) * 86400.0

    def get_work_by_doi(self, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("crossref.work_by_doi", [doi_norm])
            if hit:
                return cached
        url = f"https://api.crossref.org/works/{doi_norm}"
        for attempt in range(3):
            try:
                resp = self._client().get(url, headers=self._headers(), timeout=self.timeout_seconds)
                if resp.status_code == 404:
                    if cache and cache.settings.cache_enabled:
                        cache.set_json("crossref.work_by_doi", [doi_norm], None, ttl_seconds=self._ttl_seconds(1))
                    return None
                resp.raise_for_status()
                msg = (resp.json() or {}).get("message")
                if cache and cache.settings.cache_enabled:
                    cache.set_json("crossref.work_by_doi", [doi_norm], msg, ttl_seconds=self._ttl_seconds(90))
                return msg
            except requests.RequestException:
                backoff_sleep(attempt)
        return None

    def search(self, query: str, *, rows: int = 5) -> list[dict]:
        url = "https://api.crossref.org/works"
        params = {"query.bibliographic": query, "rows": rows}
        if self.mailto:
            params["mailto"] = self.mailto
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("crossref.search", [query, str(rows)])
            if hit and isinstance(cached, list):
                return cached
        for attempt in range(3):
            try:
                resp = self._client().get(url, headers=self._headers(), params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                msg = (resp.json() or {}).get("message") or {}
                items = msg.get("items") or []
                if cache and cache.settings.cache_enabled and isinstance(items, list):
                    cache.set_json("crossref.search", [query, str(rows)], items, ttl_seconds=self._ttl_seconds(7))
                return items
            except requests.RequestException:
                backoff_sleep(attempt)
        return []

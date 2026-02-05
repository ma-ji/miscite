from __future__ import annotations

from dataclasses import dataclass, field
import threading

import requests

from server.miscite.core.cache import Cache
from server.miscite.analysis.shared.normalize import normalize_doi
from server.miscite.sources.http import backoff_sleep


def _openalex_work_id_suffix(openalex_id: str) -> str | None:
    if not openalex_id:
        return None
    openalex_id = openalex_id.strip()
    if not openalex_id:
        return None
    if openalex_id.startswith("https://openalex.org/"):
        return openalex_id.rstrip("/").split("/")[-1] or None
    if openalex_id.startswith("https://api.openalex.org/works/"):
        return openalex_id.rstrip("/").split("/")[-1] or None
    if openalex_id.startswith("W"):
        return openalex_id
    return None


def _openalex_author_id_suffix(author_id: str) -> str | None:
    if not author_id:
        return None
    author_id = author_id.strip()
    if not author_id:
        return None
    if author_id.startswith("https://openalex.org/"):
        return author_id.rstrip("/").split("/")[-1] or None
    if author_id.startswith("https://api.openalex.org/authors/"):
        return author_id.rstrip("/").split("/")[-1] or None
    if author_id.startswith("A"):
        return author_id
    return None


@dataclass
class OpenAlexClient:
    timeout_seconds: float = 20.0
    cache: Cache | None = None
    _session_local: threading.local = field(default_factory=threading.local, init=False, repr=False)

    def _client(self) -> requests.Session:
        session = getattr(self._session_local, "session", None)
        if session is None:
            session = requests.Session()
            self._session_local.session = session
        return session

    def _ttl_seconds(self, suggested_days: int) -> float:
        cache = self.cache
        if not cache:
            return 0.0
        days = min(int(suggested_days), int(cache.settings.cache_http_ttl_days))
        return float(max(0, days)) * 86400.0

    def _debug_increment(self, namespace: str, metric: str) -> None:
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            cache.debug_stats.increment(namespace, metric)

    def get_work_by_doi(self, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("openalex.work_by_doi", [doi_norm])
            if hit:
                return cached
        url = f"https://api.openalex.org/works/https://doi.org/{doi_norm}"
        for attempt in range(3):
            try:
                self._debug_increment("openalex.work_by_doi", "http_request")
                resp = self._client().get(url, timeout=self.timeout_seconds)
                if resp.status_code == 404:
                    if cache and cache.settings.cache_enabled:
                        cache.set_json("openalex.work_by_doi", [doi_norm], None, ttl_seconds=self._ttl_seconds(1))
                    return None
                resp.raise_for_status()
                data = resp.json()
                if cache and cache.settings.cache_enabled:
                    cache.set_json("openalex.work_by_doi", [doi_norm], data, ttl_seconds=self._ttl_seconds(90))
                return data
            except requests.RequestException:
                backoff_sleep(attempt)
        return None

    def get_work_by_id(self, openalex_id: str) -> dict | None:
        if not openalex_id:
            return None
        openalex_id = openalex_id.strip()
        if not openalex_id:
            return None
        cache = self.cache
        suffix = _openalex_work_id_suffix(openalex_id) or openalex_id
        if cache and cache.settings.cache_enabled and suffix:
            hit, cached = cache.get_json("openalex.work_by_id", [suffix])
            if hit:
                return cached

        if openalex_id.startswith("https://openalex.org/"):
            suffix = openalex_id.rstrip("/").split("/")[-1]
            url = f"https://api.openalex.org/works/{suffix}"
        elif openalex_id.startswith("https://api.openalex.org/works/"):
            url = openalex_id
        elif openalex_id.startswith("W"):
            url = f"https://api.openalex.org/works/{openalex_id}"
        else:
            url = openalex_id

        for attempt in range(3):
            try:
                self._debug_increment("openalex.work_by_id", "http_request")
                resp = self._client().get(url, timeout=self.timeout_seconds)
                if resp.status_code == 404:
                    if cache and cache.settings.cache_enabled and suffix:
                        cache.set_json("openalex.work_by_id", [suffix], None, ttl_seconds=self._ttl_seconds(1))
                    return None
                resp.raise_for_status()
                data = resp.json()
                if cache and cache.settings.cache_enabled and suffix:
                    cache.set_json("openalex.work_by_id", [suffix], data, ttl_seconds=self._ttl_seconds(90))
                return data
            except requests.RequestException:
                backoff_sleep(attempt)
        return None

    def search(self, query: str, *, rows: int = 5) -> list[dict]:
        url = "https://api.openalex.org/works"
        params = {"search": query, "per-page": rows}
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("openalex.search", [query, str(rows)])
            if hit and isinstance(cached, list):
                return cached
        for attempt in range(3):
            try:
                self._debug_increment("openalex.search", "http_request")
                resp = self._client().get(url, params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                results = (resp.json() or {}).get("results") or []
                if cache and cache.settings.cache_enabled and isinstance(results, list):
                    cache.set_json("openalex.search", [query, str(rows)], results, ttl_seconds=self._ttl_seconds(7))
                return results
            except requests.RequestException:
                backoff_sleep(attempt)
        return []

    def list_citing_works(self, openalex_id: str, *, rows: int = 100) -> list[dict]:
        """
        Returns a list of OpenAlex works that cite the given work.

        Note: This method returns at most `rows` results (single page).
        """
        suffix = _openalex_work_id_suffix(openalex_id)
        if not suffix:
            return []
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("openalex.list_citing_works", [suffix, str(rows)])
            if hit and isinstance(cached, list):
                return cached
        url = "https://api.openalex.org/works"
        params = {
            "filter": f"cites:{suffix}",
            "sort": "publication_date:desc",
            "per-page": rows,
        }
        for attempt in range(3):
            try:
                self._debug_increment("openalex.list_citing_works", "http_request")
                resp = self._client().get(url, params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                results = (resp.json() or {}).get("results") or []
                if cache and cache.settings.cache_enabled and isinstance(results, list):
                    cache.set_json(
                        "openalex.list_citing_works",
                        [suffix, str(rows)],
                        results,
                        ttl_seconds=self._ttl_seconds(3),
                    )
                return results
            except requests.RequestException:
                backoff_sleep(attempt)
        return []

    def list_author_works(self, author_id: str, *, rows: int = 100) -> list[dict]:
        """
        Returns a list of OpenAlex works authored by the given author.

        Note: This method returns at most `rows` results (single page).
        """
        suffix = _openalex_author_id_suffix(author_id)
        if not suffix:
            return []
        rows = max(1, min(int(rows), 200))
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json("openalex.list_author_works", [suffix, str(rows)])
            if hit and isinstance(cached, list):
                return cached
        url = "https://api.openalex.org/works"
        params = {
            "filter": f"authorships.author.id:{suffix}",
            "sort": "publication_date:desc",
            "per-page": rows,
        }
        for attempt in range(3):
            try:
                self._debug_increment("openalex.list_author_works", "http_request")
                resp = self._client().get(url, params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                results = (resp.json() or {}).get("results") or []
                if cache and cache.settings.cache_enabled and isinstance(results, list):
                    cache.set_json(
                        "openalex.list_author_works",
                        [suffix, str(rows)],
                        results,
                        ttl_seconds=self._ttl_seconds(7),
                    )
                return results
            except requests.RequestException:
                backoff_sleep(attempt)
        return []

from __future__ import annotations

from dataclasses import dataclass, field

import requests

from server.miscite.analysis.normalize import normalize_doi
from server.miscite.sources.http import backoff_sleep


@dataclass
class OpenAlexClient:
    timeout_seconds: float = 20.0
    _session: requests.Session | None = field(default=None, init=False, repr=False)

    def _client(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def get_work_by_doi(self, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        url = f"https://api.openalex.org/works/https://doi.org/{doi_norm}"
        for attempt in range(3):
            try:
                resp = self._client().get(url, timeout=self.timeout_seconds)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException:
                backoff_sleep(attempt)
        return None

    def get_work_by_id(self, openalex_id: str) -> dict | None:
        if not openalex_id:
            return None
        openalex_id = openalex_id.strip()
        if not openalex_id:
            return None

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
                resp = self._client().get(url, timeout=self.timeout_seconds)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException:
                backoff_sleep(attempt)
        return None

    def search(self, query: str, *, rows: int = 5) -> list[dict]:
        url = "https://api.openalex.org/works"
        params = {"search": query, "per-page": rows}
        for attempt in range(3):
            try:
                resp = self._client().get(url, params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                return (resp.json() or {}).get("results") or []
            except requests.RequestException:
                backoff_sleep(attempt)
        return []

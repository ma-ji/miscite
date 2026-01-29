from __future__ import annotations

from dataclasses import dataclass, field

import requests

from server.miscite.analysis.normalize import normalize_doi
from server.miscite.sources.http import backoff_sleep


@dataclass
class CrossrefClient:
    user_agent: str
    mailto: str = ""
    timeout_seconds: float = 20.0
    _session: requests.Session | None = field(default=None, init=False, repr=False)

    def _client(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _headers(self) -> dict[str, str]:
        return {"User-Agent": self.user_agent}

    def get_work_by_doi(self, doi: str) -> dict | None:
        doi_norm = normalize_doi(doi)
        if not doi_norm:
            return None
        url = f"https://api.crossref.org/works/{doi_norm}"
        for attempt in range(3):
            try:
                resp = self._client().get(url, headers=self._headers(), timeout=self.timeout_seconds)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return (resp.json() or {}).get("message")
            except requests.RequestException:
                backoff_sleep(attempt)
        return None

    def search(self, query: str, *, rows: int = 5) -> list[dict]:
        url = "https://api.crossref.org/works"
        params = {"query.bibliographic": query, "rows": rows}
        if self.mailto:
            params["mailto"] = self.mailto
        for attempt in range(3):
            try:
                resp = self._client().get(url, headers=self._headers(), params=params, timeout=self.timeout_seconds)
                resp.raise_for_status()
                msg = (resp.json() or {}).get("message") or {}
                return msg.get("items") or []
            except requests.RequestException:
                backoff_sleep(attempt)
        return []

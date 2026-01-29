from __future__ import annotations

from dataclasses import dataclass, field

import requests

from server.miscite.sources.http import backoff_sleep


def _norm_text(s: str) -> str:
    return " ".join("".join(ch.lower() for ch in s.strip() if ch.isalnum() or ch.isspace()).split())


def _norm_issn(issn: str) -> str:
    return (issn or "").replace("-", "").strip().lower()


@dataclass
class PredatoryApiClient:
    """Optional API client for predatory venue lookups.

    This is intentionally generic. The lookup request is:
    GET `${url}?issn=<issn>&journal=<journal>&publisher=<publisher>`

    Supported response shapes:
    - {"match": true, "record": {...}}
    - {"records": [{...}, ...]}
    - [{...}, ...]
    """

    url: str
    token: str = ""
    mode: str = "lookup"  # "lookup" | "list"
    timeout_seconds: float = 20.0

    _list_cache: list[dict] | None = None
    _session: requests.Session | None = field(default=None, init=False, repr=False)

    def _client(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
        return self._session

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def lookup(self, *, journal: str | None, publisher: str | None, issn: str | None) -> dict | None:
        if not self.url:
            return None
        if self.mode == "list":
            return self._lookup_from_list(journal=journal, publisher=publisher, issn=issn)
        return self._lookup_via_http(journal=journal, publisher=publisher, issn=issn)

    def _lookup_via_http(self, *, journal: str | None, publisher: str | None, issn: str | None) -> dict | None:
        params = {
            "issn": issn or "",
            "journal": journal or "",
            "publisher": publisher or "",
        }
        for attempt in range(3):
            try:
                resp = self._client().get(self.url, params=params, headers=self._headers(), timeout=self.timeout_seconds)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return _parse_predatory_lookup_response(resp.json(), journal=journal, publisher=publisher, issn=issn)
            except requests.RequestException:
                backoff_sleep(attempt)
            except Exception:
                return None
        return None

    def _lookup_from_list(self, *, journal: str | None, publisher: str | None, issn: str | None) -> dict | None:
        if self._list_cache is None:
            self._list_cache = self._fetch_list() or []

        journal_n = _norm_text(journal or "")
        publisher_n = _norm_text(publisher or "")
        issn_n = _norm_issn(issn or "")

        for rec in self._list_cache:
            if not isinstance(rec, dict):
                continue
            rec_issn = _norm_issn(str(rec.get("issn") or ""))
            rec_journal = _norm_text(str(rec.get("journal") or ""))
            rec_publisher = _norm_text(str(rec.get("publisher") or ""))

            if issn_n and rec_issn and issn_n == rec_issn:
                return rec
            if journal_n and rec_journal and (journal_n == rec_journal or rec_journal in journal_n):
                return rec
            if publisher_n and rec_publisher and (publisher_n == rec_publisher or rec_publisher in publisher_n):
                return rec
        return None

    def _fetch_list(self) -> list[dict] | None:
        for attempt in range(3):
            try:
                resp = self._client().get(self.url, headers=self._headers(), timeout=self.timeout_seconds)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return [d for d in data if isinstance(d, dict)]
                if isinstance(data, dict):
                    records = data.get("records") or data.get("items") or data.get("data")
                    if isinstance(records, list):
                        return [d for d in records if isinstance(d, dict)]
                return None
            except requests.RequestException:
                backoff_sleep(attempt)
            except Exception:
                return None
        return None


def _parse_predatory_lookup_response(payload: object, *, journal: str | None, publisher: str | None, issn: str | None) -> dict | None:
    if isinstance(payload, dict):
        if payload.get("match") is True and isinstance(payload.get("record"), dict):
            return payload["record"]
        if isinstance(payload.get("record"), dict):
            return payload["record"]
        records = payload.get("records") or payload.get("items") or payload.get("data")
        if isinstance(records, list):
            # If the API returns candidate records, apply the same matching logic.
            client = PredatoryApiClient(url="", mode="list")
            client._list_cache = [r for r in records if isinstance(r, dict)]
            return client._lookup_from_list(journal=journal, publisher=publisher, issn=issn)
        # Some APIs return a single record object.
        if any(k in payload for k in ("journal", "publisher", "issn")):
            return payload
        return None

    if isinstance(payload, list):
        client = PredatoryApiClient(url="", mode="list")
        client._list_cache = [r for r in payload if isinstance(r, dict)]
        return client._lookup_from_list(journal=journal, publisher=publisher, issn=issn)
    return None

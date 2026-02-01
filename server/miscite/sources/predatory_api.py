from __future__ import annotations

from dataclasses import dataclass, field

import requests

from server.miscite.core.cache import Cache
from server.miscite.sources.http import backoff_sleep


def _norm_text(s: str) -> str:
    return " ".join("".join(ch.lower() for ch in s.strip() if ch.isalnum() or ch.isspace()).split())


def _norm_issn(issn: str) -> str:
    return (issn or "").replace("-", "").strip().lower()


def _record_exact_match(record: dict, *, journal: str | None, publisher: str | None, issn: str | None) -> bool:
    issn_n = _norm_issn(issn or "")
    journal_n = _norm_text(journal or "")
    publisher_n = _norm_text(publisher or "")

    rec_issn = _norm_issn(str(record.get("issn") or ""))
    rec_journal = _norm_text(str(record.get("journal") or ""))
    rec_publisher = _norm_text(str(record.get("publisher") or ""))

    if issn_n and rec_issn and issn_n == rec_issn:
        return True
    if journal_n and rec_journal and journal_n == rec_journal:
        return True
    if publisher_n and rec_publisher and publisher_n == rec_publisher:
        return True
    return False


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
    cache: Cache | None = None

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

    def _ttl_seconds(self, suggested_days: int) -> float:
        cache = self.cache
        if not cache:
            return 0.0
        days = min(int(suggested_days), int(cache.settings.cache_http_ttl_days))
        return float(max(0, days)) * 86400.0

    def lookup(self, *, journal: str | None, publisher: str | None, issn: str | None) -> dict | None:
        if not self.url:
            return None
        cache = self.cache
        if cache and cache.settings.cache_enabled:
            hit, cached = cache.get_json(
                "predatory_api.lookup",
                [
                    self.mode,
                    self.url,
                    _norm_issn(issn or ""),
                    _norm_text(journal or ""),
                    _norm_text(publisher or ""),
                ],
            )
            if hit:
                return cached
        if self.mode == "list":
            return self._lookup_from_list(journal=journal, publisher=publisher, issn=issn)
        return self._lookup_via_http(journal=journal, publisher=publisher, issn=issn)

    def _lookup_via_http(self, *, journal: str | None, publisher: str | None, issn: str | None) -> dict | None:
        cache = self.cache
        cache_parts = [
            self.mode,
            self.url,
            _norm_issn(issn or ""),
            _norm_text(journal or ""),
            _norm_text(publisher or ""),
        ]
        params = {
            "issn": issn or "",
            "journal": journal or "",
            "publisher": publisher or "",
        }
        for attempt in range(3):
            try:
                resp = self._client().get(self.url, params=params, headers=self._headers(), timeout=self.timeout_seconds)
                if resp.status_code == 404:
                    if cache and cache.settings.cache_enabled:
                        cache.set_json("predatory_api.lookup", cache_parts, None, ttl_seconds=self._ttl_seconds(1))
                    return None
                resp.raise_for_status()
                record = _parse_predatory_lookup_response(resp.json(), journal=journal, publisher=publisher, issn=issn)
                if cache and cache.settings.cache_enabled:
                    cache.set_json("predatory_api.lookup", cache_parts, record, ttl_seconds=self._ttl_seconds(30))
                return record
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
            if journal_n and rec_journal and journal_n == rec_journal:
                return rec
            if publisher_n and rec_publisher and publisher_n == rec_publisher:
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
            record = payload["record"]
            return record if _record_exact_match(record, journal=journal, publisher=publisher, issn=issn) else None
        if isinstance(payload.get("record"), dict):
            record = payload["record"]
            return record if _record_exact_match(record, journal=journal, publisher=publisher, issn=issn) else None
        records = payload.get("records") or payload.get("items") or payload.get("data")
        if isinstance(records, list):
            # If the API returns candidate records, apply the same matching logic.
            client = PredatoryApiClient(url="", mode="list")
            client._list_cache = [r for r in records if isinstance(r, dict)]
            return client._lookup_from_list(journal=journal, publisher=publisher, issn=issn)
        # Some APIs return a single record object.
        if any(k in payload for k in ("journal", "publisher", "issn")):
            return payload if _record_exact_match(payload, journal=journal, publisher=publisher, issn=issn) else None
        return None

    if isinstance(payload, list):
        client = PredatoryApiClient(url="", mode="list")
        client._list_cache = [r for r in payload if isinstance(r, dict)]
        return client._lookup_from_list(journal=journal, publisher=publisher, issn=issn)
    return None

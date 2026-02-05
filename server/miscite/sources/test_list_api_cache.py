import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from server.miscite.core.cache import Cache
from server.miscite.core.config import Settings
from server.miscite.sources.predatory_api import PredatoryApiClient
from server.miscite.sources.retraction_api import RetractionApiClient


class _RaisingSession:
    def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("HTTP should not be called when cache is populated.")


class _StubResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self):  # type: ignore[no-untyped-def]
        return self._payload


class _CountingSession:
    def __init__(self, payload: object) -> None:
        self._payload = payload
        self.calls = 0

    def get(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return _StubResponse(self._payload)


class TestListApiCache(unittest.TestCase):
    def test_predatory_list_reads_from_file_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(Settings.from_env(), cache_enabled=True, cache_dir=Path(tmp))
            cache = Cache(settings=settings)
            client = PredatoryApiClient(url="https://example.test/predatory", token="tok", mode="list", cache=cache)

            records = [{"journal": "A"}, {"publisher": "B"}]
            cache.set_text_file("predatory_api.list", [client.mode, client.url, client.token or ""], json.dumps(records))

            client._session = _RaisingSession()  # type: ignore[assignment]
            self.assertEqual(client._fetch_list(), records)

    def test_predatory_list_written_then_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(Settings.from_env(), cache_enabled=True, cache_dir=Path(tmp))
            cache = Cache(settings=settings)
            payload = [{"journal": "A"}]

            first = PredatoryApiClient(url="https://example.test/predatory", token="tok", mode="list", cache=cache)
            session = _CountingSession(payload)
            first._session = session  # type: ignore[assignment]
            self.assertEqual(first._fetch_list(), payload)
            self.assertEqual(session.calls, 1)

            second = PredatoryApiClient(url="https://example.test/predatory", token="tok", mode="list", cache=cache)
            second._session = _RaisingSession()  # type: ignore[assignment]
            self.assertEqual(second._fetch_list(), payload)

    def test_retraction_list_reads_from_file_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(Settings.from_env(), cache_enabled=True, cache_dir=Path(tmp))
            cache = Cache(settings=settings)
            client = RetractionApiClient(url="https://example.test/retractions", token="tok", mode="list", cache=cache)

            records = [{"doi": "10.1234/abc", "is_retracted": True}]
            cache.set_text_file("retraction_api.list", [client.mode, client.url, client.token or ""], json.dumps(records))

            client._session = _RaisingSession()  # type: ignore[assignment]
            self.assertEqual(client._fetch_list(), records)

    def test_retraction_list_written_then_reused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            settings = replace(Settings.from_env(), cache_enabled=True, cache_dir=Path(tmp))
            cache = Cache(settings=settings)
            payload = [{"doi": "10.1234/abc", "is_retracted": True}]

            first = RetractionApiClient(url="https://example.test/retractions", token="tok", mode="list", cache=cache)
            session = _CountingSession(payload)
            first._session = session  # type: ignore[assignment]
            self.assertEqual(first._fetch_list(), payload)
            self.assertEqual(session.calls, 1)

            second = RetractionApiClient(url="https://example.test/retractions", token="tok", mode="list", cache=cache)
            second._session = _RaisingSession()  # type: ignore[assignment]
            self.assertEqual(second._fetch_list(), payload)


if __name__ == "__main__":
    unittest.main()


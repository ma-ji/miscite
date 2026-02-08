import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from server.miscite.core.cache import Cache
from server.miscite.core.config import Settings
from server.miscite.core.migrations import upgrade_to_head
from server.miscite.llm.openrouter import OpenRouterClient


class _StubResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):  # type: ignore[no-untyped-def]
        return self._payload


class _StubSession:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls = 0

    def post(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        return _StubResponse(self._payload)


class TestOpenRouterCacheDebug(unittest.TestCase):
    def test_http_request_metric_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                Settings.from_env(),
                db_url=f"sqlite:///{root / 'openrouter-cache-debug.db'}",
                cache_enabled=True,
                cache_dir=root / "cache",
                cache_llm_ttl_days=30,
            )
            upgrade_to_head(settings)
            cache = Cache(settings=settings)
            client = OpenRouterClient(api_key="test-key", model="test/model", cache=cache)

            session = _StubSession(
                {
                    "model": "test/model",
                    "choices": [{"message": {"content": '{"ok": 1}'}}],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }
            )
            client._session_local.session = session

            out = client.chat_json(system="s", user="u")
            self.assertEqual(out, {"ok": 1})
            self.assertEqual(session.calls, 1)

            snap = cache.debug_snapshot()
            ns = (snap.get("namespaces") or {}).get("openrouter.chat_json") or {}
            self.assertEqual(ns.get("http_request"), 1)


if __name__ == "__main__":
    unittest.main()

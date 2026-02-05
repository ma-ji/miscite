import unittest

from server.miscite.worker import _cache_debug_summary


class TestCacheDebugSummary(unittest.TestCase):
    def test_formats_totals_and_top_namespaces(self) -> None:
        summary = _cache_debug_summary(
            {
                "totals": {
                    "json_get_hit": 4,
                    "json_get_miss": 2,
                    "file_get_hit": 3,
                    "file_get_error": 1,
                    "json_set_ok": 5,
                    "http_request": 11,
                },
                "namespaces": {
                    "openalex.work_by_id": {"json_get_hit": 3, "json_get_miss": 1, "http_request": 2},
                    "openalex.list_citing_works": {"json_get_hit": 2, "json_get_miss": 1},
                    "openrouter.chat_json": {"json_get_hit": 1, "file_get_hit": 2, "json_get_miss": 0},
                },
            }
        )
        self.assertIsInstance(summary, str)
        assert summary is not None
        self.assertIn("hits=7", summary)
        self.assertIn("json_hits=4", summary)
        self.assertIn("file_hits=3", summary)
        self.assertIn("misses=2", summary)
        self.assertIn("http_calls=11", summary)
        self.assertIn("errors=1", summary)
        self.assertIn("cache_writes=5", summary)
        self.assertIn("top=", summary)
        self.assertIn("openalex.work_by_id", summary)
        self.assertIn("http=2", summary)
        self.assertIn("jh=3", summary)
        self.assertIn("fh=2", summary)

    def test_returns_none_for_invalid_payload(self) -> None:
        self.assertIsNone(_cache_debug_summary(None))
        self.assertIsNone(_cache_debug_summary("bad"))


if __name__ == "__main__":
    unittest.main()

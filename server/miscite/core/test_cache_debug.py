import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from server.miscite.core.cache import Cache
from server.miscite.core.config import Settings
from server.miscite.core.migrations import upgrade_to_head


class TestCacheDebug(unittest.TestCase):
    def test_debug_snapshot_counts_hits_and_misses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                Settings.from_env(),
                db_url=f"sqlite:///{root / 'cache-debug.db'}",
                cache_enabled=True,
                cache_dir=root / "cache",
            )
            upgrade_to_head(settings)
            cache = Cache(settings=settings)

            self.assertEqual(cache.get_json("demo.json", ["k1"]), (False, None))
            cache.set_json("demo.json", ["k1"], {"ok": 1}, ttl_seconds=60.0)
            self.assertEqual(cache.get_json("demo.json", ["k1"]), (True, {"ok": 1}))

            self.assertEqual(cache.get_text_file("demo.file", ["f1"], ttl_days=1), (False, ""))
            cache.set_text_file("demo.file", ["f1"], "hello")
            self.assertEqual(cache.get_text_file("demo.file", ["f1"], ttl_days=1), (True, "hello"))

            snap = cache.debug_snapshot()
            totals = snap.get("totals") or {}
            self.assertEqual(totals.get("json_get_miss"), 1)
            self.assertEqual(totals.get("json_set_ok"), 1)
            self.assertEqual(totals.get("json_get_hit"), 1)
            self.assertEqual(totals.get("file_get_miss"), 1)
            self.assertEqual(totals.get("file_set_ok"), 1)
            self.assertEqual(totals.get("file_get_hit"), 1)

    def test_scoped_caches_share_debug_stats(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                Settings.from_env(),
                db_url=f"sqlite:///{root / 'cache-debug-scope.db'}",
                cache_enabled=True,
                cache_dir=root / "cache",
            )
            upgrade_to_head(settings)
            cache = Cache(settings=settings)
            scoped = cache.scoped("doc:abc123")

            self.assertIs(cache.debug_stats, scoped.debug_stats)
            self.assertEqual(scoped.get_json("scoped.ns", ["k"]), (False, None))

            snap = cache.debug_snapshot()
            namespace_stats = (snap.get("namespaces") or {}).get("scoped.ns") or {}
            self.assertEqual(namespace_stats.get("json_get_miss"), 1)


if __name__ == "__main__":
    unittest.main()

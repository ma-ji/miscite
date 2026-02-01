import unittest
from pathlib import Path

from server.miscite.analysis.pipeline import _text_extract_cache_parts
from server.miscite.core.cache import Cache
from server.miscite.core.config import Settings


class TestTextExtractCacheParts(unittest.TestCase):
    def test_sha_scoped_parts_ignore_storage_path(self) -> None:
        settings = Settings.from_env()
        sha = "a" * 64
        parts_a = _text_extract_cache_parts(settings, document_sha256=sha, path=Path("/tmp/upload-a.pdf"))
        parts_b = _text_extract_cache_parts(settings, document_sha256=sha, path=Path("/tmp/upload-b.pdf"))
        self.assertEqual(parts_a, parts_b)

        cache = Cache(settings=settings).scoped(f"doc:{sha}")
        file_a = cache._file_path("text_extract", parts_a, ext="txt")
        file_b = cache._file_path("text_extract", parts_b, ext="txt")
        self.assertEqual(file_a, file_b)

    def test_no_sha_includes_path_to_avoid_collisions(self) -> None:
        settings = Settings.from_env()
        parts_a = _text_extract_cache_parts(settings, document_sha256=None, path=Path("/tmp/upload-a.pdf"))
        parts_b = _text_extract_cache_parts(settings, document_sha256=None, path=Path("/tmp/upload-b.pdf"))
        self.assertNotEqual(parts_a, parts_b)


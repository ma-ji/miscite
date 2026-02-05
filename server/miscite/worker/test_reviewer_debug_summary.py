import unittest

from server.miscite.worker import _reviewer_debug_summary


class TestReviewerDebugSummary(unittest.TestCase):
    def test_summary_contains_core_fields(self) -> None:
        deep_analysis = {
            "status": "completed",
            "reviewer_debug": {
                "reviewers": 3,
                "order_rule": "degree",
                "coupling_rids_total": 80,
                "coupling_rids_top": 50,
                "recent_years": 10,
                "cutoff_year": 2017,
                "recent_rids": 12,
                "cited_sources_count": 6,
                "cited_sources_sample": ["journal a", "journal b"],
                "cited_sources_override_refs_total": 120,
                "cited_sources_override_refs_with_source": 110,
                "works_missing_authors": 2,
                "authors_missing_id": 1,
                "authors_seen": 20,
                "authors_with_cited_source": 5,
                "coupling_work_lookups": 10,
                "coupling_work_results": 8,
                "author_work_lookups": 8,
                "author_work_results": 6,
                "author_work_total": 42,
            },
        }
        summary = _reviewer_debug_summary(deep_analysis)
        self.assertIsInstance(summary, str)
        assert summary is not None
        self.assertIn("reviewers=3", summary)
        self.assertIn("order_rule=degree", summary)
        self.assertIn("coupling_total=80", summary)
        self.assertIn("coupling_top=50", summary)
        self.assertIn("recent_years=10", summary)
        self.assertIn("cutoff_year=2017", summary)
        self.assertIn("recent_works=12", summary)
        self.assertIn("cited_sources=6", summary)
        self.assertIn("cited_refs_total=120", summary)
        self.assertIn("cited_refs_with_source=110", summary)
        self.assertIn("cited_sources_sample=journal a|journal b", summary)
        self.assertIn("missing_authors=2", summary)
        self.assertIn("authors_seen=20", summary)
        self.assertIn("authors_in_cited_sources=5", summary)
        self.assertIn("coupling_work_lookups=10", summary)
        self.assertIn("coupling_work_results=8", summary)
        self.assertIn("author_work_lookups=8", summary)
        self.assertIn("author_work_results=6", summary)
        self.assertIn("author_work_total=42", summary)
        self.assertIn("authors_missing_id=1", summary)

    def test_summary_skips_non_completed(self) -> None:
        deep_analysis = {"status": "failed", "reviewer_debug": {"reviewers": 1}}
        self.assertIsNone(_reviewer_debug_summary(deep_analysis))


if __name__ == "__main__":
    unittest.main()

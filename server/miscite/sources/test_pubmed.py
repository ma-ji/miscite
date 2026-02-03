import unittest

from server.miscite.sources.pubmed import _summarize_summary_record


class TestPubMedSummaryParsing(unittest.TestCase):
    def test_first_author_family_uses_surname_for_initials_format(self) -> None:
        record = {
            "uid": "32861308",
            "title": "Test title",
            "authors": [{"name": "Smyth EC"}],
            "pubdate": "2020 Aug 29",
            "fulljournalname": "The Lancet",
            "articleids": [],
        }
        summarized = _summarize_summary_record(record)
        self.assertEqual(summarized.get("first_author"), "smyth")

    def test_first_author_family_handles_comma_format(self) -> None:
        record = {
            "uid": "123",
            "title": "Test title",
            "authors": [{"name": "Smyth, EC"}],
            "pubdate": "2020",
            "articleids": [],
        }
        summarized = _summarize_summary_record(record)
        self.assertEqual(summarized.get("first_author"), "smyth")

    def test_first_author_family_falls_back_for_group_author(self) -> None:
        record = {
            "uid": "999",
            "title": "Test title",
            "authors": [{"name": "World Health Organization"}],
            "pubdate": "2020",
            "articleids": [],
        }
        summarized = _summarize_summary_record(record)
        self.assertEqual(summarized.get("first_author"), "world")


if __name__ == "__main__":
    unittest.main()


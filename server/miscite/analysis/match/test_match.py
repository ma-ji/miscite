import unittest

from server.miscite.analysis.match.index import build_reference_index
from server.miscite.analysis.match.match import match_citations_to_references
from server.miscite.analysis.parse.citation_parsing import CitationInstance, ReferenceEntry
from server.miscite.analysis.parse.llm_parsing import parse_references_with_llm
from server.miscite.analysis.shared.normalize import normalize_author_name


class TestCitationBibliographyMatching(unittest.TestCase):
    def test_normalize_author_name_collapses_dotless_i(self) -> None:
        self.assertEqual(normalize_author_name("Çorbacıo˘ glu"), "corbacioglu")

    def test_matches_unicode_author_with_ocr_split(self) -> None:
        citations = [
            CitationInstance(
                kind="author_year",
                raw="(Çorbacıo˘ glu & Aksel, 2023)",
                locator="çorbacıo˘ glu & aksel, 2023",
                context="x",
            )
        ]
        references = [
            ReferenceEntry(
                ref_id="ref-1",
                raw="Corbacioglu, A., & Aksel, M. (2023). Example title.",
                ref_number=None,
                doi=None,
                year=2023,
                first_author="corbacioglu",
            )
        ]
        matches = match_citations_to_references(citations, references, reference_records={})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, "matched")
        self.assertIsNotNone(matches[0].ref)
        self.assertEqual(matches[0].ref.ref_id, "ref-1")

    def test_matches_when_locator_includes_multiple_authors(self) -> None:
        citations = [
            CitationInstance(
                kind="author_year",
                raw="(Varela, Thompson, & Rosch, 1991)",
                locator="varela, thompson, & rosch, 1991",
                context="x",
            )
        ]
        references = [
            ReferenceEntry(
                ref_id="ref-1",
                raw="Varela, F. J., Thompson, E., & Rosch, E. (1991). The Embodied Mind.",
                ref_number=None,
                doi=None,
                year=1991,
                first_author="varela",
            )
        ]
        matches = match_citations_to_references(citations, references, reference_records={})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, "matched")
        self.assertIsNotNone(matches[0].ref)
        self.assertEqual(matches[0].ref.ref_id, "ref-1")

    def test_matches_when_year_suffix_missing_in_bibliography(self) -> None:
        citations = [
            CitationInstance(
                kind="author_year",
                raw="(Matta, 2026a)",
                locator="matta-2026a",
                context="x",
            )
        ]
        references = [
            ReferenceEntry(
                ref_id="ref-1",
                raw="Matta. (2026). Some title.",
                ref_number=None,
                doi=None,
                year=2026,
                first_author="matta",
            )
        ]
        matches = match_citations_to_references(citations, references, reference_records={})
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, "matched")
        self.assertIsNotNone(matches[0].ref)
        self.assertEqual(matches[0].ref.ref_id, "ref-1")

    def test_prebuilt_reference_index_matches_default_path(self) -> None:
        citations = [
            CitationInstance(
                kind="author_year",
                raw="(Matta, 2026a)",
                locator="matta-2026a",
                context="x",
            ),
            CitationInstance(
                kind="author_year",
                raw="(Varela, Thompson, & Rosch, 1991)",
                locator="varela, thompson, & rosch, 1991",
                context="x",
            ),
        ]
        references = [
            ReferenceEntry(
                ref_id="ref-1",
                raw="Matta. (2026). Some title.",
                ref_number=None,
                doi=None,
                year=2026,
                first_author="matta",
            ),
            ReferenceEntry(
                ref_id="ref-2",
                raw="Varela, F. J., Thompson, E., & Rosch, E. (1991). The Embodied Mind.",
                ref_number=None,
                doi=None,
                year=1991,
                first_author="varela",
            ),
        ]
        reference_records: dict[str, dict] = {}
        default_matches = match_citations_to_references(
            citations,
            references,
            reference_records=reference_records,
        )
        prebuilt_index = build_reference_index(
            references,
            reference_records=reference_records,
        )
        indexed_matches = match_citations_to_references(
            citations,
            references,
            reference_records=reference_records,
            reference_index=prebuilt_index,
        )
        self.assertEqual(default_matches, indexed_matches)


class _StubLlm:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def chat_json(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        return self._payload


class TestLlmBibliographyParsing(unittest.TestCase):
    def test_sanitizes_first_author_to_family_name(self) -> None:
        llm = _StubLlm(
            {
                "references": [
                    {
                        "id": "ref-1",
                        "raw": "Varela, F. J., Thompson, E., & Rosch, E. (1991). The Embodied Mind.",
                        "ref_number": None,
                        "doi": None,
                        "year": 1991,
                        "first_author": "Varela, Thompson, & Rosch",
                        "csl": None,
                    }
                ],
                "notes": [],
            }
        )
        references, _, _ = parse_references_with_llm(llm, "dummy", max_chars=1000, max_refs=50)
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].first_author, "varela")

    def test_drops_trailing_initials_from_first_author(self) -> None:
        llm = _StubLlm(
            {
                "references": [
                    {
                        "id": "ref-1",
                        "raw": "Smyth EC. Test Title. 2020.",
                        "ref_number": None,
                        "doi": None,
                        "year": 2020,
                        "first_author": "Smyth EC",
                        "csl": None,
                    }
                ],
                "notes": [],
            }
        )
        references, _, _ = parse_references_with_llm(llm, "dummy", max_chars=1000, max_refs=50)
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].first_author, "smyth")

    def test_drops_trailing_year_suffix_from_first_author(self) -> None:
        llm = _StubLlm(
            {
                "references": [
                    {
                        "id": "ref-1",
                        "raw": "Matta. (2026a). Some title.",
                        "ref_number": None,
                        "doi": None,
                        "year": 2026,
                        "first_author": "Matta (2026a)",
                        "csl": None,
                    }
                ],
                "notes": [],
            }
        )
        references, _, _ = parse_references_with_llm(llm, "dummy", max_chars=1000, max_refs=50)
        self.assertEqual(len(references), 1)
        self.assertEqual(references[0].first_author, "matta")


if __name__ == "__main__":
    unittest.main()

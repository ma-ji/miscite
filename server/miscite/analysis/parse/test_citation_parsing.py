import unittest

from server.miscite.analysis.parse.citation_parsing import CitationInstance, normalize_llm_citations, split_multi_citations


class TestCitationSplittingHtmlEntities(unittest.TestCase):
    def test_normalize_does_not_split_on_html_entity_semicolon(self) -> None:
        citations = [
            CitationInstance(
                kind="author_year",
                raw="(Greenlee &amp; Trussel, 2000)",
                locator="greenlee-2000",
                context="x",
            )
        ]

        normalized = normalize_llm_citations(citations)
        self.assertEqual(len(normalized), 1)
        self.assertEqual(normalized[0].locator, "greenlee-2000")
        self.assertEqual(normalized[0].raw, "(Greenlee &amp; Trussel, 2000)")

    def test_split_multi_citations_ignores_html_entity_semicolons(self) -> None:
        citations = [
            CitationInstance(
                kind="author_year",
                raw="(Greenlee &amp; Trussel, 2000; Hodge &amp; Piccolo, 2005; Trussel, 2002)",
                locator="greenlee-2000",
                context="x",
            )
        ]

        split = split_multi_citations(citations)
        self.assertEqual([c.locator for c in split], ["greenlee-2000", "hodge-2005", "trussel-2002"])
        self.assertEqual(
            [c.raw for c in split],
            ["(Greenlee & Trussel, 2000)", "(Hodge & Piccolo, 2005)", "(Trussel, 2002)"],
        )

    def test_normalize_splits_multi_citations_with_html_entities(self) -> None:
        citations = [
            CitationInstance(
                kind="author_year",
                raw="(Greenlee &amp; Trussel, 2000; Hodge &amp; Piccolo, 2005; Trussel, 2002)",
                locator="greenlee-2000",
                context="x",
            )
        ]

        normalized = normalize_llm_citations(citations)
        self.assertEqual([c.locator for c in normalized], ["greenlee-2000", "hodge-2005", "trussel-2002"])
        self.assertEqual(
            [c.raw for c in normalized],
            ["(Greenlee & Trussel, 2000)", "(Hodge & Piccolo, 2005)", "(Trussel, 2002)"],
        )


if __name__ == "__main__":
    unittest.main()


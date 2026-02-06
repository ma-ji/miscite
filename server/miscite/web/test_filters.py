import unittest

from server.miscite.web import deep_cite_links
from server.miscite.web import reference_sources


class TestDeepCiteLinks(unittest.TestCase):
    def test_adds_tooltip_when_reference_payload_available(self) -> None:
        html = str(
            deep_cite_links(
                "See [R12] for details.",
                {
                    "R12": {
                        "apa": "Doe, J. (2024). Example title. Journal of Tests, 12(3), 1-10.",
                    }
                },
            )
        )
        self.assertIn('href="#da-ref-R12"', html)
        self.assertIn('title="Doe, J. (2024). Example title. Journal of Tests, 12(3), 1-10."', html)
        self.assertIn('aria-label="Doe, J. (2024). Example title. Journal of Tests, 12(3), 1-10."', html)

    def test_falls_back_without_tooltip(self) -> None:
        html = str(deep_cite_links("See [R7] for details."))
        self.assertIn('href="#da-ref-R7"', html)
        self.assertNotIn("title=", html)

    def test_tooltip_excludes_source_names(self) -> None:
        html = str(
            deep_cite_links(
                "Compare [R5].",
                {
                    "R5": {
                        "apa_base": "Smith, A. (2022). Methods paper.",
                        "source": "Journal of Methods",
                        "venue": "Journal of Methods",
                        "publisher": "Science Press",
                    }
                },
            )
        )
        self.assertIn('title="Smith, A. (2022). Methods paper."', html)
        self.assertNotIn("Source:", html)


class TestReferenceSources(unittest.TestCase):
    def test_keeps_publication_source_names(self) -> None:
        labels = reference_sources(
            {
                "source": "Journal of Methods",
                "venue": "Journal of Methods",
                "publisher": "Science Press",
            }
        )
        self.assertEqual(labels, ["Journal of Methods", "Science Press"])

    def test_excludes_database_source_names(self) -> None:
        labels = reference_sources(
            {
                "source": "OpenAlex",
                "venue": "Crossref",
                "publisher": "Science Press",
            }
        )
        self.assertEqual(labels, ["Science Press"])


if __name__ == "__main__":
    unittest.main()

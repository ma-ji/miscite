import unittest

from server.miscite.analysis.deep_analysis.reviewers import build_potential_reviewers_from_coupling


class _OpenAlexStub:
    def __init__(self, works_by_author: dict[str, list[dict]], default_works: list[dict] | None = None):
        self._works_by_author = works_by_author
        self._default_works = default_works or []

    def list_author_works(self, author_id: str, *, rows: int = 100) -> list[dict]:
        return list(self._works_by_author.get(author_id, self._default_works))[:rows]


def _ref(
    year: int,
    author_name: str,
    *,
    source: str = "",
    venue: str = "",
    in_paper: bool = False,
    author_id: str | None = None,
) -> dict:
    return {
        "year": year,
        "source": source,
        "venue": venue,
        "in_paper": in_paper,
        "authors_detailed": [
            {
                "name": author_name,
                "author_id": author_id or author_name.lower().replace(" ", "_"),
                "affiliation": f"{author_name} University",
            }
        ],
    }


def _ref_multi(
    year: int,
    authors: list[dict],
    *,
    source: str = "",
    venue: str = "",
    in_paper: bool = False,
) -> dict:
    return {
        "year": year,
        "source": source,
        "venue": venue,
        "in_paper": in_paper,
        "authors_detailed": authors,
    }


class TestReviewers(unittest.TestCase):
    def test_uses_only_top_50_in_original_coupling_order(self) -> None:
        coupling_rids = [f"R{i}" for i in range(1, 56)]
        references_by_rid = {
            rid: _ref(2024, f"Author {i:02d}", source="Journal A")
            for i, rid in enumerate(coupling_rids, start=1)
        }
        references_by_rid["P1"] = _ref(2019, "Seed Author", source="Journal A", in_paper=True)

        reviewers = build_potential_reviewers_from_coupling(
            coupling_rids=coupling_rids,
            references_by_rid=references_by_rid,
            current_year=2026,
            openalex=_OpenAlexStub({}, default_works=[{"host_venue": {"display_name": "Journal A"}}]),
        )

        names = {r["name"] for r in reviewers}
        self.assertEqual(len(names), 50)
        self.assertIn("Author 01", names)
        self.assertIn("Author 50", names)
        self.assertNotIn("Author 51", names)
        self.assertNotIn("Author 55", names)

    def test_keeps_only_recent_works_from_past_10_years(self) -> None:
        coupling_rids = ["R1", "R2", "R3"]
        references_by_rid = {
            "R1": _ref(2026, "Recent Author", source="Journal A"),
            "R2": _ref(2017, "Cutoff Author", source="Journal A"),
            "R3": _ref(2016, "Old Author", source="Journal A"),
            "P1": _ref(2020, "Seed Author", source="Journal A", in_paper=True),
        }

        reviewers = build_potential_reviewers_from_coupling(
            coupling_rids=coupling_rids,
            references_by_rid=references_by_rid,
            current_year=2026,
            openalex=_OpenAlexStub(
                {
                    "recent_author": [{"host_venue": {"display_name": "Journal A"}}],
                    "cutoff_author": [{"host_venue": {"display_name": "Journal A"}}],
                }
            ),
        )

        names = {r["name"] for r in reviewers}
        self.assertIn("Recent Author", names)
        self.assertIn("Cutoff Author", names)
        self.assertNotIn("Old Author", names)

    def test_keeps_authors_with_publication_in_cited_sources(self) -> None:
        coupling_rids = ["R1", "R2", "R3", "R4"]
        references_by_rid = {
            "R1": _ref(2025, "Alice", source="Journal A", author_id="A1"),
            "R2": _ref(2025, "Bob", source="Journal B", author_id="B1"),
            "R3": _ref(2024, "Alice", source="Journal C", author_id="A1"),
            "R4": _ref(2023, "Carol", venue="Journal A", author_id="C1"),
            "P1": _ref(2022, "Seed Author", source="Journal A", in_paper=True),
        }

        reviewers = build_potential_reviewers_from_coupling(
            coupling_rids=coupling_rids,
            references_by_rid=references_by_rid,
            current_year=2026,
            openalex=_OpenAlexStub(
                {
                    "A1": [{"host_venue": {"display_name": "Journal A"}}],
                    "B1": [{"host_venue": {"display_name": "Journal B"}}],
                    "C1": [{"primary_location": {"source": {"display_name": "Journal A"}}}],
                }
            ),
        )

        names = {r["name"] for r in reviewers}
        self.assertIn("Alice", names)
        self.assertIn("Carol", names)
        self.assertNotIn("Bob", names)

    def test_recent_years_zero_includes_all_years(self) -> None:
        coupling_rids = ["R1", "R2"]
        references_by_rid = {
            "R1": _ref(2010, "Alice", source="Journal A"),
            "R2": _ref(2024, "Bob", source="Journal A"),
            "P1": _ref(2022, "Seed Author", source="Journal A", in_paper=True),
        }

        reviewers = build_potential_reviewers_from_coupling(
            coupling_rids=coupling_rids,
            references_by_rid=references_by_rid,
            recent_years=0,
            current_year=2026,
            openalex=_OpenAlexStub(
                {
                    "alice": [{"host_venue": {"display_name": "Journal A"}}],
                    "bob": [{"host_venue": {"display_name": "Journal A"}}],
                }
            ),
        )

        names = {r["name"] for r in reviewers}
        self.assertIn("Alice", names)
        self.assertIn("Bob", names)

    def test_orders_by_degree_centrality_by_default(self) -> None:
        coupling_rids = ["R1", "R2", "R3"]
        references_by_rid = {
            "R1": _ref_multi(
                2025,
                [
                    {"name": "Alice", "author_id": "A1", "affiliation": "A University"},
                    {"name": "Bob", "author_id": "B1", "affiliation": "B University"},
                ],
                source="Journal A",
            ),
            "R2": _ref_multi(
                2024,
                [
                    {"name": "Alice", "author_id": "A1", "affiliation": "A University"},
                    {"name": "Carol", "author_id": "C1", "affiliation": "C University"},
                ],
                source="Journal A",
            ),
            "R3": _ref_multi(
                2023,
                [
                    {"name": "Alice", "author_id": "A1", "affiliation": "A University"},
                    {"name": "Dan", "author_id": "D1", "affiliation": "D University"},
                ],
                source="Journal A",
            ),
            "P1": _ref(2022, "Seed Author", source="Journal A", in_paper=True),
        }

        reviewers = build_potential_reviewers_from_coupling(
            coupling_rids=coupling_rids,
            references_by_rid=references_by_rid,
            current_year=2026,
            openalex=_OpenAlexStub(
                {
                    "A1": [{"host_venue": {"display_name": "Journal A"}}],
                    "B1": [{"host_venue": {"display_name": "Journal A"}}],
                    "C1": [{"host_venue": {"display_name": "Journal A"}}],
                    "D1": [{"host_venue": {"display_name": "Journal A"}}],
                }
            ),
        )

        self.assertEqual(reviewers[0]["name"], "Alice")


if __name__ == "__main__":
    unittest.main()

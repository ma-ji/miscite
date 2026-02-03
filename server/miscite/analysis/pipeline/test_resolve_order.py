import unittest

from server.miscite.analysis.parse.citation_parsing import ReferenceEntry
from server.miscite.analysis.pipeline.resolve import resolve_references
from server.miscite.core.config import Settings


class _StubOpenAlex:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def get_work_by_doi(self, doi: str) -> dict | None:
        self.calls.append(("get_work_by_doi", doi))
        return None

    def get_work_by_id(self, openalex_id: str) -> dict | None:
        self.calls.append(("get_work_by_id", openalex_id))
        return None

    def search(self, query: str, *, rows: int = 5) -> list[dict]:
        self.calls.append(("search", query))
        return [
            {
                "id": "W123",
                "display_name": "Test Title",
                "publication_year": 2020,
                "doi": "10.1234/abc",
            }
        ]


class _FailingClient:
    def __getattr__(self, name: str):  # type: ignore[override]
        raise AssertionError(f"Unexpected call: {name}")


class _StubLlm:
    def chat_json(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("LLM should not be called in this test.")


class TestResolveOrder(unittest.TestCase):
    def test_pmid_does_not_change_lookup_order(self) -> None:
        settings = Settings.from_env()

        refs = [
            ReferenceEntry(
                ref_id="1",
                raw="Smyth EC. Test Title. 2020.",
                ref_number=1,
                doi=None,
                year=2020,
                first_author="smyth",
            )
        ]
        reference_records = {"1": {"title": "Test Title", "PMID": "32861308"}}

        openalex = _StubOpenAlex()
        crossref = _FailingClient()
        pubmed = _FailingClient()
        arxiv = _FailingClient()

        resolved_by_ref_id, llm_calls = resolve_references(
            settings=settings,
            references=refs,
            reference_records=reference_records,
            openalex=openalex,
            crossref=crossref,
            pubmed=pubmed,
            arxiv=arxiv,
            llm_match_client=_StubLlm(),
            llm_call_budget=0,
        )
        self.assertEqual(llm_calls, 0)
        self.assertIn("1", resolved_by_ref_id)
        resolved = resolved_by_ref_id["1"]
        self.assertEqual(resolved.source, "openalex")
        self.assertEqual(resolved.pmid, "32861308")
        self.assertTrue(openalex.calls and openalex.calls[0][0] == "search")


if __name__ == "__main__":
    unittest.main()


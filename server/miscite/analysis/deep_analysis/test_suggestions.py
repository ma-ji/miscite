import unittest

from server.miscite.analysis.deep_analysis.suggestions import _validate_llm_suggestions


class TestSuggestions(unittest.TestCase):
    def test_validate_llm_suggestions_enforces_shape_and_anchor(self) -> None:
        excerpt = (
            "Introduction We frame the central question around evidence quality. "
            "Methods We estimate effects using a constrained model."
        )
        payload = {
            "overview": "Priority 1: strengthen support [R1].",
            "items": [
                {
                    "section_title": "Introduction",
                    "action_type": "add",
                    "rid": "R1",
                    "priority": "high",
                    "action": "Add this work to support the opening claim.",
                    "why": "The opening claim currently has thin support.",
                    "where": "After the first sentence.",
                    "anchor_quote": "not in excerpt",
                }
            ],
        }
        out = _validate_llm_suggestions(
            payload,
            allowed_rids={"R1"},
            allowed_sections={"Introduction", "Methods"},
            excerpt=excerpt,
            section_anchors={"Introduction": "We frame the central question around evidence quality."},
            default_anchor="We estimate effects using a constrained model.",
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["items"][0]["section_title"], "Introduction")
        self.assertEqual(
            out["items"][0]["anchor_quote"],
            "We frame the central question around evidence quality.",
        )

    def test_validate_llm_suggestions_rejects_invalid_payload(self) -> None:
        out = _validate_llm_suggestions(
            {"overview": "bad", "items": [{"section_title": "Intro"}]},
            allowed_rids={"R1"},
            allowed_sections={"Intro"},
            excerpt="Intro text",
            section_anchors={"Intro": "Intro text"},
            default_anchor="Intro text",
        )
        self.assertIsNone(out)


if __name__ == "__main__":
    unittest.main()

import unittest

from server.miscite.analysis.deep_analysis.subsection_recommendations import (
    _heuristic_plan,
    _validate_plan,
)


class TestSubsectionRecommendations(unittest.TestCase):
    def test_validate_plan_normalizes_and_filters(self) -> None:
        section_text = (
            "This section introduces the main model choice. "
            "We then compare alternatives under the same assumptions."
        )
        payload = {
            "summary": "Refine this section.",
            "improvements": [
                {
                    "priority": 1,
                    "action_type": "invalid",
                    "action": "Clarify why this citation is used.",
                    "why": "The support is not explicit.",
                    "where": "After the first claim sentence.",
                    "anchor_quote": "not present in section",
                    "rids": ["R1", "R99"],
                }
            ],
            "reference_integrations": [
                {
                    "rid": "R2",
                    "priority": "high",
                    "action_type": "add",
                    "action": "Add this nearby evidence.",
                    "why": "It strengthens support for the claim.",
                    "where": "After model choice sentence.",
                    "anchor_quote": "This section introduces the main model choice.",
                    "example": "Prior work supports this choice [R2].",
                },
                {
                    "rid": "R3",
                    "priority": "high",
                    "action_type": "add",
                    "action": "Should be filtered.",
                    "why": "Filtered due to disallowed integration rid.",
                    "where": "Anywhere.",
                    "anchor_quote": "This section introduces the main model choice.",
                    "example": "Filtered [R3].",
                },
            ],
            "questions": ["What is the primary claim?"],
        }

        out = _validate_plan(
            payload,
            allowed_rids={"R1", "R2", "R3"},
            allowed_integration_rids={"R2"},
            section_text=section_text,
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(len(out["improvements"]), 1)
        self.assertEqual(out["improvements"][0]["action_type"], "strengthen")
        self.assertEqual(out["improvements"][0]["rids"], ["R1"])
        self.assertEqual(len(out["reference_integrations"]), 1)
        self.assertEqual(out["reference_integrations"][0]["rid"], "R2")
        self.assertIn("This section introduces the main model choice", out["improvements"][0]["anchor_quote"])

    def test_heuristic_plan_includes_anchor_quotes(self) -> None:
        plan = _heuristic_plan(
            [
                {"rid": "R1", "distance": 1, "in_paper": False, "cited_in_subsection": False},
                {"rid": "R2", "distance": 2, "in_paper": True, "cited_in_subsection": False},
            ],
            section_text=(
                "We define the estimation strategy here. "
                "The assumptions are then evaluated against prior studies."
            ),
        )
        self.assertTrue(plan.get("improvements"))
        self.assertTrue(plan.get("reference_integrations"))
        self.assertTrue(plan["improvements"][0].get("anchor_quote"))
        self.assertTrue(plan["reference_integrations"][0].get("anchor_quote"))


if __name__ == "__main__":
    unittest.main()

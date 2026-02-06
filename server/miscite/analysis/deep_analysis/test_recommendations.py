import unittest

from server.miscite.analysis.deep_analysis.recommendations import build_recommendations


class TestRecommendations(unittest.TestCase):
    def test_merges_and_limits_actions(self) -> None:
        suggestions = {
            "status": "completed",
            "overview": "Priority 1: tighten evidence framing.",
            "items": [
                {
                    "section_title": "Introduction",
                    "action_type": "add",
                    "rid": "R2",
                    "priority": "high",
                    "action": "Add this reference to support the core claim.",
                    "why": "It improves background coverage.",
                    "where": "After the claim sentence.",
                    "anchor_quote": "The current evidence base is limited.",
                },
                {
                    "section_title": "Discussion",
                    "action_type": "reconsider",
                    "rid": "R3",
                    "priority": "high",
                    "action": "Reconsider this citation and justify relevance.",
                    "why": "Its link to the claim is weak.",
                    "where": "At the end of the paragraph.",
                    "anchor_quote": "This interpretation remains tentative.",
                },
            ],
        }
        subsection_recommendations = {
            "status": "completed",
            "items": [
                {
                    "title": "Introduction",
                    "plan_mode": "llm",
                    "plan": {
                        "summary": "Focus this section.",
                        "improvements": [
                            {
                                "priority": 1,
                                "action_type": "justify",
                                "action": "Explain why the current citation supports the claim.",
                                "why": "Readers need clear justification.",
                                "where": "After the opening claim.",
                                "anchor_quote": "The current evidence base is limited.",
                                "rids": ["R1"],
                            },
                            {
                                "priority": 1,
                                "action_type": "justify",
                                "action": "Explain why the current citation supports the claim.",
                                "why": "Readers need clear justification.",
                                "where": "After the opening claim.",
                                "anchor_quote": "The current evidence base is limited.",
                                "rids": ["R1"],
                            },
                        ],
                        "reference_integrations": [
                            {
                                "rid": "R4",
                                "priority": "medium",
                                "action_type": "add",
                                "action": "Integrate this supporting reference.",
                                "why": "Adds supporting evidence.",
                                "where": "Before the transition sentence.",
                                "anchor_quote": "The current evidence base is limited.",
                                "example": "This finding is supported by prior work [R4].",
                            }
                        ],
                        "questions": [],
                    },
                },
                {
                    "title": "Methods",
                    "plan_mode": "heuristic",
                    "plan": {
                        "summary": "Clarify methodological choices.",
                        "improvements": [
                            {
                                "priority": 1,
                                "action_type": "strengthen",
                                "action": "Clarify the rationale for model choice.",
                                "why": "Method rationale is currently implicit.",
                                "where": "After model description.",
                                "anchor_quote": "We fit the model to all available data.",
                                "rids": [],
                            },
                            {
                                "priority": 2,
                                "action_type": "strengthen",
                                "action": "Add one sentence on robustness checks.",
                                "why": "Improves reproducibility.",
                                "where": "At the end of the section.",
                                "anchor_quote": "We fit the model to all available data.",
                                "rids": [],
                            },
                            {
                                "priority": 3,
                                "action_type": "strengthen",
                                "action": "Define all abbreviations at first use.",
                                "why": "Improves readability.",
                                "where": "Where each abbreviation first appears.",
                                "anchor_quote": "We fit the model to all available data.",
                                "rids": [],
                            },
                            {
                                "priority": 4,
                                "action_type": "strengthen",
                                "action": "Move implementation detail to appendix.",
                                "why": "Improves flow.",
                                "where": "After results pointer.",
                                "anchor_quote": "We fit the model to all available data.",
                                "rids": [],
                            },
                        ],
                        "reference_integrations": [],
                        "questions": [],
                    },
                },
            ],
        }
        references_by_rid = {
            "R1": {"in_paper": True},
            "R2": {"in_paper": False},
            "R3": {"in_paper": True},
            "R4": {"in_paper": False},
        }

        out = build_recommendations(
            suggestions=suggestions,
            subsection_recommendations=subsection_recommendations,
            references_by_rid=references_by_rid,
            max_global_actions=5,
            max_actions_per_section=3,
        )

        self.assertEqual(out.get("status"), "completed")
        self.assertLessEqual(len(out.get("global_actions") or []), 5)
        for section in out.get("sections") or []:
            self.assertLessEqual(len(section.get("actions") or []), 3)

        intro_actions = []
        for section in out.get("sections") or []:
            if section.get("title") == "Introduction":
                intro_actions = section.get("actions") or []
                break
        self.assertTrue(intro_actions)
        self.assertEqual(
            len(
                [
                    action
                    for action in intro_actions
                    if action.get("action") == "Explain why the current citation supports the claim."
                ]
            ),
            1,
        )

    def test_returns_skipped_when_empty(self) -> None:
        out = build_recommendations(
            suggestions={"status": "skipped", "reason": "No suggestions"},
            subsection_recommendations={"status": "skipped", "reason": "No sections"},
            references_by_rid={},
        )
        self.assertEqual(out.get("status"), "skipped")


if __name__ == "__main__":
    unittest.main()

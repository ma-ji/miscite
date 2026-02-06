import unittest

from server.miscite.analysis.deep_analysis.recommendations import build_recommendations


def _action_signature(section_title: str, action: dict) -> tuple[str, str, tuple[str, ...], str, str]:
    return (
        section_title.strip().lower(),
        str(action.get("action_type") or "").strip().lower(),
        tuple(sorted(action.get("rids") or [])),
        str(action.get("action") or "").strip().lower(),
        str(action.get("anchor_quote") or "").strip().lower(),
    )


class TestRecommendations(unittest.TestCase):
    def test_merges_redundancies_and_hides_global_repeats(self) -> None:
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
                    "title": "**Introduction**",
                    "plan_mode": "llm",
                    "plan": {
                        "summary": "Focus this section.",
                        "improvements": [
                            {
                                "priority": 1,
                                "action_type": "justify",
                                "action": "Support the gap claim with current Chinese evidence.",
                                "why": "Readers need clear justification.",
                                "where": "After the opening claim.",
                                "anchor_quote": "The current evidence base is limited.",
                                "rids": ["R1"],
                            },
                            {
                                "priority": 2,
                                "action_type": "justify",
                                "action": "Support this gap claim with contemporary Chinese evidence.",
                                "why": "The central claim needs stronger justification.",
                                "where": "After the opening claim.",
                                "anchor_quote": "The current evidence base is limited.",
                                "rids": ["R1"],
                            },
                        ],
                        "reference_integrations": [
                            {
                                "rid": "R2",
                                "priority": "medium",
                                "action_type": "add",
                                "action": "Integrate this supporting reference.",
                                "why": "Adds supporting evidence.",
                                "where": "Before the transition sentence.",
                                "anchor_quote": "The current evidence base is limited.",
                            }
                        ],
                        "questions": [],
                    },
                },
                {
                    "title": "Introduction",
                    "plan_mode": "heuristic",
                    "plan": {
                        "summary": "Clarify context.",
                        "improvements": [
                            {
                                "priority": 4,
                                "action_type": "strengthen",
                                "action": "Clarify the contextual scope in one sentence.",
                                "why": "Improves readability.",
                                "where": "At the end of the paragraph.",
                                "anchor_quote": "External context influences outcomes.",
                                "rids": [],
                            }
                        ],
                        "reference_integrations": [],
                        "questions": [],
                    },
                },
                {
                    "title": "Methods",
                    "plan_mode": "heuristic",
                    "plan": {
                        "summary": "Clarify methods.",
                        "improvements": [
                            {
                                "priority": 1,
                                "action_type": "strengthen",
                                "action": "Clarify the rationale for model choice.",
                                "why": "Method rationale is currently implicit.",
                                "where": "After model description.",
                                "anchor_quote": "We fit the model to all available data.",
                                "rids": [],
                            }
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
        }

        out = build_recommendations(
            suggestions=suggestions,
            subsection_recommendations=subsection_recommendations,
            references_by_rid=references_by_rid,
            max_global_actions=2,
            max_actions_per_section=3,
        )

        self.assertEqual(out.get("status"), "completed")
        self.assertLessEqual(len(out.get("global_actions") or []), 2)

        # No markdown artifacts should remain in section titles.
        for action in out.get("global_actions") or []:
            self.assertNotIn("*", str(action.get("section_title") or ""))
        for section in out.get("sections") or []:
            self.assertNotIn("*", str(section.get("title") or ""))

        # Top priorities should not be duplicated under By section.
        global_sigs = {
            _action_signature(str(action.get("section_title") or ""), action)
            for action in out.get("global_actions") or []
        }
        section_sigs = set()
        for section in out.get("sections") or []:
            self.assertLessEqual(len(section.get("actions") or []), 3)
            title = str(section.get("title") or "")
            for action in section.get("actions") or []:
                section_sigs.add(_action_signature(title, action))
        self.assertTrue(section_sigs)
        self.assertFalse(global_sigs & section_sigs)

        # Paraphrased duplicate justify-actions for the same claim should merge.
        intro_r1_actions = []
        for action in out.get("global_actions") or []:
            if str(action.get("section_title") or "") == "Introduction" and "R1" in (action.get("rids") or []):
                intro_r1_actions.append(action)
        for section in out.get("sections") or []:
            if str(section.get("title") or "") != "Introduction":
                continue
            for action in section.get("actions") or []:
                if "R1" in (action.get("rids") or []):
                    intro_r1_actions.append(action)
        self.assertEqual(len(intro_r1_actions), 1)

    def test_prefers_reconsider_when_merging_same_claim(self) -> None:
        subsection_recommendations = {
            "status": "completed",
            "items": [
                {
                    "title": "Discussion",
                    "plan_mode": "llm",
                    "plan": {
                        "summary": "Tighten claim quality.",
                        "improvements": [
                            {
                                "priority": 2,
                                "action_type": "add",
                                "action": "Justify this claim with stronger evidence.",
                                "why": "The argument is currently undersupported.",
                                "where": "After the claim sentence.",
                                "anchor_quote": "The evidence remains uncertain.",
                                "rids": ["R9"],
                            },
                            {
                                "priority": 1,
                                "action_type": "reconsider",
                                "action": "Justify this claim with stronger evidence.",
                                "why": "The citation may not fit the claim.",
                                "where": "After the claim sentence.",
                                "anchor_quote": "The evidence remains uncertain.",
                                "rids": ["R9"],
                            },
                        ],
                        "reference_integrations": [],
                        "questions": [],
                    },
                }
            ],
        }

        out = build_recommendations(
            suggestions={"status": "skipped", "reason": "No suggestions"},
            subsection_recommendations=subsection_recommendations,
            references_by_rid={"R9": {"in_paper": True}},
            max_global_actions=5,
            max_actions_per_section=3,
        )

        self.assertEqual(out.get("status"), "completed")
        global_actions = out.get("global_actions") or []
        self.assertEqual(len(global_actions), 1)
        self.assertEqual(global_actions[0].get("action_type"), "reconsider")

    def test_drops_opening_section_actions(self) -> None:
        subsection_recommendations = {
            "status": "completed",
            "items": [
                {
                    "title": "opening",
                    "plan_mode": "llm",
                    "plan": {
                        "summary": "Placeholder opening section.",
                        "improvements": [
                            {
                                "priority": 1,
                                "action_type": "strengthen",
                                "action": "Replace title-only placeholder with real introduction text.",
                                "why": "The opening placeholder is not actionable for revision.",
                                "where": "At manuscript start.",
                                "anchor_quote": "Title only.",
                                "rids": [],
                            }
                        ],
                        "reference_integrations": [],
                        "questions": [],
                    },
                },
                {
                    "title": "Introduction",
                    "plan_mode": "llm",
                    "plan": {
                        "summary": "Real section.",
                        "improvements": [
                            {
                                "priority": 1,
                                "action_type": "justify",
                                "action": "Clarify the introduction claim with direct evidence.",
                                "why": "The claim is currently under-supported.",
                                "where": "After the first claim sentence.",
                                "anchor_quote": "Current evidence is limited.",
                                "rids": ["R1"],
                            }
                        ],
                        "reference_integrations": [],
                        "questions": [],
                    },
                },
            ],
        }
        out = build_recommendations(
            suggestions={"status": "skipped", "reason": "No suggestions"},
            subsection_recommendations=subsection_recommendations,
            references_by_rid={"R1": {"in_paper": True}},
            max_global_actions=5,
            max_actions_per_section=3,
        )

        self.assertEqual(out.get("status"), "completed")
        all_section_titles = {
            str(action.get("section_title") or "").strip().lower()
            for action in out.get("global_actions") or []
        }
        all_section_titles.update(
            str(section.get("title") or "").strip().lower()
            for section in out.get("sections") or []
        )
        self.assertNotIn("opening", all_section_titles)
        self.assertIn("introduction", all_section_titles)

    def test_returns_skipped_when_empty(self) -> None:
        out = build_recommendations(
            suggestions={"status": "skipped", "reason": "No suggestions"},
            subsection_recommendations={"status": "skipped", "reason": "No sections"},
            references_by_rid={},
        )
        self.assertEqual(out.get("status"), "skipped")


if __name__ == "__main__":
    unittest.main()

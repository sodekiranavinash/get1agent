"""Unit tests for the pre-run planner's JSON parsing and prompt folding."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import planner  # noqa: E402


class ExtractJsonTests(unittest.TestCase):
    def test_plain_json(self) -> None:
        raw = '{"understanding": "x", "subQueries": []}'
        self.assertEqual(planner._extract_json(raw)["understanding"], "x")

    def test_fenced_json(self) -> None:
        raw = 'Here you go:\n```json\n{"subQueries": [{"query": "a"}]}\n```\n'
        parsed = planner._extract_json(raw)
        self.assertEqual(parsed["subQueries"][0]["query"], "a")

    def test_json_embedded_in_prose(self) -> None:
        raw = 'Sure. {"subQueries": [{"query": "a"}]} done.'
        self.assertIsNotNone(planner._extract_json(raw))

    def test_garbage_returns_none(self) -> None:
        self.assertIsNone(planner._extract_json("not json at all"))


class CleanPlanTests(unittest.TestCase):
    def test_nested_sub_queries(self) -> None:
        raw = {
            "understanding": "do a thing",
            "subQueries": [
                {
                    "query": "first angle",
                    "todos": [{"title": "search", "tool": "knowledge_search", "query": "x"}],
                },
                {
                    "query": "second angle",
                    "todos": [{"title": "browse", "tool": "web-search"}],
                },
            ],
        }
        plan = planner._clean_plan(raw)
        self.assertEqual(len(plan["subQueries"]), 2)
        first = plan["subQueries"][0]
        self.assertEqual(first["query"], "first angle")
        self.assertEqual(first["todos"][0]["tool"], "knowledge_search")
        self.assertEqual(plan["subQueries"][1]["todos"][0]["tool"], "web-search")

    def test_tool_less_todos_are_dropped(self) -> None:
        plan = planner._clean_plan(
            {
                "subQueries": [
                    {"query": "reasoning only", "todos": [{"title": "think"}]},
                    {
                        "query": "search",
                        "todos": [{"title": "search", "tool": "web-search"}],
                    },
                ]
            }
        )
        self.assertEqual(len(plan["subQueries"]), 1)
        self.assertEqual(plan["subQueries"][0]["todos"][0]["tool"], "web-search")

    def test_flat_todos_become_one_sub_query(self) -> None:
        plan = planner._clean_plan(
            {
                "understanding": "legacy",
                "todos": [
                    {"title": "a", "tool": "web-search"},
                    {"title": "b", "tool": "web-search"},
                ],
            }
        )
        self.assertEqual(len(plan["subQueries"]), 1)
        self.assertEqual(plan["subQueries"][0]["query"], "legacy")
        self.assertEqual(len(plan["subQueries"][0]["todos"]), 2)

    def test_missing_plan_returns_none(self) -> None:
        self.assertIsNone(planner._clean_plan({"understanding": "x"}))
        self.assertIsNone(planner._clean_plan(None))

    def test_sub_query_with_only_a_skill_becomes_a_skills_step(self) -> None:
        raw = {
            "subQueries": [
                {
                    "query": "compose",
                    "todos": [{"title": "Compose the email", "tool": "email-composer"}],
                }
            ]
        }
        plan = planner._clean_plan(raw, frozenset({"email-composer"}))
        self.assertEqual(plan["subQueries"][0]["todos"][0]["tool"], "skills")

    def test_skill_names_load_via_the_skills_tool(self) -> None:
        raw = {
            "subQueries": [
                {
                    "query": "compose",
                    "todos": [
                        {"title": "Compose the email", "tool": "email-composer"},
                        {"title": "Look it up", "tool": "email-composer, web-search"},
                    ],
                }
            ]
        }
        plan = planner._clean_plan(raw, frozenset({"email-composer"}))
        todos = plan["subQueries"][0]["todos"]
        # A skill is loaded through the `skills` tool, with the skill in `query`.
        self.assertEqual(todos[0]["tool"], "skills")
        self.assertEqual(todos[0]["query"], "email-composer")
        # A mixed step keeps the real tool and prepends the skills loader.
        self.assertEqual(todos[1]["tool"], "skills, web-search")

    def test_skills_tool_survives_the_known_tools_filter(self) -> None:
        raw = {
            "subQueries": [
                {
                    "query": "q",
                    "todos": [{"title": "load", "tool": "skills", "query": "pdf-extract"}],
                }
            ]
        }
        plan = planner._clean_plan(raw, frozenset(), frozenset({"skills", "web-search"}))
        self.assertEqual(plan["subQueries"][0]["todos"][0]["tool"], "skills")

    def test_unknown_tools_are_dropped(self) -> None:
        raw = {
            "subQueries": [
                {
                    "query": "look it up",
                    "todos": [
                        {"title": "Web search", "tool": "global_search"},
                        {"title": "Search KB", "tool": "search-user-knowledge-bases"},
                        {"title": "Mixed", "tool": "global_search, web-search"},
                    ],
                }
            ]
        }
        plan = planner._clean_plan(
            raw,
            frozenset(),
            frozenset({"search-user-knowledge-bases", "web-search"}),
        )
        todos = plan["subQueries"][0]["todos"]
        # The invented `global_search` never survives.
        self.assertEqual(
            [todo["tool"] for todo in todos],
            ["search-user-knowledge-bases", "web-search"],
        )

    def test_plan_of_only_unknown_tools_is_dropped(self) -> None:
        raw = {
            "subQueries": [
                {"query": "x", "todos": [{"title": "a", "tool": "global_search"}]}
            ]
        }
        self.assertIsNone(
            planner._clean_plan(raw, frozenset(), frozenset({"web-search"}))
        )

    def test_tool_name_forms_still_match(self) -> None:
        raw = {
            "subQueries": [
                {
                    "query": "x",
                    "todos": [
                        {"title": "a", "tool": "`web-search`"},
                        {"title": "b", "tool": "myserver/tool"},
                    ],
                }
            ]
        }
        plan = planner._clean_plan(
            raw, frozenset(), frozenset({"web-search", "myserver-tool"})
        )
        todos = plan["subQueries"][0]["todos"]
        self.assertEqual([todo["tool"] for todo in todos], ["web-search", "myserver/tool"])


class EnsureKnowledgePlanTests(unittest.TestCase):
    """The runtime forces a KB-first step so it can't be skipped by the model."""

    def test_prepends_a_kb_step_when_missing(self) -> None:
        plan = {
            "understanding": "u",
            "subQueries": [
                {
                    "id": "1",
                    "query": "q",
                    "todos": [{"id": "1", "title": "web", "tool": "web-search"}],
                }
            ],
        }
        result = planner.ensure_knowledge_plan(plan, ["my-resume"])
        first = result["subQueries"][0]
        self.assertEqual(first["todos"][0]["tool"], "search-user-knowledge-bases")
        # The planner's own step is preserved after the KB step.
        self.assertEqual(result["subQueries"][1]["todos"][0]["tool"], "web-search")

    def test_leaves_a_plan_that_already_uses_the_kb(self) -> None:
        plan = {
            "understanding": "u",
            "subQueries": [
                {
                    "query": "q",
                    "todos": [{"title": "kb", "tool": "search-user-knowledge-bases"}],
                }
            ],
        }
        self.assertIs(planner.ensure_knowledge_plan(plan, ["my-resume"]), plan)

    def test_builds_a_kb_plan_when_there_is_none(self) -> None:
        result = planner.ensure_knowledge_plan(None, ["my-resume"])
        self.assertEqual(
            result["subQueries"][0]["todos"][0]["tool"],
            "search-user-knowledge-bases",
        )

    def test_noop_without_knowledge_bases(self) -> None:
        self.assertIsNone(planner.ensure_knowledge_plan(None, []))


class ExecutionInputTests(unittest.TestCase):
    def test_folds_steps_with_sub_query_headings(self) -> None:
        plan = {
            "subQueries": [
                {
                    "query": "budget",
                    "todos": [
                        {"title": "Search", "tool": "knowledge_search", "query": "budget"},
                        {"title": "Summarise"},
                    ],
                }
            ]
        }
        text = planner.execution_input("What is the budget?", plan)
        self.assertIn("What is the budget?", text)
        self.assertIn("Sub-query: budget", text)
        self.assertIn("1. Search", text)
        self.assertIn("`knowledge_search`", text)
        self.assertIn('"budget"', text)
        self.assertIn("2. Summarise", text)

    def test_empty_plan_passthrough(self) -> None:
        self.assertEqual(planner.execution_input("hello", {"subQueries": []}), "hello")

    def test_skill_step_is_phrased_as_a_load(self) -> None:
        plan = {
            "subQueries": [
                {
                    "query": "q",
                    "todos": [
                        {"title": "Load skill", "tool": "skills", "query": "pdf-extract"}
                    ],
                }
            ]
        }
        text = planner.execution_input("hello", plan)
        self.assertIn('load the "pdf-extract" skill with the `skills` tool', text)

    def test_steps_are_sequential(self) -> None:
        plan = {"subQueries": [{"query": "q", "todos": [{"title": "a"}]}]}
        text = planner.execution_input("hello", plan)
        self.assertIn("strictly in sequential order", text)
        self.assertIn("one at a time", text)

    def test_answer_must_be_grounded_in_tool_results(self) -> None:
        plan = {
            "subQueries": [
                {"query": "q", "todos": [{"title": "a", "tool": "web-search"}]}
            ]
        }
        text = planner.execution_input("hello", plan)
        self.assertIn("using ONLY the results of these tool calls", text)


if __name__ == "__main__":
    unittest.main()

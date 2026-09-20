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

    def test_steps_are_sequential(self) -> None:
        plan = {"subQueries": [{"query": "q", "todos": [{"title": "a"}]}]}
        text = planner.execution_input("hello", plan)
        self.assertIn("strictly in sequential order", text)
        self.assertIn("one at a time", text)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for MCP tool wrapping (schema passthrough + result flattening)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "packages"))

from agentflow import tools  # noqa: E402

try:  # Strands is only installed in the container / smoke env.
    import strands  # noqa: F401

    HAVE_STRANDS = True
except Exception:  # noqa: BLE001
    HAVE_STRANDS = False


class TextOfTests(unittest.TestCase):
    def test_flattens_content_blocks(self) -> None:
        response = {
            "result": {
                "content": [
                    {"type": "text", "text": "a"},
                    {"type": "text", "text": "b"},
                ]
            }
        }
        self.assertEqual(tools._text_of(response), "a\nb")

    def test_empty_result(self) -> None:
        self.assertEqual(tools._text_of({}), "")


class SlugTests(unittest.TestCase):
    def test_slugifies(self) -> None:
        self.assertEqual(tools._slug("My Server!", "x"), "my-server")

    def test_fallback(self) -> None:
        self.assertEqual(tools._slug("", "server-0"), "server-0")


class NumberSourcesTests(unittest.TestCase):
    def test_numbers_sources_and_results_globally(self) -> None:
        counter = {"n": 0}
        first = tools._number_sources(
            json.dumps({"results": [{"url": "a"}, {"url": "b"}]}), counter
        )
        second = tools._number_sources(json.dumps({"sources": [{"fileName": "x"}]}), counter)
        self.assertEqual([item["index"] for item in json.loads(first)["results"]], [1, 2])
        self.assertEqual(json.loads(second)["sources"][0]["index"], 3)

    def test_non_json_is_unchanged(self) -> None:
        self.assertEqual(tools._number_sources("not json", {"n": 0}), "not json")

    def test_propagates_index_to_chunks(self) -> None:
        payload = {
            "sources": [{"documentId": "d1", "page": 2}],
            "chunks": [{"documentId": "d1", "page": 2, "content": "x"}],
        }
        result = json.loads(tools._number_sources(json.dumps(payload), {"n": 0}))
        self.assertEqual(result["sources"][0]["index"], 1)
        self.assertEqual(result["chunks"][0]["index"], 1)


class KnowledgeCallerTests(unittest.TestCase):
    def test_injects_attached_knowledge_bases(self) -> None:
        from unittest import mock

        captured: dict = {}

        def fake_call(function, user_id, tool_name, arguments):
            captured.update(function=function, tool_name=tool_name, arguments=arguments)
            return None, {"result": {"content": [{"text": "ok"}]}}

        with mock.patch.object(tools.mcp_client, "call_tool", fake_call):
            caller = tools._knowledge_caller(
                "kb-fn", "u1", "search-user-knowledge-bases", ["my-kb"], True, {"n": 0}
            )
            result = caller({"query": "x", "knowledgeBaseNames": ["other"]})

        self.assertEqual(result, "ok")
        self.assertEqual(captured["tool_name"], "search-user-knowledge-bases")
        self.assertEqual(captured["arguments"]["knowledgeBaseNames"], ["my-kb"])
        self.assertEqual(captured["arguments"]["query"], "x")
        self.assertTrue(captured["arguments"]["rerank"])


@unittest.skipUnless(HAVE_STRANDS, "strands not installed")
class MakeToolTests(unittest.TestCase):
    def test_input_schema_is_passed_through(self) -> None:
        schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        tool = tools._make_tool("web-search", "Search.", lambda args: "ok", schema)
        self.assertEqual(tool.tool_name, "web-search")
        self.assertEqual(tool.tool_spec["inputSchema"], schema)

    def test_missing_schema_defaults_to_empty_object(self) -> None:
        tool = tools._make_tool("remote/some", "d", lambda args: "ok", None)
        self.assertEqual(tool.tool_spec["inputSchema"], {"type": "object", "properties": {}})

    def test_arguments_are_forwarded_verbatim(self) -> None:
        import asyncio

        captured: dict = {}

        def fn(arguments: dict) -> str:
            captured.update(arguments)
            return "ok"

        tool = tools._make_tool(
            "web-search",
            "Search.",
            fn,
            {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        )

        async def run() -> None:
            tool_use = {"toolUseId": "1", "name": "web_search", "input": {"query": "hi"}}
            async for _ in tool.stream(tool_use, {}):
                pass

        asyncio.run(run())
        self.assertEqual(captured, {"query": "hi"})


if __name__ == "__main__":
    unittest.main()

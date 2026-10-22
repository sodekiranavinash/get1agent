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

    def test_jsonrpc_error_becomes_readable_text(self) -> None:
        """A failed call must never look like "the tool returned nothing"."""
        response = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32600, "message": "Invalid Request"}}
        self.assertEqual(tools._text_of(response), "MCP error -32600: Invalid Request")

    def test_error_without_a_message_still_surfaces(self) -> None:
        self.assertIn("-32601", tools._text_of({"error": {"code": -32601}}))


class SlugTests(unittest.TestCase):
    def test_slugifies(self) -> None:
        self.assertEqual(tools._slug("My Server!", "x"), "my-server")

    def test_fallback(self) -> None:
        self.assertEqual(tools._slug("", "server-0"), "server-0")


class RegisteredToolNamesTests(unittest.TestCase):
    """The planner's tool list must come from the agent, not the MCP list.

    The memory manager registers its own tools on the agent (plugin registry), so
    reading only the MCP ``tools`` list hid ``add_memory`` from the planner — and
    "remember this" was routed to the only persistence tool it could see, a
    storage file.
    """

    class _Registry:
        def __init__(self, specs: object) -> None:
            self._specs = specs

        def get_all_tool_specs(self) -> object:
            return self._specs

    @staticmethod
    def _agent(specs: object):
        from types import SimpleNamespace

        return SimpleNamespace(tool_registry=RegisteredToolNamesTests._Registry(specs))

    def test_reads_every_registered_tool(self) -> None:
        agent = self._agent(
            [
                {"name": "search-user-knowledge-bases"},
                {"name": "search_memory"},
                {"name": "add_memory"},
            ]
        )
        self.assertEqual(
            tools.registered_tool_names(agent),
            ["search-user-knowledge-bases", "search_memory", "add_memory"],
        )

    def test_plugin_registered_memory_tools_are_visible(self) -> None:
        self.assertIn("add_memory", tools.registered_tool_names(self._agent([{"name": "add_memory"}])))

    def test_agent_without_a_registry_is_empty(self) -> None:
        self.assertEqual(tools.registered_tool_names(object()), [])

    def test_unreadable_registry_never_raises(self) -> None:
        from types import SimpleNamespace

        class _Boom:
            @staticmethod
            def get_all_tool_specs() -> object:
                raise RuntimeError("registry down")

        self.assertEqual(
            tools.registered_tool_names(SimpleNamespace(tool_registry=_Boom())), []
        )

    def test_unnamed_and_malformed_specs_are_skipped(self) -> None:
        agent = self._agent([{"name": "ok"}, {}, {"name": ""}, "junk", {"name": "two"}])
        self.assertEqual(tools.registered_tool_names(agent), ["ok", "two"])


class LambdaTransportTests(unittest.TestCase):
    """Lambda-backed MCP servers are always reached by direct invoke.

    The AgentCore Gateway cannot serve them: a Lambda target is invoked with the
    tool's *arguments* as its event (the tool name rides in the Lambda client
    context), the gateway only exposes the tools written into the target's inline
    schema, and it carries no caller identity. Routing knowledge/custom tools
    through it returned nothing at all in production.
    """

    def test_mcp_caller_invokes_the_lambda_directly(self) -> None:
        from unittest import mock

        response = {"result": {"content": [{"text": "ok"}]}}
        with mock.patch.object(tools.mcp_client, "gateway_call_tool") as gateway, \
                mock.patch.object(
                    tools.mcp_client, "call_tool", return_value=(None, response)
                ) as direct:
            caller = tools._mcp_caller("storage-fn", "u1", "list-storage-files", {"n": 0})
            self.assertEqual(caller({"maxItems": 5}), "ok")

        gateway.assert_not_called()
        direct.assert_called_once_with(
            "storage-fn", "u1", "list-storage-files", {"maxItems": 5}
        )

    def test_knowledge_caller_invokes_the_lambda_directly(self) -> None:
        from unittest import mock

        response = {"result": {"content": [{"text": "ok"}]}}
        with mock.patch.object(tools.mcp_client, "gateway_call_tool") as gateway, \
                mock.patch.object(
                    tools.mcp_client, "call_tool", return_value=(None, response)
                ) as direct:
            caller = tools._knowledge_caller(
                "kb-fn", "u1", "search-user-knowledge-bases", ["my-kb"], True, {"n": 0}
            )
            self.assertEqual(caller({"query": "x"}), "ok")

        gateway.assert_not_called()
        self.assertEqual(direct.call_args[0][3]["knowledgeBaseNames"], ["my-kb"])

    def test_transport_failure_is_reported_not_swallowed(self) -> None:
        from unittest import mock

        with mock.patch.object(
            tools.mcp_client, "call_tool", side_effect=tools.mcp_client.McpClientError("boom")
        ):
            caller = tools._mcp_caller("storage-fn", "u1", "list-storage-files", {"n": 0})
            self.assertIn("boom", caller({}))


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

    def test_graph_is_omitted_unless_forced(self) -> None:
        """An agent that never opted in must not downgrade a Graph KB.

        Retrieval is the knowledge base's own mode; sending ``graph: false``
        would silently turn every graph search into plain hybrid.
        """
        from unittest import mock

        calls: list[dict] = []

        def fake_call(function, user_id, tool_name, arguments):
            calls.append(arguments)
            return None, {"result": {"content": [{"text": "ok"}]}}

        with mock.patch.object(tools.mcp_client, "call_tool", fake_call):
            tools._knowledge_caller(
                "kb-fn", "u1", "search-user-knowledge-bases", ["my-kb"], False, {"n": 0}
            )({"query": "x"})
            self.assertNotIn("graph", calls[-1])

            tools._knowledge_caller(
                "kb-fn", "u1", "search-user-knowledge-bases", ["my-kb"], False, {"n": 0},
                graph=True,
            )({"query": "x"})
            self.assertTrue(calls[-1]["graph"])


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


@unittest.skipUnless(HAVE_STRANDS, "strands not installed")
class WebSearchAvailabilityTests(unittest.TestCase):
    """Web search is a gateway-only connector (no local fallback)."""

    @staticmethod
    def _config(gateway: str = ""):
        from types import SimpleNamespace

        return SimpleNamespace(
            mcp_transport="gateway" if gateway else "aggregator",
            gateway_url=gateway,
            web_search_gateway_url=gateway,
            web_search_gateway_tool="web-search___WebSearch",
            web_search_gateway_region="us-west-2",
            knowledge_function="",
            code_interpreter_function="",
            http_fetch_function="",
            storage_function="",
            browser_function="",
            custom_tools_function="",
            remote_function="",
        )

    def test_no_web_tool_without_a_gateway(self) -> None:
        agent = {"servers": [{"source": "builtin", "id": "web-search"}]}
        self.assertEqual(tools.build_tools(self._config(""), "u1", agent, []), [])

    def test_web_tool_with_a_gateway(self) -> None:
        agent = {"servers": [{"source": "builtin", "id": "web-search"}]}
        names = [
            tool.tool_name
            for tool in tools.build_tools(self._config("https://gw.example/mcp"), "u1", agent, [])
        ]
        self.assertEqual(names, ["web-search"])


@unittest.skipUnless(HAVE_STRANDS, "strands not installed")
class GatewayTransportRoutingTests(unittest.TestCase):
    """`MCP_TRANSPORT=gateway` (the deployed setting) reaches Lambda servers directly."""

    @staticmethod
    def _config():
        from types import SimpleNamespace

        return SimpleNamespace(
            mcp_transport="gateway",
            gateway_url="https://gw.example/mcp",
            web_search_gateway_url="https://web.example/mcp",
            web_search_gateway_tool="web-search___WebSearch",
            web_search_gateway_region="us-west-2",
            knowledge_function="",
            code_interpreter_function="",
            http_fetch_function="",
            storage_function="storage-fn",
            browser_function="",
            custom_tools_function="",
            remote_function="",
        )

    def test_builtin_server_still_direct_invokes(self) -> None:
        import asyncio
        from unittest import mock

        specs = [
            {
                "name": "list-storage-files",
                "description": "List files.",
                "inputSchema": {"type": "object", "properties": {}},
            }
        ]
        response = {"result": {"content": [{"text": "3 files"}]}}
        spec_response = {"result": {"tools": specs}}
        agent = {"servers": [{"source": "builtin", "id": "storage"}]}
        with mock.patch.object(tools.mcp_client, "list_tools", return_value=(None, spec_response)), \
                mock.patch.object(tools.mcp_client, "gateway_call_tool") as gateway, \
                mock.patch.object(
                    tools.mcp_client, "call_tool", return_value=(None, response)
                ) as direct:
            built = tools.build_tools(self._config(), "u1", agent, [])
            self.assertEqual([tool.tool_name for tool in built], ["list-storage-files"])

            async def run() -> None:
                tool_use = {"toolUseId": "1", "name": "list-storage-files", "input": {}}
                async for _ in built[0].stream(tool_use, {}):
                    pass

            asyncio.run(run())

        gateway.assert_not_called()
        direct.assert_called_once_with("storage-fn", "u1", "list-storage-files", {})


if __name__ == "__main__":
    unittest.main()

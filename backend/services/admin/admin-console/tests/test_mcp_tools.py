"""Unit tests for the admin console's MCP client (direct-invoke transport).

The admin console lists and calls the MCP servers over the direct-invoke Lambda
transport only. The AgentCore Gateway cannot serve these servers: a Lambda
target is invoked with the tool's arguments as its event, exposes only the tools
written into the target's inline schema, and carries no caller identity — so
routing through it listed phantom tools and returned no data.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

import handler


def _body(response: dict) -> dict:
    return json.loads(response["body"])


class TransportTests(unittest.TestCase):
    def test_the_gateway_branch_is_gone(self) -> None:
        self.assertFalse(hasattr(handler, "gateway_list_tools"))
        self.assertFalse(hasattr(handler, "gateway_call_tool"))
        self.assertFalse(hasattr(handler, "_mcp_transport"))


class ListToolsTests(unittest.TestCase):
    def test_lists_every_server_directly(self) -> None:
        tools = [{"name": "search-user-knowledge-bases", "server": "knowledge-mcp"}]
        servers = [{"function": "knowledge-mcp", "ok": True, "toolCount": 1}]
        with mock.patch.object(
            handler, "list_tools_multi", return_value=(tools, servers)
        ) as list_multi:
            response = handler._handle_list_tools(["knowledge-mcp"], "u1", "us-east-1")

        list_multi.assert_called_once_with(["knowledge-mcp"], "u1", "us-east-1")
        self.assertEqual(response["statusCode"], 200)
        body = _body(response)
        self.assertTrue(body["ok"])
        self.assertEqual(body["tools"], tools)
        self.assertEqual(body["servers"], servers)


class CallToolTests(unittest.TestCase):
    def test_routes_the_call_to_the_owning_server(self) -> None:
        params = {"name": "search-user-knowledge-bases", "arguments": {"query": "x"}}
        response = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"content": [{"type": "text", "text": "ok"}]},
        }
        with mock.patch.object(
            handler, "find_tool_server", return_value="knowledge-mcp"
        ) as finder, mock.patch.object(
            handler, "call_tool", return_value=(params, response)
        ) as call:
            result = handler._handle_call_tool(
                ["knowledge-mcp"], "u1", "us-east-1", params
            )

        finder.assert_called_once_with(
            ["knowledge-mcp"], "u1", "search-user-knowledge-bases", "us-east-1"
        )
        call.assert_called_once_with(
            "knowledge-mcp", "u1", "search-user-knowledge-bases", {"query": "x"}, "us-east-1"
        )
        body = _body(result)
        self.assertTrue(body["ok"])
        self.assertEqual(body["server"], "knowledge-mcp")
        self.assertEqual(body["result"], response["result"])

    def test_unknown_tool_is_reported(self) -> None:
        with mock.patch.object(handler, "find_tool_server", return_value=None):
            result = handler._handle_call_tool(["mcp-fn"], "u1", None, {"name": "nope"})

        body = _body(result)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["code"], -32601)
        self.assertIn("not found", body["error"]["message"])

    def test_mcp_error_is_returned_not_silently_empty(self) -> None:
        error = {"jsonrpc": "2.0", "id": 1, "error": {"code": -32603, "message": "boom"}}
        with mock.patch.object(handler, "find_tool_server", return_value="mcp-fn"), \
                mock.patch.object(handler, "call_tool", return_value=(None, error)):
            result = handler._handle_call_tool(["mcp-fn"], "u1", None, {"name": "a-tool"})

        body = _body(result)
        self.assertFalse(body["ok"])
        self.assertEqual(body["error"]["message"], "boom")

    def test_name_and_arguments_are_validated(self) -> None:
        self.assertEqual(handler._handle_call_tool(["mcp-fn"], "u1", None, {})["statusCode"], 400)
        bad = handler._handle_call_tool(["mcp-fn"], "u1", None, {"name": "x", "arguments": 3})
        self.assertEqual(bad["statusCode"], 400)


if __name__ == "__main__":
    unittest.main()

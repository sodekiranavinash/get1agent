"""Unit tests for the AgentCore Gateway transport (MCP over SigV4 HTTP)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "packages"))

from core import mcp_client  # noqa: E402


class _Response:
    def __init__(self, status_code: int, content: bytes) -> None:
        self.status_code = status_code
        self.content = content


class ParseBodyTests(unittest.TestCase):
    def test_plain_json(self) -> None:
        body = b'{"jsonrpc":"2.0","id":2,"result":{"content":[{"text":"ok"}]}}'
        parsed = mcp_client._parse_mcp_body(body)
        self.assertEqual(parsed["result"]["content"][0]["text"], "ok")

    def test_sse_takes_last_frame(self) -> None:
        body = (
            b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"a":1}}\n\n'
            b'event: message\ndata: {"jsonrpc":"2.0","id":2,"result":{"b":2}}\n\n'
        )
        parsed = mcp_client._parse_mcp_body(body)
        self.assertEqual(parsed["result"], {"b": 2})

    def test_sse_ignores_non_json_and_done(self) -> None:
        body = b'data: [DONE]\ndata: not-json\ndata: {"jsonrpc":"2.0","result":{}}\n'
        self.assertEqual(mcp_client._parse_mcp_body(body)["result"], {})

    def test_empty_body(self) -> None:
        self.assertEqual(mcp_client._parse_mcp_body(b""), {})

    def test_invalid_json_raises(self) -> None:
        with self.assertRaises(mcp_client.McpClientError):
            mcp_client._parse_mcp_body(b"{not json")

    def test_no_payload_raises(self) -> None:
        with self.assertRaises(mcp_client.McpClientError):
            mcp_client._parse_mcp_body(b"event: ping\n")


class GatewayCallTests(unittest.TestCase):
    def test_sigv4_signed_and_parsed(self) -> None:
        captured: dict = {}

        class _Session:
            def send(self, request):
                captured["url"] = request.url
                captured["headers"] = dict(request.headers)
                captured["body"] = request.body
                return _Response(200, b'{"jsonrpc":"2.0","id":2,"result":{"ok":true}}')

        creds = mock.Mock()
        creds.access_key = "AKIA"
        creds.secret_key = "secret"
        creds.token = None
        creds.get_frozen_credentials.return_value = creds

        with mock.patch("boto3.Session") as session:
            session.return_value.get_credentials.return_value = creds
            with mock.patch("botocore.httpsession.URLLib3Session", return_value=_Session()):
                result = mcp_client.gateway_call_tool(
                    "https://gw.example/mcp", "sess-1", "web-search", {"query": "x"}
                )

        self.assertEqual(result["result"], {"ok": True})
        self.assertEqual(captured["url"], "https://gw.example/mcp")
        self.assertIn("Authorization", captured["headers"])
        self.assertEqual(captured["headers"].get("mcp-session-id"), "sess-1")
        sent = json.loads(captured["body"])
        self.assertEqual(sent["params"]["name"], "web-search")

    def test_http_error_raises(self) -> None:
        class _Session:
            def send(self, _request):
                return _Response(403, b"denied")

        creds = mock.Mock(
            access_key="AKIA",
            secret_key="secret",
            token=None,
            method="GET",
        )
        creds.get_frozen_credentials.return_value = creds
        with mock.patch("boto3.Session") as session:
            session.return_value.get_credentials.return_value = creds
            with mock.patch("botocore.httpsession.URLLib3Session", return_value=_Session()):
                with self.assertRaises(mcp_client.McpClientError):
                    mcp_client.gateway_call_tool(
                        "https://gw.example/mcp", "", "web-search", {}
                    )


if __name__ == "__main__":
    unittest.main()

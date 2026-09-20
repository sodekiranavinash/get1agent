"""Unit tests for the Streamable HTTP MCP client.

Run with: ``make -C backend/services/mcp-connections test``
"""

from __future__ import annotations

import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
BACKEND = APP.parents[1]
sys.path.insert(0, str(BACKEND / "packages"))

from core import mcp_http  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_plain_json(self) -> None:
        messages = mcp_http.parse_messages(
            "application/json", b'{"jsonrpc":"2.0","id":1,"result":{}}'
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["id"], 1)

    def test_sse_stream(self) -> None:
        body = (
            b"event: message\n"
            b"data: {\"jsonrpc\":\"2.0\",\"method\":\"notifications/progress\"}\n\n"
            b"data: {\"jsonrpc\":\"2.0\",\"id\":1,\"result\":{\"tools\":[]}}\n\n"
        )
        messages = mcp_http.parse_messages("text/event-stream", body)
        self.assertEqual(len(messages), 2)
        self.assertEqual(messages[1]["id"], 1)

    def test_empty_body(self) -> None:
        self.assertEqual(mcp_http.parse_messages("application/json", b""), [])


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    sse_tools = False
    seen_auth: str | None = None
    seen_session: str | None = None

    def log_message(self, *_args) -> None:  # silence
        pass

    def _write(self, status: int, body: bytes, content_type: str = "application/json", session: str | None = None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if session:
            self.send_header("Mcp-Session-Id", session)
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        message = json.loads(self.rfile.read(length) or b"{}")
        method = message.get("method")
        _Handler.seen_auth = self.headers.get("Authorization")
        _Handler.seen_session = self.headers.get("Mcp-Session-Id")

        if method == "initialize":
            body = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": message["id"],
                    "result": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "serverInfo": {"name": "test", "version": "1"},
                    },
                }
            ).encode()
            self._write(200, body, session="sess-1")
            return

        if method == "notifications/initialized":
            self._write(202, b"")
            return

        if method == "tools/list":
            payload = {"tools": [{"name": "ping", "description": "p", "inputSchema": {"type": "object"}}]}
            result = {"jsonrpc": "2.0", "id": message["id"], "result": payload}
            if _Handler.sse_tools:
                body = f"data: {json.dumps(result)}\n\n".encode()
                self._write(200, body, content_type="text/event-stream")
            else:
                self._write(200, json.dumps(result).encode())
            return

        if method == "tools/call":
            result = {
                "jsonrpc": "2.0",
                "id": message["id"],
                "result": {"content": [{"type": "text", "text": "pong"}]},
            }
            self._write(200, json.dumps(result).encode())
            return

        self._write(404, b"")

    def do_DELETE(self) -> None:
        self._write(204, b"")


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        host, port = cls.server.server_address
        cls.url = f"http://{host}:{port}/mcp"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()

    def test_list_tools_json(self) -> None:
        _Handler.sse_tools = False
        with mcp_http.RemoteMcpClient(self.url, access_token="tok") as client:
            tools = client.list_tools()
        self.assertEqual([tool["name"] for tool in tools], ["ping"])
        self.assertEqual(_Handler.seen_auth, "Bearer tok")
        self.assertEqual(_Handler.seen_session, "sess-1")

    def test_list_tools_sse(self) -> None:
        _Handler.sse_tools = True
        try:
            with mcp_http.RemoteMcpClient(self.url) as client:
                tools = client.list_tools()
        finally:
            _Handler.sse_tools = False
        self.assertEqual([tool["name"] for tool in tools], ["ping"])

    def test_call_tool(self) -> None:
        with mcp_http.RemoteMcpClient(self.url) as client:
            result = client.call_tool("ping", {"x": 1})
        self.assertEqual(result["content"][0]["text"], "pong")


if __name__ == "__main__":
    unittest.main()

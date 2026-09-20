"""Streamable HTTP client for remote MCP servers.

Implements the client side of the MCP Streamable HTTP transport (spec
2025-03-26 → 2025-11-25): a single endpoint that accepts JSON-RPC over POST,
may reply with either ``application/json`` or an SSE stream, and may assign a
session via the ``Mcp-Session-Id`` header.

Only the standard library is used. Each instance performs one ``initialize``
handshake and reuses the negotiated protocol version and session for the
lifetime of the object; callers create one per request (or per agent turn).

Auth is a bearer access token supplied by the caller — this module never
refreshes tokens itself. A ``401``/``403`` is surfaced as
:class:`RemoteMcpAuthError` so the caller can refresh and retry.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

DEFAULT_PROTOCOL_VERSION = "2025-11-25"
CLIENT_NAME = "get1agent"
CLIENT_VERSION = "1.0.0"
USER_AGENT = f"{CLIENT_NAME}/{CLIENT_VERSION}"
DEFAULT_TIMEOUT = 30


class RemoteMcpError(Exception):
    """The remote MCP server could not be reached or returned an error."""


class RemoteMcpAuthError(RemoteMcpError):
    """The access token was rejected (401/403) — refresh and retry."""


class RemoteMcpSessionExpired(RemoteMcpError):
    """The server dropped our session (404) — re-initialize."""


def _header(headers: dict[str, str], name: str) -> str | None:
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def _post(
    url: str,
    *,
    message: dict[str, Any],
    headers: dict[str, str],
    timeout: int,
) -> tuple[int, dict[str, str], bytes]:
    request = urllib.request.Request(
        url, data=json.dumps(message).encode("utf-8"), method="POST"
    )
    for key, value in headers.items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers or {}), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RemoteMcpError(f"network error: {exc}") from exc


def parse_messages(content_type: str | None, raw: bytes) -> list[dict[str, Any]]:
    """Decode a response body that is either one JSON object or an SSE stream."""
    text = raw.decode("utf-8", "replace")
    if "text/event-stream" in (content_type or "").lower():
        messages: list[dict[str, Any]] = []
        data_lines: list[str] = []

        def flush() -> None:
            if not data_lines:
                return
            chunk = "\n".join(data_lines)
            data_lines.clear()
            try:
                parsed = json.loads(chunk)
            except ValueError:
                return
            if isinstance(parsed, dict):
                messages.append(parsed)

        for line in text.splitlines():
            if line == "":
                flush()
            elif line.startswith(":"):
                continue
            elif line.startswith("data:"):
                data_lines.append(line[5:].lstrip())
        flush()
        return messages

    if not text.strip():
        return []
    try:
        parsed = json.loads(text)
    except ValueError:
        return []
    return [parsed] if isinstance(parsed, dict) else []


class RemoteMcpClient:
    """One connection to a remote Streamable HTTP MCP server."""

    def __init__(
        self,
        server_url: str,
        *,
        access_token: str | None = None,
        protocol_version: str = DEFAULT_PROTOCOL_VERSION,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self.server_url = server_url
        self.access_token = access_token
        self.protocol_version = protocol_version
        self.timeout = timeout
        self.session_id: str | None = None
        self.server_info: dict[str, Any] = {}
        self._initialized = False
        self._request_id = 0

    # -- context manager -----------------------------------------------------

    def __enter__(self) -> "RemoteMcpClient":
        self.initialize()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- plumbing ------------------------------------------------------------

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _headers(self, *, with_protocol: bool) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": USER_AGENT,
        }
        if with_protocol and self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _check_status(self, status: int, headers: dict[str, str], raw: bytes) -> None:
        if status in (401, 403):
            raise RemoteMcpAuthError(f"authorization rejected ({status})")
        if status == 404:
            raise RemoteMcpSessionExpired("session expired")
        if status >= 400:
            detail = raw[:300].decode("utf-8", "replace") if raw else ""
            raise RemoteMcpError(f"remote MCP error {status}: {detail}")

    def _reset_session(self) -> None:
        self.session_id = None
        self._initialized = False

    # -- protocol ------------------------------------------------------------

    def initialize(self) -> dict[str, Any]:
        message = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": "initialize",
            "params": {
                "protocolVersion": self.protocol_version,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        }
        status, headers, raw = _post(
            self.server_url,
            message=message,
            headers=self._headers(with_protocol=False),
            timeout=self.timeout,
        )
        self._check_status(status, headers, raw)

        session_id = _header(headers, "mcp-session-id")
        if session_id:
            self.session_id = session_id

        result = self._extract_result(message["id"], headers, raw)
        version = result.get("protocolVersion")
        if isinstance(version, str) and version:
            self.protocol_version = version
        self.server_info = result.get("serverInfo") or {}

        self._notify("notifications/initialized", {})
        self._initialized = True
        return result

    def _extract_result(
        self, request_id: int, headers: dict[str, str], raw: bytes
    ) -> dict[str, Any]:
        messages = parse_messages(_header(headers, "content-type"), raw)
        for message in messages:
            if message.get("id") != request_id:
                continue
            if "error" in message:
                error = message.get("error") or {}
                raise RemoteMcpError(
                    f"JSON-RPC error {error.get('code')}: {error.get('message')}"
                )
            result = message.get("result")
            return result if isinstance(result, dict) else {}
        raise RemoteMcpError("no matching JSON-RPC response")

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        message = {"jsonrpc": "2.0", "method": method, "params": params}
        status, headers, raw = _post(
            self.server_url,
            message=message,
            headers=self._headers(with_protocol=True),
            timeout=self.timeout,
        )
        # Notifications expect 202; tolerate 200/204 and ignore 4xx/5xx.
        if status in (401, 403):
            self._check_status(status, headers, raw)

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._initialized:
            self.initialize()
        message = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params,
        }
        status, headers, raw = _post(
            self.server_url,
            message=message,
            headers=self._headers(with_protocol=True),
            timeout=self.timeout,
        )
        self._check_status(status, headers, raw)
        return self._extract_result(message["id"], headers, raw)

    def _rpc_retry(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Run an RPC, re-initializing once if the session was dropped."""
        try:
            return self._rpc(method, params)
        except RemoteMcpSessionExpired:
            self._reset_session()
            self.initialize()
            return self._rpc(method, params)

    # -- tools ---------------------------------------------------------------

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._rpc_retry("tools/list", {})
        tools = result.get("tools")
        return [tool for tool in tools or [] if isinstance(tool, dict)]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._rpc_retry(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )

    def close(self) -> None:
        if not self.session_id:
            return
        request = urllib.request.Request(self.server_url, method="DELETE")
        for key, value in self._headers(with_protocol=True).items():
            request.add_header(key, value)
        try:
            urllib.request.urlopen(request, timeout=self.timeout).close()
        except (urllib.error.URLError, TimeoutError, OSError):
            pass


def list_tools(
    server_url: str,
    *,
    access_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict[str, Any]]:
    with RemoteMcpClient(server_url, access_token=access_token, timeout=timeout) as client:
        return client.list_tools()


def call_tool(
    server_url: str,
    name: str,
    arguments: dict[str, Any] | None = None,
    *,
    access_token: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    with RemoteMcpClient(server_url, access_token=access_token, timeout=timeout) as client:
        return client.call_tool(name, arguments)

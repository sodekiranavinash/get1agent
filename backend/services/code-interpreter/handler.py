"""code-interpreter MCP server Lambda.

Runs LLM-generated Python in a Bedrock AgentCore Code Interpreter sandbox,
exposed as its own MCP server (the ``code-interpreter`` tool).

Flow: static guard -> resolve/reuse a per-user AgentCore session (TTL + cap) ->
execute -> return output. The function runs outside a VPC (AgentCore + DynamoDB
are public endpoints). When ``CODE_INTERPRETER_MODE=local`` the AgentCore /
DynamoDB path is replaced by a guarded local subprocess (Floci development).

The guard + session + execution machinery is shared with the ``custom-tools``
server and lives in :mod:`core.sandbox`.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from core.mcp_server import build_handler, require_sub
from core.sandbox import SandboxConfig, agentcore, run_code

from data.repositories.users import get_user_by_sub

mcp = MCPLambdaHandler(name="get1agent-code-interpreter", version="1.0.0")

CODE_TOOL = "code-interpreter"

_CODE_SCHEMA: dict[str, Any] = {
    "name": CODE_TOOL,
    "description": (
        "Execute Python code in an isolated sandbox and return its output. Use "
        "this for calculations, data analysis and transforming data. Network "
        "access, package installs, heavy ML frameworks and OS/shell escapes are "
        "blocked. Pass the same conversationId across calls to reuse one sandbox."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "Python code to execute.",
            },
            "conversationId": {
                "type": "string",
                "description": (
                    "Optional conversation/thread id. Calls with the same id "
                    "reuse one sandbox; omit to use the per-user default."
                ),
            },
        },
        "required": ["code"],
    },
}


# --- config ------------------------------------------------------------------


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _config() -> SandboxConfig:
    return SandboxConfig(
        mode=os.environ.get("CODE_INTERPRETER_MODE", "agentcore").strip().lower(),
        identifier=os.environ.get(
            "CODE_INTERPRETER_IDENTIFIER", agentcore.DEFAULT_IDENTIFIER
        ),
        region=(
            os.environ.get("CODE_INTERPRETER_REGION")
            or os.environ.get("AWS_REGION")
            or "ap-south-1"
        ),
        # Sessions live in the shared single table; the dedicated name is kept
        # as a fallback for older deployments.
        table=os.environ.get("CODE_INTERPRETER_SESSIONS_TABLE")
        or os.environ.get("DYNAMODB_TABLE", ""),
        session_ttl=_env_int("CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS", 900),
        exec_timeout=_env_int("CODE_INTERPRETER_EXEC_TIMEOUT_SECONDS", 120),
        max_sessions=max(_env_int("CODE_INTERPRETER_MAX_SESSIONS_PER_USER", 1), 1),
        max_code_bytes=_env_int("CODE_INTERPRETER_MAX_CODE_BYTES", 102_400),
        max_output=_env_int("CODE_INTERPRETER_MAX_OUTPUT_CHARS", 20_000),
        thread_prefix="CONV#",
        session_name_prefix="ci-",
    )


def _log(event: str, **fields: Any) -> None:
    print(json.dumps({"event": event, **fields}, default=str), flush=True)


# --- execution ---------------------------------------------------------------


def execute(
    sub: str, code: str, language: str, conversation_id: str | None
) -> dict[str, Any]:
    """Run ``code`` for ``sub``; returns the tool result payload."""
    return run_code(
        sub,
        code,
        conversation_id=conversation_id,
        config=_config(),
        language=language,
        blocked_extra=os.environ.get("BLOCKED_MODULES", ""),
        allowed_extra=os.environ.get("ALLOWED_MODULES", ""),
        log=_log,
    )


def code_interpreter(
    code: str,
    language: str = "python",
    conversationId: str | None = None,
) -> str:
    """Execute Python code in an isolated sandbox and return the output."""
    try:
        result = execute(require_sub(), code, language, conversationId)
    except Exception as exc:  # noqa: BLE001
        print(f"code-interpreter error: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        result = {
            "error": {"code": "internal_error", "message": "Request failed", "detail": repr(exc)[:300]}
        }
    return json.dumps(result, default=str)


mcp.tools[CODE_TOOL] = _CODE_SCHEMA
mcp.tool_implementations[CODE_TOOL] = code_interpreter


def _resolve_user_id(sub: str) -> str | None:
    """Map the HTTP caller's Auth0 sub to the internal userId for sessions."""
    try:
        profile = get_user_by_sub(sub)
    except Exception:  # noqa: BLE001 - fall through to an unauthenticated tool error
        return None
    return str(profile["userId"]) if profile else None


lambda_handler = build_handler(mcp, resolve_user_id=_resolve_user_id)

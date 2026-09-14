"""code-interpreter MCP server Lambda.

Runs LLM-generated Python in a Bedrock AgentCore Code Interpreter sandbox,
exposed as its own MCP server (the ``code-interpreter`` tool).

Flow: static guard -> resolve/reuse a per-user AgentCore session (TTL + cap) ->
execute -> return output. The function runs outside a VPC (AgentCore + DynamoDB
are public endpoints). When ``CODE_INTERPRETER_MODE=local`` the AgentCore /
DynamoDB path is replaced by a guarded local subprocess (Floci development).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import traceback
from typing import Any

from awslabs.mcp_lambda_handler import MCPLambdaHandler

from ai.mcp_server import build_handler, require_sub

import agentcore
import guard
import local_exec
import sessions

from shared.users import get_user_by_sub

_THREAD_RE = re.compile(r"[^A-Za-z0-9_.:-]+")

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


def _config() -> dict[str, Any]:
    return {
        "mode": os.environ.get("CODE_INTERPRETER_MODE", "agentcore").strip().lower(),
        "identifier": os.environ.get(
            "CODE_INTERPRETER_IDENTIFIER", agentcore.DEFAULT_IDENTIFIER
        ),
        "region": (
            os.environ.get("CODE_INTERPRETER_REGION")
            or os.environ.get("AWS_REGION")
            or "ap-south-1"
        ),
        # Sessions live in the shared single table; the dedicated name is kept
        # as a fallback for older deployments.
        "table": os.environ.get("CODE_INTERPRETER_SESSIONS_TABLE")
        or os.environ.get("DYNAMODB_TABLE", ""),
        "session_ttl": _env_int("CODE_INTERPRETER_SESSION_TIMEOUT_SECONDS", 900),
        "exec_timeout": _env_int("CODE_INTERPRETER_EXEC_TIMEOUT_SECONDS", 120),
        "max_sessions": max(_env_int("CODE_INTERPRETER_MAX_SESSIONS_PER_USER", 1), 1),
        "max_code_bytes": _env_int("CODE_INTERPRETER_MAX_CODE_BYTES", 102_400),
        "max_output": _env_int("CODE_INTERPRETER_MAX_OUTPUT_CHARS", 20_000),
        "safety_margin": 30,
    }


def _log(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    print(json.dumps(payload, default=str), flush=True)


def _sanitize_thread(conversation_id: str | None) -> str:
    raw = str(conversation_id or "").strip()
    if not raw:
        return sessions.DEFAULT_THREAD
    cleaned = _THREAD_RE.sub("-", raw)[:64].strip("-")
    return cleaned or sessions.DEFAULT_THREAD


def _error(code: str, message: str, detail: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail:
        payload["error"]["detail"] = detail
    return payload


# --- execution ---------------------------------------------------------------


def _shape(
    result: dict[str, Any],
    *,
    session_id: str | None,
    reused: bool,
    started: float,
) -> dict[str, Any]:
    return {
        "output": result.get("output") or "",
        "isError": bool(result.get("is_error")),
        "timedOut": bool(result.get("timed_out")),
        "sessionId": session_id,
        "reused": reused,
        "durationMs": int((time.perf_counter() - started) * 1000),
    }


def _stop_quietly(client: Any, identifier: str, session_id: str | None) -> None:
    if not session_id:
        return
    try:
        agentcore.stop_session(client, identifier, session_id)
    except Exception as exc:  # noqa: BLE001 - cleanup must not mask the error
        _log("code-interpreter stop failed", sessionId=session_id, error=str(exc))


def _create_session(
    client: Any,
    store: sessions.SessionStore,
    sub: str,
    thread: str,
    cfg: dict[str, Any],
    now: int,
) -> sessions.SessionRef:
    pk, sk = sessions.partition_key(sub), sessions.sort_key(thread)

    active = store.list_active(pk, now)
    if len(active) >= cfg["max_sessions"]:
        victim = min(active, key=lambda item: int(item.get("lastUsedAt", 0)))
        _stop_quietly(client, cfg["identifier"], str(victim.get("sessionId") or ""))
        store.delete(str(victim.get("pk")), str(victim.get("sk")))

    token = sessions.deterministic_token(sub, thread, now, cfg["session_ttl"])
    name = "ci-" + hashlib.sha1(f"{sub}:{thread}".encode("utf-8")).hexdigest()[:32]
    session_id = agentcore.start_session(
        client, cfg["identifier"], name=name, ttl=cfg["session_ttl"], client_token=token
    )
    item = sessions.new_item(pk, sk, session_id, cfg["session_ttl"], now)
    if store.claim(item, now):
        _log("code-interpreter session created", sessionId=session_id, conversationId=thread)
        return sessions.SessionRef(session_id, reused=False)

    # Lost a race with a concurrent invocation: reuse the winner's session.
    winner = store.get(pk, sk)
    winner_id = str((winner or {}).get("sessionId") or "")
    if winner_id and winner_id != session_id:
        # Same deterministic token normally returns the same session; if not,
        # drop the extra one so we never leak a sandbox.
        _stop_quietly(client, cfg["identifier"], session_id)
    if not winner_id:
        return sessions.SessionRef(session_id, reused=False)
    return sessions.SessionRef(winner_id, reused=True)


def _execute_agentcore(
    sub: str,
    thread: str,
    code: str,
    prelude: str,
    cfg: dict[str, Any],
    started: float,
) -> dict[str, Any]:
    if not cfg["table"]:
        return _error("not_configured", "CODE_INTERPRETER_SESSIONS_TABLE is not set")

    now = int(time.time())
    client = agentcore.client(cfg["region"], cfg["exec_timeout"])
    store = sessions.SessionStore(cfg["table"], cfg["region"])
    pk, sk = sessions.partition_key(sub), sessions.sort_key(thread)

    def _resolve_ref() -> sessions.SessionRef:
        entry = store.get(pk, sk)
        if entry and int(entry.get("expiresAt", 0)) > now + cfg["safety_margin"]:
            return sessions.SessionRef(str(entry["sessionId"]), reused=True)
        return _create_session(client, store, sub, thread, cfg, now)

    try:
        ref = _resolve_ref()
    except agentcore.AgentCoreError as exc:
        _log("code-interpreter session failed", error=exc.message, code=exc.code)
        return _error("session_failed", exc.message, detail=exc.code)

    script = f"{prelude}\n{code}\n"

    def _run_once(session_id: str) -> dict[str, Any]:
        return agentcore.execute(
            client,
            cfg["identifier"],
            session_id,
            code=script,
            language="python",
            timeout=cfg["exec_timeout"],
            max_output=cfg["max_output"],
        )

    try:
        result = _run_once(ref.session_id)
    except agentcore.SessionGone:
        # Stale mapping: recreate once and retry.
        store.delete(pk, sk)
        try:
            ref = _resolve_ref()
        except agentcore.AgentCoreError as exc:
            _log("code-interpreter session failed", error=exc.message, code=exc.code)
            return _error("session_failed", exc.message, detail=exc.code)
        try:
            result = _run_once(ref.session_id)
        except agentcore.SessionGone as exc:
            store.delete(pk, sk)
            _log("code-interpreter failed", error=str(exc))
            return _error("execution_failed", exc.message)
        except agentcore.ExecutionTimeout as exc:
            _stop_quietly(client, cfg["identifier"], ref.session_id)
            store.delete(pk, sk)
            _log("code-interpreter timeout", sessionId=ref.session_id)
            return _error("execution_timeout", exc.message)
    except agentcore.ExecutionTimeout as exc:
        _stop_quietly(client, cfg["identifier"], ref.session_id)
        store.delete(pk, sk)
        _log("code-interpreter timeout", sessionId=ref.session_id)
        return _error("execution_timeout", exc.message)

    if ref.reused:
        store.touch(pk, sk, now)
    _log(
        "code-interpreter executed",
        sessionId=ref.session_id,
        conversationId=thread,
        reused=ref.reused,
        isError=result.get("is_error"),
        durationMs=int((time.perf_counter() - started) * 1000),
    )
    return _shape(result, session_id=ref.session_id, reused=ref.reused, started=started)


def execute(
    sub: str, code: str, language: str, conversation_id: str | None
) -> dict[str, Any]:
    """Run ``code`` for ``sub``; returns the tool result payload."""
    started = time.perf_counter()
    cfg = _config()

    language = (language or "python").strip().lower()
    if language != "python":
        return _error("unsupported_language", f"Unsupported language: {language}")
    if not isinstance(code, str) or not code.strip():
        return _error("invalid_code", "code must be a non-empty string")

    blocked_extra = os.environ.get("BLOCKED_MODULES", "")
    allowed_extra = os.environ.get("ALLOWED_MODULES", "")
    decision = guard.check(
        code,
        max_bytes=cfg["max_code_bytes"],
        blocked_extra=blocked_extra,
        allowed_extra=allowed_extra,
    )
    if not decision.ok:
        _log("code-interpreter blocked", reason=decision.reason, detail=decision.detail)
        return _error("blocked", decision.reason or "Blocked by policy", decision.detail)

    prelude = guard.prelude(blocked_extra=blocked_extra, allowed_extra=allowed_extra)
    thread = _sanitize_thread(conversation_id)

    if cfg["mode"] == "local":
        ref = sessions.local_resolve(sub, thread, cfg["session_ttl"], int(time.time()))
        result = local_exec.run(
            code,
            timeout=cfg["exec_timeout"],
            prelude=prelude,
            max_output=cfg["max_output"],
        )
        _log(
            "code-interpreter executed (local)",
            sessionId=ref.session_id,
            conversationId=thread,
            reused=ref.reused,
            isError=result.get("is_error"),
            durationMs=int((time.perf_counter() - started) * 1000),
        )
        return _shape(result, session_id=ref.session_id, reused=ref.reused, started=started)

    return _execute_agentcore(sub, thread, code, prelude, cfg, started)


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
        result = _error("internal_error", "Request failed", detail=repr(exc)[:300])
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

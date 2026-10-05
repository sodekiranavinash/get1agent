"""Shared Python sandbox runner.

Owns the full "run some Python for a user" flow used by both the
``code-interpreter`` MCP tool and the ``custom-tools`` MCP server:

1. static policy check (:mod:`core.sandbox.guard`),
2. resolve/reuse a per-user AgentCore session (TTL + cap + conditional claim),
3. execute in the AgentCore microVM, or a guarded local subprocess when the
   mode is ``local`` (Floci development).

The result shape is identical across backends: ``{output, isError, timedOut,
sessionId, reused, durationMs}`` or ``{error: {code, message, detail?}}``.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any, Callable

from . import agentcore, guard, local_exec, sessions


@dataclass(frozen=True)
class SandboxConfig:
    """Per-service sandbox configuration (built from env by each handler)."""

    mode: str
    identifier: str
    region: str
    table: str
    session_ttl: int
    exec_timeout: int
    max_sessions: int
    max_code_bytes: int
    max_output: int
    safety_margin: int = 30
    # Session rows live under ``USER#<sub>`` / ``<thread_prefix><thread>``. A
    # distinct prefix keeps two services from sharing one sandbox by accident.
    thread_prefix: str = "CONV#"
    session_name_prefix: str = "ci-"
    # When true the sandbox may reach the public internet (HTTP(S)); outbound
    # connections are counted and private/reserved destinations are refused.
    allow_network: bool = False
    max_connections: int = 25


def _log_default(event: str, **fields: Any) -> None:
    import json

    print(json.dumps({"event": event, **fields}, default=str), flush=True)


def error(code: str, message: str, detail: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"error": {"code": code, "message": message}}
    if detail:
        payload["error"]["detail"] = detail
    return payload


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


def _stop_quietly(
    client: Any, identifier: str, session_id: str | None, log: Callable[..., None]
) -> None:
    if not session_id:
        return
    try:
        agentcore.stop_session(client, identifier, session_id)
    except Exception as exc:  # noqa: BLE001 - cleanup must not mask the error
        log("sandbox stop failed", sessionId=session_id, error=str(exc))


def _create_session(
    client: Any,
    store: sessions.SessionStore,
    sub: str,
    thread: str,
    cfg: SandboxConfig,
    now: int,
    log: Callable[..., None],
) -> sessions.SessionRef:
    pk = sessions.partition_key(sub)
    sk = sessions.sort_key(thread, cfg.thread_prefix)

    active = store.list_active(pk, now)
    if len(active) >= cfg.max_sessions:
        victim = min(active, key=lambda item: int(item.get("lastUsedAt", 0)))
        _stop_quietly(client, cfg.identifier, str(victim.get("sessionId") or ""), log)
        store.delete(str(victim.get("pk")), str(victim.get("sk")))

    token = sessions.deterministic_token(sub, thread, now, cfg.session_ttl)
    name = cfg.session_name_prefix + hashlib.sha1(
        f"{sub}:{thread}".encode("utf-8")
    ).hexdigest()[:32]
    session_id = agentcore.start_session(
        client, cfg.identifier, name=name, ttl=cfg.session_ttl, client_token=token
    )
    item = sessions.new_item(pk, sk, session_id, cfg.session_ttl, now)
    if store.claim(item, now):
        log("sandbox session created", sessionId=session_id, conversationId=thread)
        return sessions.SessionRef(session_id, reused=False)

    # Lost a race with a concurrent invocation: reuse the winner's session.
    winner = store.get(pk, sk)
    winner_id = str((winner or {}).get("sessionId") or "")
    if winner_id and winner_id != session_id:
        # Same deterministic token normally returns the same session; if not,
        # drop the extra one so we never leak a sandbox.
        _stop_quietly(client, cfg.identifier, session_id, log)
    if not winner_id:
        return sessions.SessionRef(session_id, reused=False)
    return sessions.SessionRef(winner_id, reused=True)


def _execute_agentcore(
    sub: str,
    thread: str,
    code: str,
    prelude: str,
    cfg: SandboxConfig,
    started: float,
    log: Callable[..., None],
    timeout: int | None = None,
) -> dict[str, Any]:
    if not cfg.table:
        return error("not_configured", "The sandbox session table is not set")
    deadline = timeout or cfg.exec_timeout

    now = int(time.time())
    client = agentcore.client(cfg.region, deadline)
    store = sessions.SessionStore(cfg.table, cfg.region)
    pk = sessions.partition_key(sub)
    sk = sessions.sort_key(thread, cfg.thread_prefix)

    def _resolve_ref() -> sessions.SessionRef:
        entry = store.get(pk, sk)
        if entry and int(entry.get("expiresAt", 0)) > now + cfg.safety_margin:
            return sessions.SessionRef(str(entry["sessionId"]), reused=True)
        return _create_session(client, store, sub, thread, cfg, now, log)

    try:
        ref = _resolve_ref()
    except agentcore.AgentCoreError as exc:
        log("sandbox session failed", error=exc.message, code=exc.code)
        return error("session_failed", exc.message, detail=exc.code)

    script = f"{prelude}\n{code}\n"

    def _run_once(session_id: str) -> dict[str, Any]:
        return agentcore.execute(
            client,
            cfg.identifier,
            session_id,
            code=script,
            language="python",
            timeout=deadline,
            max_output=cfg.max_output,
        )

    try:
        result = _run_once(ref.session_id)
    except agentcore.SessionGone:
        # Stale mapping: recreate once and retry.
        store.delete(pk, sk)
        try:
            ref = _resolve_ref()
        except agentcore.AgentCoreError as exc:
            log("sandbox session failed", error=exc.message, code=exc.code)
            return error("session_failed", exc.message, detail=exc.code)
        try:
            result = _run_once(ref.session_id)
        except agentcore.SessionGone as exc:
            store.delete(pk, sk)
            log("sandbox failed", error=str(exc))
            return error("execution_failed", exc.message)
        except agentcore.ExecutionTimeout as exc:
            _stop_quietly(client, cfg.identifier, ref.session_id, log)
            store.delete(pk, sk)
            log("sandbox timeout", sessionId=ref.session_id)
            return error("execution_timeout", exc.message)
    except agentcore.ExecutionTimeout as exc:
        _stop_quietly(client, cfg.identifier, ref.session_id, log)
        store.delete(pk, sk)
        log("sandbox timeout", sessionId=ref.session_id)
        return error("execution_timeout", exc.message)

    if ref.reused:
        store.touch(pk, sk, now)
    log(
        "sandbox executed",
        sessionId=ref.session_id,
        conversationId=thread,
        reused=ref.reused,
        isError=result.get("is_error"),
        durationMs=int((time.perf_counter() - started) * 1000),
    )
    return _shape(result, session_id=ref.session_id, reused=ref.reused, started=started)


def run_code(
    sub: str,
    code: str,
    *,
    conversation_id: str | None,
    config: SandboxConfig,
    language: str = "python",
    blocked_extra: str = "",
    allowed_extra: str = "",
    prelude: str | None = None,
    exec_timeout: int | None = None,
    log: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Run ``code`` for ``sub``; returns the shared result payload.

    ``exec_timeout`` overrides the config's wall-clock limit for this call (used
    by the MCP Builder test path, which is allowed a longer budget than a real
    tool invocation).
    """
    log = log or _log_default
    started = time.perf_counter()
    timeout = exec_timeout or config.exec_timeout

    language = (language or "python").strip().lower()
    if language != "python":
        return error("unsupported_language", f"Unsupported language: {language}")
    if not isinstance(code, str) or not code.strip():
        return error("invalid_code", "code must be a non-empty string")

    decision = guard.check(
        code,
        max_bytes=config.max_code_bytes,
        blocked_extra=blocked_extra,
        allowed_extra=allowed_extra,
        allow_network=config.allow_network,
    )
    if not decision.ok:
        log("sandbox blocked", reason=decision.reason, detail=decision.detail)
        return error("blocked", decision.reason or "Blocked by policy", decision.detail)

    preamble = prelude or guard.prelude(
        blocked_extra=blocked_extra,
        allowed_extra=allowed_extra,
        allow_network=config.allow_network,
        max_connections=config.max_connections,
    )
    thread = sessions.sanitize_thread(conversation_id)

    if config.mode == "local":
        ref = sessions.local_resolve(
            sub, thread, config.session_ttl, int(time.time()), config.thread_prefix
        )
        result = local_exec.run(
            code,
            timeout=timeout,
            prelude=preamble,
            max_output=config.max_output,
        )
        log(
            "sandbox executed (local)",
            sessionId=ref.session_id,
            conversationId=thread,
            reused=ref.reused,
            isError=result.get("is_error"),
            durationMs=int((time.perf_counter() - started) * 1000),
        )
        return _shape(result, session_id=ref.session_id, reused=ref.reused, started=started)

    return _execute_agentcore(
        sub, thread, code, preamble, config, started, log, timeout=timeout
    )

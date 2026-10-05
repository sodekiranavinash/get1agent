"""Validate arguments, run a user tool in the sandbox, validate its result."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable

from core import network, ratelimit
from core.sandbox import run_code

from data.repositories import quotas

from . import config, harness, schema


def run_tool(
    sub: str,
    *,
    code: str,
    args: dict[str, Any],
    input_schema: dict[str, Any] | None,
    output_schema: dict[str, Any] | None,
    entrypoint: str = harness.DEFAULT_ENTRYPOINT,
    is_test: bool = False,
    conversation_id: str | None = None,
    log: Callable[..., None] | None = None,
) -> dict[str, Any]:
    """Execute one tool call and return a normalized result payload."""
    if not isinstance(code, str) or not code.strip():
        return _error("no_code", "This tool has no source code")

    input_errors = schema.validate(args, schema.normalize_schema(input_schema))
    if input_errors:
        return _error(
            "invalid_input",
            "Arguments do not match the tool's input schema",
            detail="; ".join(input_errors),
        )

    cfg = config.sandbox_config()
    # Admin kill switch: when platform network is off, run offline (pure tools
    # still work) and skip the network rate limit.
    network_on = cfg.allow_network and network.enabled()
    if network_on and not ratelimit.allow(
        sub, kind="custom-tools", limit=config.runs_per_hour()
    ):
        return _error(
            "rate_limited",
            "Too many custom-tool runs in the last hour. "
            "Please wait a few minutes and try again.",
        )
    cfg = replace(cfg, allow_network=network_on)
    if network_on:
        try:
            quotas.record_network_run(sub)
        except Exception:  # noqa: BLE001 - usage counting must not fail a run
            pass

    program = harness.build_program(code, args, entrypoint)
    result = run_code(
        sub,
        program,
        conversation_id=conversation_id,
        config=cfg,
        blocked_extra=config.blocked_modules(),
        allowed_extra=config.allowed_modules(),
        exec_timeout=config.test_exec_timeout() if is_test else None,
        log=log,
    )

    if "error" in result:
        return _error(
            str(result["error"].get("code") or "sandbox_error"),
            str(result["error"].get("message") or "Execution failed"),
            detail=result["error"].get("detail"),
            duration_ms=result.get("durationMs"),
        )

    output = str(result.get("output") or "")
    parsed = harness.parse_output(output)
    if parsed is None:
        return {
            "ok": False,
            "error": {
                "code": "no_result",
                "message": (
                    "The tool did not return a result. Make sure it defines a "
                    f"`{entrypoint}(args)` function."
                ),
            },
            "output": output[-4000:],
            "durationMs": result.get("durationMs"),
        }

    if "error" in parsed:
        return {
            "ok": False,
            "error": {
                "code": "tool_error",
                "message": str(parsed.get("error") or "Tool raised an error"),
                "traceback": str(parsed.get("traceback") or "")[-4000:],
            },
            "output": output[-4000:],
            "durationMs": result.get("durationMs"),
        }

    value = parsed.get("result")
    output_errors = schema.validate(value, schema.normalize_schema(output_schema))
    return {
        "ok": True,
        "result": value,
        "outputSchemaErrors": output_errors,
        "durationMs": result.get("durationMs"),
        "sessionId": result.get("sessionId"),
        "reused": bool(result.get("reused")),
    }


def _error(
    code: str,
    message: str,
    *,
    detail: str | None = None,
    duration_ms: int | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": {"code": code, "message": message}}
    if detail:
        payload["error"]["detail"] = detail
    if duration_ms is not None:
        payload["durationMs"] = duration_ms
    return payload

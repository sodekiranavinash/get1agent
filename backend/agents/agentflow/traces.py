"""Build and persist a Langfuse-style trace for one agent run (AWS-native).

The runtime already streams normalized frames and records them for the
transcript. This module projects those frames into a **trace + observations**
tree (the Langfuse data model) with real per-observation timing, so the traces
page can render a rich explorer instead of a coarse X-Ray waterfall:

* the full tree is written to S3 (``retrieval.layout.trace_key``) — inputs,
  outputs, arguments and tool results stay here, never in DynamoDB;
* a small index item goes to DynamoDB (``data.repositories.traces``) so the
  list/filter view is one Query with no S3 reads;
* ``agentflow.observability`` still exports the OpenTelemetry spans that
  CloudWatch GenAI Observability reads — this store is additive, not a
  replacement.

The hierarchy mirrors how a run actually executes, so the tree reads in order:

    run (SPAN)
      ├─ skills / attachments (EVENT)
      ├─ planner (GENERATION)          the plan
      │    ├─ tool (TOOL)              each planned step
      │    └─ tool (TOOL)
      └─ answer (GENERATION)           the final response

Everything is best-effort: a trace-store failure must never fail a run.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from agentflow.config import RuntimeConfig
from core.storage import Storage
from data.repositories import traces as traces_repo
from retrieval.layout import trace_key

# A single observation must not balloon the S3 object; clip the long fields.
MAX_FIELD_CHARS = 40_000
# How many observations one trace may carry (drop the rest, count is kept).
MAX_OBSERVATIONS = 400


def _warn(message: str, exc: BaseException) -> None:
    print(
        json.dumps({"level": "warning", "message": message, "error": str(exc)}),
        flush=True,
    )


def _clip(value: Any, limit: int = MAX_FIELD_CHARS) -> Any:
    """Bound a field for storage without losing its type when small."""
    if value is None:
        return None
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit]
    try:
        text = json.dumps(value, default=str)
    except (TypeError, ValueError):
        text = str(value)
    if len(text) <= limit:
        return value
    return text[:limit]


def _parse_ms(value: Any) -> int | None:
    """ISO timestamp -> epoch milliseconds (None when unparseable)."""
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str) or not value:
        return None
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)
    except (TypeError, ValueError):
        return None


def _event_at(event: dict[str, Any], fallback: int | None) -> int | None:
    value = event.get("_at")
    return int(value) if isinstance(value, (int, float)) else fallback


def _observation_id(trace_id: str, kind: str, key: str) -> str:
    return f"{trace_id}-{kind}-{key}"


def _normalize_status(status: str) -> str:
    return "ok" if status in ("completed", "ok", "") else str(status)


def _cost_micro_usd(model: str, usage: dict[str, Any]) -> int:
    try:
        from core import usage as usage_mod

        return int(
            usage_mod.cost_micro_usd(
                model,
                int(usage.get("inputTokens") or 0),
                int(usage.get("outputTokens") or 0),
            )
        )
    except Exception:  # noqa: BLE001 - pricing must never break a trace
        return 0


def _planner_model() -> str:
    return (os.environ.get("AGENT_PLANNER_MODEL") or "").strip()


def build_trace(
    *,
    trace_id: str,
    run_id: str,
    user_id: str,
    agent_id: str,
    agent_name: str,
    model: str,
    provider: str | None,
    conversation_id: str | None,
    question: str,
    answer: str,
    status: str,
    started_at: str,
    ended_at: str,
    events: list[dict[str, Any]],
    usage: dict[str, Any] | None,
    tags: list[str],
) -> dict[str, Any]:
    """Project a run's recorded frames into a trace + observation tree."""
    trace_id = str(trace_id)
    start_ms = _parse_ms(started_at)
    end_ms = _parse_ms(ended_at)
    latency_ms = (
        max(0, end_ms - start_ms)
        if start_ms is not None and end_ms is not None
        else None
    )

    observations: list[dict[str, Any]] = []
    root_id = _observation_id(trace_id, "run", "root")
    planner_id = _observation_id(trace_id, "planner", "0")
    answer_id = _observation_id(trace_id, "gen", "answer")
    pending_tools: dict[str, dict[str, Any]] = {}
    tool_order: list[str] = []
    error_message: str | None = None
    has_plan = False
    first_text_at: int | None = None
    last_tool_end: int | None = None
    cursor = start_ms

    def add(observation: dict[str, Any]) -> None:
        if len(observations) < MAX_OBSERVATIONS:
            observations.append(observation)

    for event in events:
        if not isinstance(event, dict):
            continue
        kind = event.get("type")
        at = _event_at(event, cursor)
        if at is not None:
            cursor = at

        if kind == "plan":
            has_plan = True
            add(
                {
                    "id": planner_id,
                    "parentObservationId": root_id,
                    "type": "GENERATION",
                    "name": "planner",
                    "model": _planner_model() or None,
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": _clip(question),
                    "output": _clip(
                        {
                            "understanding": event.get("understanding"),
                            "subQueries": event.get("subQueries"),
                        }
                    ),
                    "usage": None,
                    "metadata": {"kind": "plan"},
                }
            )
        elif kind in ("tool.start", "tool.input", "tool.stream", "tool.result"):
            tool_use_id = str(event.get("toolUseId") or f"tool-{len(tool_order)}")
            tool = pending_tools.get(tool_use_id)
            if tool is None:
                tool = {
                    "id": _observation_id(trace_id, "tool", tool_use_id),
                    # Tools are the plan's steps: nest them under the planner so
                    # the tree reads plan -> tool, not answer -> tool.
                    "parentObservationId": planner_id if has_plan else root_id,
                    "type": "TOOL",
                    "name": str(event.get("name") or "tool"),
                    "startTime": at,
                    "endTime": None,
                    "durationMs": None,
                    "level": "DEFAULT",
                    "input": None,
                    "output": None,
                    "usage": None,
                    "metadata": {},
                }
                pending_tools[tool_use_id] = tool
                tool_order.append(tool_use_id)
            if event.get("name"):
                tool["name"] = str(event["name"])
            if kind in ("tool.start", "tool.input") and event.get("input") is not None:
                tool["input"] = _clip(event.get("input"))
            if kind == "tool.result":
                tool["endTime"] = at
                tool["output"] = _clip(event.get("data"))
                tool["durationMs"] = (
                    max(0, at - tool["startTime"])
                    if at is not None and tool.get("startTime") is not None
                    else None
                )
                tool["level"] = (
                    "ERROR" if str(event.get("status") or "") == "error" else "DEFAULT"
                )
                if event.get("sources"):
                    tool["metadata"]["sources"] = _clip(event.get("sources"))
            if tool.get("endTime") is not None:
                last_tool_end = max(last_tool_end or 0, int(tool["endTime"]))
        elif kind == "skills":
            names = [str(s.get("name")) for s in (event.get("skills") or []) if s.get("name")]
            add(
                {
                    "id": _observation_id(trace_id, "event", "skills"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "skills",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": None,
                    "output": names,
                    "usage": None,
                    "metadata": {"kind": "skills"},
                }
            )
        elif kind == "attachments":
            files = [str(f.get("fileName")) for f in (event.get("files") or []) if f.get("fileName")]
            add(
                {
                    "id": _observation_id(trace_id, "event", "attachments"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "attachments",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": None,
                    "output": files,
                    "usage": None,
                    "metadata": {"kind": "attachments"},
                }
            )
        elif kind == "question":
            add(
                {
                    "id": _observation_id(trace_id, "event", "question"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "user_question",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": _clip(event.get("question")),
                    "output": _clip(event.get("answer")),
                    "usage": None,
                    "metadata": {"options": event.get("options") or []},
                }
            )
        elif kind == "context":
            add(
                {
                    "id": _observation_id(trace_id, "event", "context"),
                    "parentObservationId": root_id,
                    "type": "EVENT",
                    "name": "context",
                    "startTime": at,
                    "endTime": at,
                    "durationMs": 0,
                    "level": "DEFAULT",
                    "input": None,
                    "output": None,
                    "usage": None,
                    "metadata": {
                        "usedTokens": event.get("usedTokens"),
                        "limitTokens": event.get("limitTokens"),
                        "ratio": event.get("ratio"),
                        "breakdown": event.get("breakdown"),
                    },
                }
            )
        elif kind == "text":
            if first_text_at is None:
                first_text_at = at
        elif kind == "run.error":
            error_message = str(event.get("message") or event.get("error") or "run failed")

    # Finish any tool that never produced a result (errored/aborted runs).
    for tool in pending_tools.values():
        if tool["endTime"] is None:
            tool["endTime"] = end_ms
            if tool["startTime"] is not None and end_ms is not None:
                tool["durationMs"] = max(0, end_ms - tool["startTime"])
            tool["level"] = "ERROR"
            if end_ms is not None:
                last_tool_end = max(last_tool_end or 0, end_ms)

    for tool_use_id in tool_order:
        add(pending_tools[tool_use_id])

    usage = usage or {}

    # The final answer generation: after planning/tools, before the run ends.
    answer_start = first_text_at or last_tool_end or start_ms
    add(
        {
            "id": answer_id,
            "parentObservationId": root_id,
            "type": "GENERATION",
            "name": "answer",
            "model": model or None,
            "startTime": answer_start,
            "endTime": end_ms,
            "durationMs": (
                max(0, end_ms - answer_start)
                if end_ms is not None and answer_start is not None
                else latency_ms
            ),
            "level": "ERROR" if error_message else "DEFAULT",
            "statusMessage": error_message,
            "input": _clip(question),
            "output": _clip(answer),
            "usage": usage or None,
            "metadata": {"provider": provider} if provider else {},
        }
    )

    # The root span is the run itself; it sorts first and owns every stage.
    observations.insert(
        0,
        {
            "id": root_id,
            "parentObservationId": None,
            "type": "SPAN",
            "name": agent_name or agent_id or "run",
            "model": model or None,
            "startTime": start_ms,
            "endTime": end_ms,
            "durationMs": latency_ms,
            "level": "ERROR" if error_message else "DEFAULT",
            "statusMessage": None,
            "input": None,
            "output": None,
            "usage": usage or None,
            "metadata": {
                "kind": "run",
                "agentId": agent_id,
                "runId": run_id,
                "conversationId": conversation_id,
                "provider": provider,
                "tags": [str(tag) for tag in (tags or [])],
            },
        },
    )

    normalized_status = _normalize_status(status)
    return {
        "id": trace_id,
        "traceId": trace_id,
        "name": f"agent:{agent_name or agent_id or 'run'}",
        "userId": user_id,
        "sessionId": conversation_id,
        "conversationId": conversation_id,
        "runId": run_id,
        "agentId": agent_id,
        "agentName": agent_name,
        "model": model,
        "provider": provider,
        "tags": [str(tag) for tag in (tags or [])],
        "status": normalized_status,
        "level": "ERROR" if error_message else "DEFAULT",
        "statusMessage": error_message,
        "startedAt": started_at,
        "endedAt": ended_at,
        "latencyMs": latency_ms,
        "input": question,
        "output": answer,
        "usage": usage,
        "costMicroUsd": _cost_micro_usd(model, usage),
        "observationCount": len(observations),
        "createdAt": started_at,
        "observations": observations,
    }


def persist_trace(config: RuntimeConfig, user_id: str, trace: dict[str, Any]) -> None:
    """Write the full tree to S3 and the small index item to DynamoDB."""
    if not config.s3_bucket or not user_id or not trace:
        return
    trace_id = str(trace.get("traceId") or "")
    if not trace_id:
        return
    try:
        Storage().put_json(trace_key(user_id, trace_id), trace)
    except Exception as exc:  # noqa: BLE001 - never fail a run on the tree
        _warn("Trace tree write failed", exc)
    try:
        traces_repo.save_trace_index(user_id, trace)
    except Exception as exc:  # noqa: BLE001 - never fail a run on the index
        _warn("Trace index write failed", exc)


def local_now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)

"""Normalize Strands multi-agent events into the workflow SSE envelope.

Wire contract (consumed by the workflow builder and the chat screen):

    {"type": "node.started",   "nodeId", "nodeName", "agentName"}
    {"type": "node.handoff",   "from": [...], "to": [...], "message"}
    {"type": "node.completed", "nodeId", "status", "usage"}
    {"type": "node.stream",    "nodeId", "event": <normalized agent frame>}
    {"type": "run.completed",  "answer", "usage"}
    {"type": "run.error",      "message"}

Inner agent frames (text / tool.*) are nested under ``event`` so their ``type``
never collides with the outer workflow frame.
"""

from __future__ import annotations

from typing import Any

from agentflow.events import normalize_many
from agentflow.hitl import question_from_interrupt

# Inner frames forwarded from a node's agent stream.
_FORWARDED = {"text", "tool.start", "tool.input", "tool.stream", "tool.result"}


def _status(node_result: Any) -> str:
    status = getattr(node_result, "status", None)
    value = getattr(status, "value", None)
    return str(value or "completed")


def _usage(node_result: Any) -> dict[str, Any]:
    usage = getattr(node_result, "accumulated_usage", None)
    if not usage:
        return {}
    return {
        "inputTokens": getattr(usage, "inputTokens", None),
        "outputTokens": getattr(usage, "outputTokens", None),
        "totalTokens": getattr(usage, "totalTokens", None),
    }


def _node_meta(meta: dict[str, dict[str, Any]], node_id: str) -> dict[str, Any]:
    return meta.get(node_id) or {}


def normalize(
    event: Any, meta: dict[str, dict[str, Any]] | None = None
) -> list[dict[str, Any]]:
    """Turn one Strands multi-agent event into zero or more workflow frames."""
    if not isinstance(event, dict):
        return []
    meta = meta or {}
    etype = event.get("type")

    if etype == "multiagent_node_start":
        node_id = str(event.get("node_id") or "")
        info = _node_meta(meta, node_id)
        return [
            {
                "type": "node.started",
                "nodeId": node_id,
                "nodeName": info.get("agentName") or node_id,
                "agentName": info.get("agentName") or node_id,
            }
        ]

    if etype == "multiagent_node_stop":
        node_id = str(event.get("node_id") or "")
        node_result = event.get("node_result")
        return [
            {
                "type": "node.completed",
                "nodeId": node_id,
                "status": _status(node_result),
                "usage": _usage(node_result),
            }
        ]

    if etype == "multiagent_handoff":
        return [
            {
                "type": "node.handoff",
                "from": [str(item) for item in event.get("from_node_ids") or []],
                "to": [str(item) for item in event.get("to_node_ids") or []],
                "message": event.get("message"),
            }
        ]

    if etype == "multiagent_node_interrupt":
        node_id = str(event.get("node_id") or "")
        frames: list[dict[str, Any]] = []
        for interrupt in event.get("interrupts") or []:
            question = question_from_interrupt(interrupt)
            if not question:
                continue
            frames.append({"type": "question", "nodeId": node_id, **question})
        return frames

    if etype == "multiagent_node_stream":
        node_id = str(event.get("node_id") or "")
        inner = event.get("event") or {}
        frames: list[dict[str, Any]] = []
        for frame in normalize_many(inner):
            if frame.get("type") not in _FORWARDED:
                continue
            frames.append({"type": "node.stream", "nodeId": node_id, "event": frame})
        return frames

    return []

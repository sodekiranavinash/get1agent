"""Read OpenTelemetry traces back from AWS X-Ray.

The agent runtime / Lambdas **write** spans to X-Ray automatically (auto-
instrumentation + the ADOT collector). Those traces are private to the AWS
console, so this module pulls a trace by id with the caller's IAM role and
normalises it into a compact span tree the app can render publicly — no AWS
login for the viewer.

``xray:BatchGetTraces`` (and ``xray:GetTraceSummaries``) are required on the
calling role. Best-effort: any failure returns ``None`` so a trace page can fall
back to the stored run events.
"""

from __future__ import annotations

import json
import os
from typing import Any

_MAX_ATTRS = 40
_MAX_VALUE = 500


def _region(region: str | None = None) -> str:
    return (
        region
        or os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "ap-south-1"
    )


def _client(region: str | None = None) -> Any:
    import boto3

    return boto3.client("xray", region_name=_region(region))


def _flatten(values: Any) -> dict[str, Any]:
    """Keep only small scalar attribute values for the UI."""
    out: dict[str, Any] = {}
    if not isinstance(values, dict):
        return out
    for key, value in values.items():
        if len(out) >= _MAX_ATTRS or value is None:
            break
        if isinstance(value, (str, int, float, bool)):
            text = value if isinstance(value, str) else str(value)
            out[str(key)] = text[:_MAX_VALUE]
        elif isinstance(value, (list, tuple)):
            out[str(key)] = ", ".join(str(item) for item in value)[:_MAX_VALUE]
    return out


def _to_span(doc: dict[str, Any]) -> dict[str, Any]:
    start = doc.get("start_time")
    end = doc.get("end_time")
    duration = None
    try:
        if start is not None and end is not None:
            duration = int(round((float(end) - float(start)) * 1000))
    except (TypeError, ValueError):
        duration = None

    attributes: dict[str, Any] = {}
    metadata = doc.get("metadata")
    if isinstance(metadata, dict):
        attributes.update(_flatten(metadata.get("default")))
    attributes.update(_flatten(doc.get("annotations")))

    error = doc.get("error") or doc.get("fault") or doc.get("throttle")
    cause = doc.get("cause")
    message = None
    if isinstance(cause, dict):
        message = cause.get("exceptions") and "exception" in cause or cause.get("message")

    aws = doc.get("aws") if isinstance(doc.get("aws"), dict) else {}
    http = doc.get("http") if isinstance(doc.get("http"), dict) else {}

    return {
        "id": doc.get("id"),
        "traceId": doc.get("trace_id"),
        "parentId": doc.get("parent_id"),
        "name": doc.get("name") or "span",
        "startTime": start,
        "endTime": end,
        "durationMs": duration,
        "operation": aws.get("operation"),
        "status": "error" if error else "ok",
        "message": str(message)[:400] if message else None,
        "attributes": attributes,
        "children": [
            _to_span(sub)
            for sub in (doc.get("subsegments") or [])
            if isinstance(sub, dict)
        ],
    }


def _candidate_ids(trace_id: str) -> list[str]:
    """X-Ray accepts the dashed ``1-xxxxxxxx-…`` id; also try the raw 32-hex."""
    candidates = [trace_id]
    hex32 = trace_id.replace("-", "").lower()
    if len(hex32) == 32 and all(ch in "0123456789abcdef" for ch in hex32):
        dashed = f"1-{hex32[:8]}-{hex32[8:]}"
        if dashed != trace_id:
            candidates.append(dashed)
    return candidates


def get_trace(trace_id: str, region: str | None = None) -> dict[str, Any] | None:
    """Return a normalised span tree for ``trace_id``, or ``None``.

    Shape: ``{ traceId, durationMs, spans: [Span] }`` where each Span has
    ``name, durationMs, status, attributes, children``.
    """
    trace_id = (trace_id or "").strip()
    if not trace_id:
        return None

    client = None
    trace = None
    for candidate in _candidate_ids(trace_id):
        try:
            if client is None:
                client = _client(region)
            traces = client.batch_get_traces(TraceIds=[candidate]).get("Traces") or []
        except Exception:  # noqa: BLE001 - a missing trace must not break the page
            traces = []
        if traces:
            trace = traces[0]
            break
    if trace is None:
        return None

    documents: list[dict[str, Any]] = []
    for segment in trace.get("Segments") or []:
        doc = segment.get("Document") if isinstance(segment, dict) else None
        try:
            parsed = json.loads(doc) if isinstance(doc, str) else doc
        except (TypeError, ValueError):
            continue
        if isinstance(parsed, dict):
            documents.append(parsed)

    # X-Ray returns each span as its own segment document (flat) linked by
    # ``parent_id``; assemble them into a tree.
    nodes: dict[str, dict[str, Any]] = {}
    order: list[dict[str, Any]] = []
    for doc in documents:
        node = _to_span(doc)
        node["children"] = []
        nodes[str(node.get("id"))] = node
        order.append(node)

    roots: list[dict[str, Any]] = []
    for node in order:
        parent = node.get("parentId")
        parent_node = nodes.get(str(parent)) if parent else None
        if parent_node is not None and parent_node is not node:
            parent_node["children"].append(node)
        else:
            roots.append(node)

    duration = None
    try:
        duration = int(round(float(trace.get("Duration") or 0) * 1000))
    except (TypeError, ValueError):
        duration = None
    return {"traceId": trace_id, "durationMs": duration, "spans": roots}


# --- Langfuse-style observations from an X-Ray span tree ---------------------
#
# X-Ray annotations arrive with an app prefix (``get1agent.*``). Raw keys are
# meaningless to an end user, so we lift the known ones into the observation's
# name / input / output / metadata and humanise the rest before the UI sees it.

_PREFIX = "get1agent."
# Keys we surface as first-class fields rather than metadata.
_RESERVED = ("trace_name", "input", "output", "metadata", "session_id", "user_id", "tags")


def _attrs(span: dict[str, Any]) -> dict[str, Any]:
    attributes = span.get("attributes")
    return attributes if isinstance(attributes, dict) else {}


def _tag(span: dict[str, Any], key: str) -> Any:
    return _attrs(span).get(f"{_PREFIX}{key}")


def _infer_type(label: str, has_output: bool) -> str:
    lowered = label.lower()
    # Tool spans are named ``execute_tool <name>`` by the instrumentation, but
    # the app tag can override the display name, so we test the combined label.
    if "tool" in lowered:
        return "TOOL"
    if lowered.startswith("agent:") or has_output:
        return "GENERATION"
    return "SPAN"


def _to_observation(span: dict[str, Any], parent_id: str | None) -> dict[str, Any]:
    attributes = _attrs(span)
    raw_name = str(span.get("name") or "")
    name = str(_tag(span, "trace_name") or raw_name or "span")
    output = _tag(span, "output")
    metadata: dict[str, Any] = {}
    raw_metadata = _tag(span, "metadata")
    if isinstance(raw_metadata, str):
        try:
            parsed = json.loads(raw_metadata)
            if isinstance(parsed, dict):
                metadata.update(parsed)
        except (TypeError, ValueError):
            pass
    elif isinstance(raw_metadata, dict):
        metadata.update(raw_metadata)
    for key in ("session_id", "user_id", "tags"):
        value = _tag(span, key)
        if value not in (None, ""):
            metadata[key] = value
    leftover = {key: value for key, value in attributes.items() if not key.startswith(_PREFIX)}
    if leftover:
        metadata["attributes"] = leftover

    start = span.get("startTime")
    end = span.get("endTime")
    return {
        "id": str(span.get("id") or name),
        "parentObservationId": parent_id,
        "type": _infer_type(f"{name} {raw_name}", output is not None),
        "name": name,
        "model": metadata.get("model") or attributes.get("gen_ai.request.model"),
        "startTime": int(start * 1000) if isinstance(start, (int, float)) else None,
        "endTime": int(end * 1000) if isinstance(end, (int, float)) else None,
        "durationMs": span.get("durationMs"),
        "level": "ERROR" if span.get("status") == "error" else "DEFAULT",
        "statusMessage": span.get("message"),
        "input": _tag(span, "input"),
        "output": output,
        "usage": None,
        "metadata": metadata,
    }


def to_observations(trace: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten an X-Ray span tree into Langfuse-style observations."""
    observations: list[dict[str, Any]] = []

    def walk(span: dict[str, Any], parent_id: str | None) -> None:
        if len(observations) >= 400:
            return
        observation = _to_observation(span, parent_id)
        observations.append(observation)
        for child in span.get("children") or []:
            if isinstance(child, dict):
                walk(child, observation["id"])

    for root in trace.get("spans") or []:
        if isinstance(root, dict):
            walk(root, None)
    return observations


def get_observations(
    trace_id: str, region: str | None = None
) -> dict[str, Any] | None:
    """Observations (not raw spans) for a trace, or ``None`` when unavailable."""
    trace = get_trace(trace_id, region)
    if not trace:
        return None
    observations = to_observations(trace)
    if not observations:
        return None
    # The root generation carries the run name when the app tagged it.
    name = str(observations[0].get("name") or "agent run")
    return {
        "traceId": trace_id,
        "id": trace_id,
        "name": name,
        "durationMs": trace.get("durationMs"),
        "latencyMs": trace.get("durationMs"),
        "observations": observations,
    }

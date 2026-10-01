"""Langfuse-native client for the evaluation lab.

Datasets and dataset items live in Langfuse (the source of truth for curated
test cases); each evaluated case is ingested as a real **Langfuse experiment**
item using the documented OpenTelemetry experiment attributes (OTLP/HTTP), with
its metric scores attached to the item trace. Everything is namespaced
``u_<userId>/<name>`` so a single shared project cannot leak across users.

All calls use stdlib ``urllib`` (no SDK/layer); experiment ingestion is
best-effort so a run never fails because Langfuse is unavailable.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


class LangfuseError(Exception):
    """A Langfuse call failed or the client is not configured."""


def configured() -> bool:
    return bool(
        (os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip()
        and (os.environ.get("LANGFUSE_SECRET_KEY") or "").strip()
    )


def _base_token() -> tuple[str, str]:
    public_key = (os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip()
    secret_key = (os.environ.get("LANGFUSE_SECRET_KEY") or "").strip()
    if not (public_key and secret_key):
        raise LangfuseError("Langfuse is not configured")
    base = (
        os.environ.get("LANGFUSE_BASE_URL")
        or os.environ.get("LANGFUSE_HOST")
        or "https://cloud.langfuse.com"
    ).strip()
    parsed = urllib.parse.urlsplit(base)
    if parsed.hostname and parsed.hostname.endswith("langfuse.com"):
        base = f"{parsed.scheme}://{parsed.netloc}"
    else:
        for marker in ("/project/", "/api"):
            index = base.find(marker)
            if index > 0:
                base = base[:index]
    base = base.rstrip("/")
    token = base64.b64encode(f"{public_key}:{secret_key}".encode()).decode()
    return base, token


def _post(url: str, token: str, payload: Any, timeout: int) -> Any:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={
            "authorization": f"Basic {token}",
            "content-type": "application/json",
            "accept": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    try:
        return json.loads(raw or b"{}")
    except ValueError:
        return {}


def request(method: str, path: str, payload: Any = None, *, timeout: int = 10) -> Any:
    """Call a Langfuse public API path (``/api/public`` prefix added)."""
    base, token = _base_token()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        f"{base}/api/public{path}",
        data=data,
        headers={
            "authorization": f"Basic {token}",
            "content-type": "application/json",
            "accept": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        if detail.lstrip().lower().startswith(("<!doctype", "<html")):
            raise LangfuseError(
                "Langfuse returned an HTML page — LANGFUSE_BASE_URL must be the "
                "bare API host (e.g. https://us.cloud.langfuse.com)"
            ) from exc
        raise LangfuseError(f"Langfuse error ({exc.code}): {detail}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LangfuseError("Langfuse is unreachable") from exc
    try:
        return json.loads(raw or b"{}")
    except ValueError as exc:
        raise LangfuseError("Langfuse returned an invalid response") from exc


# --- namespacing -------------------------------------------------------------


def full_name(sub: str, name: str) -> str:
    return f"u_{sub}/{name}"


def display_name(sub: str, name: str) -> str:
    prefix = f"u_{sub}/"
    return name[len(prefix) :] if name.startswith(prefix) else name


# --- datasets ----------------------------------------------------------------


def list_datasets() -> list[dict[str, Any]]:
    return request("GET", "/datasets?limit=100").get("data") or []


def get_dataset(name: str) -> dict[str, Any]:
    return request("GET", f"/datasets/{urllib.parse.quote(name, safe='')}")


def create_dataset(name: str, description: str = "") -> dict[str, Any]:
    return request("POST", "/datasets", {"name": name, "description": description})


def delete_dataset(name: str) -> None:
    request("DELETE", f"/datasets/{urllib.parse.quote(name, safe='')}")


def list_dataset_items(name: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {"datasetName": name, "limit": 50, "page": page}
        )
        payload = request("GET", f"/dataset-items?{query}")
        items.extend(payload.get("data") or [])
        meta = payload.get("meta") or {}
        total_pages = meta.get("totalPages") or 1
        if page >= total_pages:
            break
        page += 1
    return items


def create_dataset_item(
    *,
    dataset_name: str,
    input_value: Any,
    expected_output: Any = None,
    metadata: dict[str, Any] | None = None,
    source_trace_id: str | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"datasetName": dataset_name, "input": input_value}
    if item_id:
        payload["id"] = item_id
    if expected_output not in (None, ""):
        payload["expectedOutput"] = expected_output
    if metadata:
        payload["metadata"] = metadata
    if source_trace_id:
        payload["sourceTraceId"] = source_trace_id
    return request("POST", "/dataset-items", payload)


def delete_dataset_item(item_id: str) -> None:
    request("DELETE", f"/dataset-items/{urllib.parse.quote(item_id, safe='')}")


def list_dataset_runs(name: str) -> list[dict[str, Any]]:
    query = urllib.parse.urlencode({"limit": 50})
    payload = request(
        "GET", f"/datasets/{urllib.parse.quote(name, safe='')}/runs?{query}"
    )
    return payload.get("data") or []


# --- experiment ingestion (OTLP) --------------------------------------------


def _attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, (int, float)):
        return {"key": key, "value": {"doubleValue": float(value)}}
    return {"key": key, "value": {"stringValue": str(value)}}


def _json(value: Any) -> str:
    try:
        return json.dumps(value, default=str)
    except (TypeError, ValueError):
        return json.dumps(str(value))


def _numeric(metrics: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for name, value in (metrics or {}).items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        out[name] = float(value)
    return out


def _otlp_payload(
    *,
    trace_id: str,
    span_id: str,
    span_name: str,
    start_ns: int,
    end_ns: int,
    attributes: list[dict[str, Any]],
    user_id: str,
) -> dict[str, Any]:
    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attr("service.name", "get1agent-evals"),
                        _attr("langfuse.environment", "eval"),
                        _attr("user.id", user_id),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "get1agent-evals", "version": "1.0.0"},
                        "spans": [
                            {
                                "traceId": trace_id,
                                "spanId": span_id,
                                "name": span_name,
                                "kind": 1,
                                "startTimeUnixNano": str(start_ns),
                                "endTimeUnixNano": str(end_ns),
                                "attributes": attributes,
                                "status": {"code": 1},
                            }
                        ],
                    }
                ],
            }
        ]
    }


def _post_otlp(payload: dict[str, Any], *, timeout: int = 15) -> None:
    base, token = _base_token()
    _post(f"{base}/api/public/otel/v1/traces", token, payload, timeout)


def emit_experiment_item(
    *,
    user_id: str,
    experiment_id: str,
    experiment_name: str,
    experiment_description: str,
    dataset_id: str,
    item_id: str,
    item_input: Any,
    item_output: Any,
    expected_output: Any,
    metrics: dict[str, Any],
    reasoning: str = "",
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Ingest one experiment item as a trace + attach its scores.

    Best-effort: returns the trace id on success, ``None`` on any failure.
    """
    if not configured():
        return None
    trace_id = uuid.uuid5(
        uuid.NAMESPACE_URL, f"get1agent:experiment:{experiment_id}:{item_id}"
    ).hex
    span_id = uuid.uuid4().hex[:16]
    start_ns = time.time_ns()
    attributes = [
        _attr("langfuse.trace.name", experiment_name),
        _attr("langfuse.experiment.id", experiment_id),
        _attr("langfuse.experiment.name", experiment_name),
        _attr("langfuse.experiment.dataset.id", dataset_id),
        _attr("langfuse.experiment.description", experiment_description),
        _attr("langfuse.experiment.item.id", item_id),
        _attr("langfuse.experiment.item.root_observation_id", span_id),
        _attr("langfuse.observation.input", _json(item_input)),
        _attr("langfuse.observation.output", _json(item_output)),
    ]
    if expected_output not in (None, ""):
        attributes.append(
            _attr("langfuse.experiment.item.expected_output", _json(expected_output))
        )
    for key, value in (metadata or {}).items():
        attributes.append(_attr(f"langfuse.experiment.item.metadata.{key}", value))

    try:
        _post_otlp(
            _otlp_payload(
                trace_id=trace_id,
                span_id=span_id,
                span_name="experiment-item",
                start_ns=start_ns,
                end_ns=time.time_ns(),
                attributes=attributes,
                user_id=user_id,
            )
        )
    except Exception as exc:  # noqa: BLE001 - ingestion is best-effort
        print(f"langfuse OTLP experiment ingest failed: {exc!r}", file=sys.stderr)
        return None

    for name, value in _numeric(metrics).items():
        try:
            request(
                "POST",
                "/scores",
                {
                    "id": str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL,
                            f"get1agent:experiment-score:{experiment_id}:{item_id}:{name}",
                        )
                    ),
                    "traceId": trace_id,
                    "observationId": span_id,
                    "name": f"eval_{name}",
                    "value": value,
                    "comment": reasoning[:500] or None,
                },
            )
        except Exception as exc:  # noqa: BLE001 - scores are best-effort
            print(f"langfuse experiment score failed: {exc!r}", file=sys.stderr)
    return trace_id

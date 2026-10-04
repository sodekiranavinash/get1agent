"""AWS-native evaluation Lab store (DynamoDB + existing S3 artifacts).

Provides two surfaces:

* the dataset/case helpers used by the ``/v1/evals`` handlers (same shapes the
  handlers already expect), and
* :func:`lab_request`, which serves the ``/v1/lab`` handlers (datasets,
  dataset-items, annotation queues, score configs, scores, traces and metrics).

Everything is stored in the shared ``get1agent`` DynamoDB table under ``LAB#``
partitions; traces are read back from the user's stored conversations.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlsplit

from data import client as ddb

_LAB = "LAB"
_DATASETS = f"{_LAB}#DATASETS"
_CASES = f"{_LAB}#CASES"
_QUEUES = f"{_LAB}#QUEUES"
_SCORECONFIGS = f"{_LAB}#SCORECONFIGS"
_SCORES = f"{_LAB}#SCORES"
_QITEMS = f"{_LAB}#QITEMS"
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


class StoreError(RuntimeError):
    """A Lab store operation failed."""


def configured() -> bool:
    """The Lab store is always available (DynamoDB-backed)."""
    return True


def full_name(sub: str, name: str) -> str:
    return f"u_{sub}/{name}"


def display_name(sub: str, name: str) -> str:
    prefix = f"u_{sub}/"
    return name[len(prefix):] if name.startswith(prefix) else name


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table() -> Any:
    return ddb.table()


def _put(pk: str, sk: str, **attrs: Any) -> None:
    item = {"pk": pk, "sk": sk, **attrs}
    try:
        _table().put_item(Item=item)
    except Exception as exc:  # noqa: BLE001
        raise StoreError(f"store write failed: {exc}") from exc


def _get(pk: str, sk: str) -> dict[str, Any] | None:
    try:
        return _table().get_item(Key={"pk": pk, "sk": sk}).get("Item")
    except Exception as exc:  # noqa: BLE001
        raise StoreError(f"store read failed: {exc}") from exc


def _delete(pk: str, sk: str) -> None:
    try:
        _table().delete_item(Key={"pk": pk, "sk": sk})
    except Exception as exc:  # noqa: BLE001
        raise StoreError(f"store delete failed: {exc}") from exc


def _query(pk: str, sk_prefix: str = "") -> list[dict[str, Any]]:
    from boto3.dynamodb.conditions import Key

    try:
        if sk_prefix:
            response = _table().query(
                KeyConditionExpression=Key("pk").eq(pk)
                & Key("sk").begins_with(sk_prefix)
            )
        else:
            response = _table().query(KeyConditionExpression=Key("pk").eq(pk))
    except Exception:  # noqa: BLE001
        return []
    return response.get("Items") or []


def _safe(value: str) -> str:
    return _SAFE.sub("_", str(value or ""))[:120]


def _as_number(value: Any) -> float | None:
    """Coerce a DynamoDB number (``Decimal``) to a float, or None."""
    try:
        if isinstance(value, bool):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


# --- datasets + cases ---------------------------------------------------------


def _dataset_item(sub: str, short: str) -> dict[str, Any] | None:
    return _get(_DATASETS, full_name(sub, short))


def list_datasets() -> list[dict[str, Any]]:
    return [
        {
            "name": item["sk"],
            "description": item.get("description") or "",
            "createdAt": item.get("createdAt"),
            "updatedAt": item.get("updatedAt"),
            "itemCount": int(item.get("itemCount") or 0),
        }
        for item in _query(_DATASETS)
    ]


def get_dataset(name: str) -> dict[str, Any]:
    item = _get(_DATASETS, name)
    if item is None:
        raise StoreError("Dataset not found")
    return {
        "name": item["sk"],
        "description": item.get("description") or "",
        "createdAt": item.get("createdAt"),
        "itemCount": int(item.get("itemCount") or 0),
    }


def create_dataset(name: str, description: str = "") -> dict[str, Any]:
    if not name:
        raise StoreError("Dataset name is required")
    now = _now_iso()
    _put(
        _DATASETS,
        name,
        description=description or "",
        createdAt=now,
        updatedAt=now,
        itemCount=0,
    )
    return {"name": name, "description": description or "", "createdAt": now}


def delete_dataset(name: str) -> None:
    _delete(_DATASETS, name)
    for item in _query(_CASES, f"{name}#"):
        _delete(_CASES, item["sk"])


def list_dataset_items(name: str) -> list[dict[str, Any]]:
    items = _query(_CASES, f"{name}#")
    return [_case_shape(item) for item in items]


def _case_shape(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("caseId"),
        "datasetName": item.get("datasetName"),
        "input": item.get("input"),
        "expectedOutput": item.get("expectedOutput"),
        "metadata": item.get("metadata") or {},
        "sourceTraceId": item.get("sourceTraceId"),
        "createdAt": item.get("createdAt"),
    }


def create_dataset_item(
    *,
    dataset_name: str,
    input_value: Any,
    expected_output: Any = None,
    metadata: dict[str, Any] | None = None,
    source_trace_id: str | None = None,
    item_id: str | None = None,
) -> dict[str, Any]:
    case_id = item_id or str(uuid.uuid4())
    _put(
        _CASES,
        f"{dataset_name}#{case_id}",
        datasetName=dataset_name,
        caseId=case_id,
        input=input_value,
        expectedOutput=expected_output or "",
        metadata=metadata or {},
        sourceTraceId=source_trace_id,
        createdAt=_now_iso(),
    )
    _bump_item_count(dataset_name, 1)
    return {
        "id": case_id,
        "datasetName": dataset_name,
        "input": input_value,
        "expectedOutput": expected_output or "",
        "metadata": metadata or {},
        "sourceTraceId": source_trace_id,
    }


def delete_dataset_item(item_id: str) -> None:
    for item in _query(_CASES):
        if item.get("caseId") == item_id:
            _delete(_CASES, item["sk"])
            _bump_item_count(str(item.get("datasetName") or ""), -1)
            return


def _bump_item_count(dataset_name: str, delta: int) -> None:
    item = _get(_DATASETS, dataset_name)
    if item is None:
        return
    count = max(0, int(item.get("itemCount") or 0) + delta)
    _put(
        _DATASETS,
        dataset_name,
        description=item.get("description") or "",
        createdAt=item.get("createdAt") or _now_iso(),
        updatedAt=_now_iso(),
        itemCount=count,
    )


def list_dataset_runs(name: str) -> list[dict[str, Any]]:
    from data.repositories import evals as evals_repo

    try:
        runs, _ = evals_repo.list_runs("", limit=50)
    except Exception:  # noqa: BLE001
        runs = []
    return [
        run
        for run in runs
        if str((run.get("config") or {}).get("datasetName") or "") == name
    ]


def emit_experiment_item(*_args: Any, **_kwargs: Any) -> None:
    """No-op: per-case results + artifacts are persisted by the runner itself."""
    return None


# --- queues / scores ----------------------------------------------------------


def _queue_shape(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("queueId"),
        "name": item.get("name"),
        "description": item.get("description") or "",
        "scoreConfigIds": item.get("scoreConfigIds") or [],
    }


def _score_config_shape(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": item.get("configId"),
        "name": item.get("name"),
        "dataType": item.get("dataType"),
        "categories": item.get("categories") or [],
        "minValue": item.get("minValue"),
        "maxValue": item.get("maxValue"),
    }


def _create_queue(name: str, description: str, score_config_ids: list[str]) -> dict[str, Any]:
    queue_id = str(uuid.uuid4())
    _put(
        _QUEUES,
        queue_id,
        queueId=queue_id,
        name=name,
        description=description,
        scoreConfigIds=score_config_ids,
        createdAt=_now_iso(),
    )
    return {"id": queue_id, "name": name, "description": description, "scoreConfigIds": score_config_ids}


def _create_score_config(payload: dict[str, Any]) -> dict[str, Any]:
    config_id = str(uuid.uuid4())
    _put(
        _SCORECONFIGS,
        config_id,
        configId=config_id,
        name=payload.get("name"),
        dataType=str(payload.get("dataType") or "NUMERIC").upper(),
        categories=payload.get("categories") or [],
        minValue=payload.get("minValue"),
        maxValue=payload.get("maxValue"),
        createdAt=_now_iso(),
    )
    return {"id": config_id, **payload}


def _put_score(payload: dict[str, Any]) -> dict[str, Any]:
    trace_id = str(payload.get("traceId") or "")
    name = str(payload.get("name") or "")
    if not trace_id or not name:
        raise StoreError("A score needs traceId and name")
    _put(
        _SCORES,
        f"{_safe(trace_id)}#{_safe(name)}",
        traceId=trace_id,
        name=name,
        value=payload.get("value"),
        stringValue=payload.get("stringValue"),
        comment=payload.get("comment"),
        configId=payload.get("configId"),
        createdAt=_now_iso(),
    )
    return {"ok": True}


def delete_user(sub: str) -> int:
    """Delete all Lab data owned by ``sub`` (erasure). Returns items removed."""
    prefix = f"u_{sub}/"
    removed = 0
    for pk, sk_prefix in (
        (_CASES, prefix),
        (_DATASETS, prefix),
    ):
        for item in _query(pk, sk_prefix):
            _delete(pk, item["sk"])
            removed += 1
    # Queues / configs / scores are identified elsewhere; best-effort by name.
    for item in list(_query(_QUEUES)) + list(_query(_SCORECONFIGS)):
        name = str(item.get("name") or "")
        if name.startswith(prefix):
            _delete(_QUEUES if item.get("queueId") else _SCORECONFIGS, item["sk"])
            removed += 1
    return removed


# --- traces (Langfuse-style store) --------------------------------------------


def _trace_summary(item: dict[str, Any]) -> dict[str, Any]:
    """Shape a trace index item (or conversation fallback) for the list UI."""
    trace_id = item.get("traceId") or item.get("id")
    latency_ms = _as_number(item.get("latencyMs"))
    return {
        "id": trace_id,
        "traceId": trace_id,
        "name": str(item.get("name") or "agent run"),
        "userId": item.get("userId"),
        "timestamp": item.get("startedAt") or item.get("timestamp") or item.get("createdAt"),
        "sessionId": item.get("sessionId"),
        "conversationId": item.get("conversationId"),
        "agentId": item.get("agentId"),
        "agentName": item.get("agentName"),
        "model": item.get("model"),
        "status": str(item.get("status") or "ok"),
        "level": str(item.get("level") or "DEFAULT"),
        "latency": (
            float(latency_ms) / 1000.0
            if latency_ms is not None
            else None
        ),
        "latencyMs": latency_ms,
        "tags": item.get("tags") or [],
        "input": {"question": item.get("inputPreview") or item.get("input") or ""},
        "output": item.get("outputPreview") or item.get("output") or "",
        "usage": item.get("usage") or {},
        "costMicroUsd": int(item.get("costMicroUsd") or 0),
        "observationCount": int(item.get("observationCount") or 0),
    }


def list_traces(
    user_id: str,
    *,
    limit: int = 25,
    cursor: str | None = None,
    agent_id: str | None = None,
) -> tuple[list[dict[str, Any]], str | None]:
    """Newest-first traces from the AWS-native trace store."""
    from data.repositories import traces as traces_repo

    items, next_cursor = traces_repo.list_traces(
        user_id, limit=limit, cursor=cursor, agent_id=agent_id
    )
    return [_trace_summary(item) for item in items], next_cursor


def _conversation_traces(
    user_id: str, limit: int, page: int = 1
) -> list[dict[str, Any]]:
    """Legacy fallback: derive a trace list from stored conversations.

    Only used before a user has runs in the trace store (old transcripts), so
    the page is never empty right after deploy.
    """
    from data.repositories import conversations as conv_repo

    try:
        conversations, _ = conv_repo.list_conversations(user_id, limit=200)
    except Exception:  # noqa: BLE001
        conversations = []
    traces: list[dict[str, Any]] = []
    for conversation in conversations:
        trace_id = conversation.get("lastTraceId")
        if not trace_id:
            continue
        traces.append(
            _trace_summary(
                {
                    "traceId": trace_id,
                    "id": trace_id,
                    "name": str(conversation.get("title") or "agent run"),
                    "userId": user_id,
                    "startedAt": conversation.get("updatedAt")
                    or conversation.get("createdAt"),
                    "sessionId": str(conversation.get("conversationId") or ""),
                    "conversationId": conversation.get("conversationId"),
                    "agentId": conversation.get("agentId"),
                    "agentName": conversation.get("agentName"),
                    "tags": [str(conversation.get("targetType") or "agent")],
                    "inputPreview": "",
                    "outputPreview": str(conversation.get("preview") or ""),
                }
            )
        )
    start = max(0, (page - 1) * limit)
    return traces[start : start + limit]


def _xray_observations(trace_id: str) -> dict[str, Any] | None:
    """Best-effort observation tree from the observability backend (X-Ray)."""
    try:
        from core import xray

        return xray.get_observations(trace_id)
    except Exception:  # noqa: BLE001 - observability is optional
        return None


def read_trace(user_id: str, trace_id: str) -> dict[str, Any]:
    """Full trace tree from S3, falling back to the index then X-Ray.

    Older runs (before the trace store existed) never wrote an S3 tree, so we
    convert their X-Ray spans into the same observation shape — the UI never has
    to understand raw span attributes.
    """
    from core.storage import Storage
    from retrieval.layout import trace_key

    try:
        data = Storage().get_json(trace_key(user_id, str(trace_id)))
    except Exception:  # noqa: BLE001 - a missing object is a store miss
        data = None
    if isinstance(data, dict) and data.get("observations"):
        return data

    from data.repositories import traces as traces_repo

    item = traces_repo.get_trace_index(user_id, str(trace_id))
    if item is None:
        # Not in the store at all: the id may still resolve in the observability
        # backend (e.g. a trace recorded before the store shipped).
        fallback = _xray_observations(str(trace_id))
        if fallback:
            return fallback
        raise StoreError("Trace not found")

    summary = _trace_summary(item)
    if not summary.get("observations"):
        fallback = _xray_observations(str(trace_id))
        if fallback and fallback.get("observations"):
            summary["observations"] = fallback["observations"]
    return summary


def trace_detail(user_id: str, trace_id: str) -> dict[str, Any]:
    """Public trace-detail lookup scoped to the owning user."""
    return read_trace(user_id, trace_id)


# --- metrics (from usage + conversations + scores) ----------------------------


def _metrics(user_id: str, days: int) -> dict[str, Any]:
    from core import usage as usage_mod
    from data.repositories import conversations as conv_repo

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    try:
        conversations, _ = conv_repo.list_conversations(user_id, limit=500)
    except Exception:  # noqa: BLE001
        conversations = []
    recent = [
        c
        for c in conversations
        if str(c.get("updatedAt") or c.get("createdAt") or "") >= start.isoformat()
    ]

    # Daily counts.
    by_day: dict[str, int] = {}
    for conversation in recent:
        stamp = str(conversation.get("updatedAt") or conversation.get("createdAt") or "")[:10]
        by_day[stamp] = by_day.get(stamp, 0) + 1
    series = sorted(
        (
            {"time_dimension": day, "count_count": count, "p95_latency": 0.0, "sum_totalCost": 0.0}
            for day, count in by_day.items()
        ),
        key=lambda row: row["time_dimension"],
    )

    try:
        budget = usage_mod.get_budget(user_id)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        budget = {}
    cost = round(float(budget.get("spentMicroUsd") or 0) / 1_000_000, 6)
    tokens = int(budget.get("platformTokensIn") or 0) + int(budget.get("platformTokensOut") or 0)

    # Scores: average per name.
    score_rows: dict[str, list[float]] = {}
    for item in _query(_SCORES):
        if item.get("traceId") is None:
            continue
        value = item.get("value")
        if isinstance(value, (int, float)):
            score_rows.setdefault(str(item.get("name") or ""), []).append(float(value))
    scores = [
        {
            "name": name,
            "avg_value": round(sum(values) / len(values), 4),
            "count_count": len(values),
        }
        for name, values in score_rows.items()
        if values
    ]

    return {
        "totals": {
            "count_count": len(recent),
            "avg_latency": 0.0,
            "p95_latency": 0.0,
            "sum_totalCost": cost,
            "sum_totalTokens": tokens,
        },
        "series": series,
        "scores": scores,
        "models": [],
    }


# --- lab_request: the REST subset the /v1/lab handlers call -------------------


def _query_param(path: str, key: str) -> str:
    query = urlsplit(path).query
    values = parse_qs(query).get(key) or []
    return values[0] if values else ""


def _user_from_metrics_query(path: str) -> str:
    raw = _query_param(path, "query")
    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return ""
    for entry in payload.get("filters") or []:
        if isinstance(entry, dict) and entry.get("column") == "userId":
            return str(entry.get("value") or "")
    return ""


def lab_request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    payload = payload or {}
    clean = urlsplit(path).path

    # datasets
    if clean == "/datasets" and method == "GET":
        return {"data": list_datasets()}
    if clean == "/datasets" and method == "POST":
        return create_dataset(str(payload.get("name") or ""), str(payload.get("description") or ""))
    if clean.startswith("/datasets/"):
        name = clean[len("/datasets/") :]
        if method == "GET":
            return get_dataset(name)
        if method == "DELETE":
            delete_dataset(name)
            return {"ok": True}

    # dataset items
    if clean == "/dataset-items" and method == "GET":
        name = _query_param(path, "datasetName")
        return {"data": list_dataset_items(name)}
    if clean == "/dataset-items" and method == "POST":
        item = create_dataset_item(
            dataset_name=str(payload.get("datasetName") or ""),
            input_value=payload.get("input"),
            expected_output=payload.get("expectedOutput"),
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
            source_trace_id=payload.get("sourceTraceId"),
            item_id=payload.get("id"),
        )
        return item
    if clean.startswith("/dataset-items/") and method == "DELETE":
        delete_dataset_item(clean[len("/dataset-items/") :])
        return {"ok": True}

    # annotation queues
    if clean == "/annotation-queues" and method == "GET":
        return {"data": [_queue_shape(item) for item in _query(_QUEUES)]}
    if clean == "/annotation-queues" and method == "POST":
        return _create_queue(
            str(payload.get("name") or ""),
            str(payload.get("description") or ""),
            list(payload.get("scoreConfigIds") or []),
        )
    if clean.startswith("/annotation-queues/"):
        rest = clean[len("/annotation-queues/") :].split("/")
        queue_id = rest[0]
        if len(rest) == 2 and rest[1] == "items" and method == "POST":
            item_id = str(uuid.uuid4())
            _put(
                f"{_QITEMS}#{_safe(queue_id)}",
                item_id,
                itemId=item_id,
                queueId=queue_id,
                objectId=payload.get("objectId"),
                objectType=payload.get("objectType"),
                status="PENDING",
                createdAt=_now_iso(),
            )
            return {"id": item_id}
        if len(rest) == 2 and rest[1] == "items" and method == "GET":
            items = _query(f"{_QITEMS}#{_safe(queue_id)}")
            status = _query_param(path, "status")
            if status:
                items = [item for item in items if item.get("status") == status]
            return {"data": items}
        if len(rest) == 3 and rest[1] == "items":
            item_id = rest[2]
            if method == "GET":
                item = _get(f"{_QITEMS}#{_safe(queue_id)}", item_id)
                if item is None:
                    raise StoreError("Queue item not found")
                return item
            if method == "PATCH":
                existing = _get(f"{_QITEMS}#{_safe(queue_id)}", item_id) or {}
                _put(
                    f"{_QITEMS}#{_safe(queue_id)}",
                    item_id,
                    itemId=item_id,
                    queueId=queue_id,
                    objectId=existing.get("objectId"),
                    objectType=existing.get("objectType"),
                    status=str(payload.get("status") or existing.get("status") or "PENDING"),
                    createdAt=existing.get("createdAt") or _now_iso(),
                )
                return {"ok": True}

    # score configs
    if clean == "/score-configs" and method == "GET":
        return {"data": [_score_config_shape(item) for item in _query(_SCORECONFIGS)]}
    if clean == "/score-configs" and method == "POST":
        return _create_score_config(payload)

    # scores
    if clean == "/scores" and method == "POST":
        return _put_score(payload)

    # traces
    if clean in ("/traces", "/v2/traces") and method == "GET":
        user_id = _query_param(path, "userId")
        limit = int(_query_param(path, "limit") or 25)
        page = int(_query_param(path, "page") or 1)
        cursor = _query_param(path, "cursor") or None
        agent_id = _query_param(path, "agentId") or None
        if user_id:
            try:
                traces, next_cursor = list_traces(
                    user_id, limit=limit, cursor=cursor, agent_id=agent_id
                )
            except Exception:  # noqa: BLE001 - an empty store is not an error
                traces, next_cursor = [], None
            # Old transcripts predate the trace store: fall back so the page is
            # never empty right after deploy.
            if not traces and not cursor and not agent_id:
                traces = _conversation_traces(user_id, limit, page)
            return {"data": traces, "meta": {"cursor": next_cursor}}
        return {"data": _conversation_traces(user_id, limit, page), "meta": {"cursor": None}}
    if clean.startswith("/traces/") and method == "GET":
        trace_id = clean[len("/traces/") :]
        user_id = _query_param(path, "userId")
        if not user_id:
            raise StoreError("Trace detail requires an owner")
        return trace_detail(user_id, trace_id)

    # metrics
    if clean == "/v2/metrics" and method == "GET":
        return _metrics(_user_from_metrics_query(path), int(_query_param(path, "days") or 7))

    raise StoreError(f"Unsupported lab path: {method} {path}")

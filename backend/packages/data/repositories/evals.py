"""Evaluation runs: bookkeeping for AWS-native experiments.

Curated datasets and their items live in the LAB# DynamoDB partition (see
``src.evals.store``); the runner persists each evaluated case result itself
as an experiment item. This repository keeps only what the UI needs to be fast
and reliable: one small **run** item (``USER#<userId>`` / ``EVALRUN#<runId>``)
with the config, status and aggregate metrics, and one tiny **case result** per
case (``EVALRUN#<runId>`` / ``CASE#<caseId>``). The bulky artifact (retrieved
contexts, generated answer, judge reasoning) lives in S3
(``retrieval.layout.eval_case_key``).

Access patterns:

* by id (owner)      GetItem on the user's partition (strong)
* by user (list)     Query GSI2 ``byUser`` on the ``EVALRUN#`` prefix
* results of a run   Query base table on ``EVALRUN#<runId>`` + ``CASE#``
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from data.client import now_iso, table
from data.keys import (
    EVAL_CASE_PREFIX,
    EVAL_RUN_PREFIX,
    eval_case_sk,
    eval_results_pk,
    eval_run_by_user_sk,
    eval_run_sk,
    user_pk,
)

RUN_QUEUED = "queued"
RUN_RUNNING = "running"
RUN_COMPLETED = "completed"
RUN_FAILED = "failed"
RUN_STATUSES = (RUN_QUEUED, RUN_RUNNING, RUN_COMPLETED, RUN_FAILED)

CASE_OK = "ok"
CASE_ERROR = "error"
CASE_SKIPPED = "skipped"


def new_id() -> str:
    return str(uuid.uuid4())


def _to_dynamo(value: Any) -> Any:
    """DynamoDB rejects Python floats; store metric numbers as ``Decimal``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _to_dynamo(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_dynamo(item) for item in value]
    return value


# --- runs --------------------------------------------------------------------


def _run_item(
    sub: str,
    *,
    run_id: str,
    dataset_id: str,
    dataset_name: str,
    knowledge_base_names: list[str],
    config: dict[str, Any],
    case_count: int,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "pk": user_pk(sub),
        "sk": eval_run_sk(run_id),
        "entity": "evalRun",
        "runId": run_id,
        "userId": sub,
        "datasetId": dataset_id,
        "datasetName": dataset_name,
        "knowledgeBaseNames": knowledge_base_names,
        "config": _to_dynamo(config),
        "status": RUN_QUEUED,
        "caseCount": int(case_count),
        "completedCount": 0,
        "failedCount": 0,
        "skippedCount": 0,
        "metrics": {},
        "error": "",
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        "gsi2pk": user_pk(sub),
        "gsi2sk": eval_run_by_user_sk(timestamp, run_id),
    }


def create_run(
    sub: str,
    *,
    dataset_id: str,
    dataset_name: str,
    knowledge_base_names: list[str],
    config: dict[str, Any],
    case_count: int,
) -> dict[str, Any]:
    run_id = new_id()
    item = _run_item(
        sub,
        run_id=run_id,
        dataset_id=dataset_id,
        dataset_name=dataset_name,
        knowledge_base_names=knowledge_base_names,
        config=config,
        case_count=case_count,
    )
    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    return item


def get_run(sub: str, run_id: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": eval_run_sk(run_id)})
    return response.get("Item")


def list_runs(
    sub: str, limit: int = 50, start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": "gsi2pk = :pk AND begins_with(gsi2sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(sub),
            ":prefix": EVAL_RUN_PREFIX,
        },
        "ScanIndexForward": False,
        "Limit": limit,
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


def update_run(sub: str, run_id: str, **fields: Any) -> dict[str, Any] | None:
    """Patch a run item (status/counters/metrics/error/timestamps)."""
    if not fields:
        return get_run(sub, run_id)
    fields["updatedAt"] = now_iso()
    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    sets: list[str] = []
    for index, (key, value) in enumerate(fields.items()):
        name = f"#f{index}"
        token = f":v{index}"
        names[name] = key
        values[token] = _to_dynamo(value)
        sets.append(f"{name} = {token}")
    # Keep the recency GSI in sync whenever the run is touched.
    names["#g2s"] = "gsi2sk"
    values[":g2s"] = eval_run_by_user_sk(fields["updatedAt"], run_id)
    sets.append("#g2s = :g2s")
    response = table().update_item(
        Key={"pk": user_pk(sub), "sk": eval_run_sk(run_id)},
        UpdateExpression="SET " + ", ".join(sets),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ConditionExpression="attribute_exists(pk)",
        ReturnValues="ALL_NEW",
    )
    return response.get("Attributes")


def delete_run(sub: str, run_id: str) -> dict[str, Any] | None:
    existing = get_run(sub, run_id)
    if existing is None:
        return None
    for result in list_all_case_results(sub, run_id):
        table().delete_item(Key={"pk": result["pk"], "sk": result["sk"]})
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return existing


# --- per-case results --------------------------------------------------------


def put_case_result(
    sub: str,
    run_id: str,
    case_id: str,
    *,
    query: str,
    status: str,
    metrics: dict[str, Any],
    artifact_key: str = "",
    error: str = "",
    latency_ms: int = 0,
    retrieved_count: int = 0,
) -> dict[str, Any]:
    item = {
        "pk": eval_results_pk(run_id),
        "sk": eval_case_sk(case_id),
        "entity": "evalCaseResult",
        "runId": run_id,
        "caseId": case_id,
        "userId": sub,
        "query": query[:1000],
        "status": status,
        "metrics": _to_dynamo(metrics),
        "artifactKey": artifact_key,
        "error": error[:1000],
        "latencyMs": int(latency_ms),
        "retrievedCount": int(retrieved_count),
        "createdAt": now_iso(),
    }
    table().put_item(Item=item)
    return item


def get_case_result(sub: str, run_id: str, case_id: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": eval_results_pk(run_id), "sk": eval_case_sk(case_id)}
    )
    item = response.get("Item")
    if item is None or item.get("userId") != sub:
        return None
    return item


def list_case_results(
    sub: str, run_id: str, limit: int = 200, start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": eval_results_pk(run_id),
            ":prefix": EVAL_CASE_PREFIX,
        },
        "ScanIndexForward": True,
        "Limit": limit,
    }
    if start_key:
        kwargs["ExclusiveStartKey"] = start_key
    response = table().query(**kwargs)
    items = [item for item in (response.get("Items") or []) if item.get("userId") == sub]
    return items, response.get("LastEvaluatedKey")


def list_all_case_results(sub: str, run_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    start_key: dict[str, Any] | None = None
    while True:
        page, start_key = list_case_results(sub, run_id, limit=200, start_key=start_key)
        items.extend(page)
        if not start_key:
            break
    return items

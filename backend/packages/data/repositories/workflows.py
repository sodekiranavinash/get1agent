"""Workflow repository.

A workflow composes several saved agents into one orchestration. It is a single
item whose ``config`` map holds the mode (``graph`` | ``swarm``), the input/output
settings and the node/edge graph; the agent nodes reference saved agents by id
(never embed their config).

Keys (single table, see docs/design/design-b-dynamodb-s3.md Part 6):

    Workflow       USER#<userId>    WORKFLOW#<lowerName>
    GSI1 byId      WORKFLOW#<id>    #META
    GSI2 byUser    USER#<userId>    WORKFLOW#<updatedAt>#<name>

Workflows are private for now; there is no public library projection.
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import (
    GSI1,
    GSI2,
    META,
    WORKFLOW_PREFIX,
    user_pk,
    workflow_sk,
)


class DuplicateWorkflow(Exception):
    pass


def _new_item(
    sub: str,
    *,
    workflow_id: str,
    name: str,
    description: str,
    config: dict[str, Any],
    status: str,
    version: int = 1,
    verified_at: str | None = None,
    last_run_at: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    nodes = config.get("nodes") or []
    agent_count = sum(
        1 for node in nodes if isinstance(node, dict) and node.get("type") == "agent"
    )
    item: dict[str, Any] = {
        "pk": user_pk(sub),
        "sk": workflow_sk(name),
        "entity": "workflow",
        "workflowId": workflow_id,
        "userId": sub,
        "name": name,
        "description": description,
        "status": status,
        "mode": config.get("mode") or "graph",
        "version": version,
        "config": config,
        "agentCount": agent_count,
        "verifiedAt": verified_at,
        "lastRunAt": last_run_at,
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        GSI1[0]: f"{WORKFLOW_PREFIX}{workflow_id}",
        GSI1[1]: META,
        GSI2[0]: user_pk(sub),
        GSI2[1]: f"{WORKFLOW_PREFIX}{timestamp}#{name}",
    }
    return item


def create_workflow(
    sub: str,
    *,
    workflow_id: str,
    name: str,
    description: str,
    config: dict[str, Any],
) -> dict[str, Any]:
    item = _new_item(
        sub,
        workflow_id=workflow_id,
        name=name,
        description=description,
        config=config,
        status="draft",
    )
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateWorkflow(name) from exc
        raise
    return item


def list_workflows(sub: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(sub),
            ":prefix": WORKFLOW_PREFIX,
        },
        "ScanIndexForward": False,
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: item.get("name", ""))


def get_workflow(sub: str, workflow_id: str) -> dict[str, Any] | None:
    item = _get_by_id(workflow_id)
    if item is None or item.get("userId") != sub:
        return None
    return item


def get_workflow_by_name(sub: str, name: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": workflow_sk(name)})
    return response.get("Item")


def update_workflow(
    sub: str,
    workflow_id: str,
    *,
    name: str,
    description: str,
    config: dict[str, Any],
) -> dict[str, Any] | None:
    """Full replace. Any edit resets verification (a promise about a config)."""
    existing = get_workflow(sub, workflow_id)
    if existing is None:
        return None
    new_item = _new_item(
        sub,
        workflow_id=workflow_id,
        name=name,
        description=description,
        config=config,
        status="draft",
        version=int(existing.get("version") or 1) + 1,
        created_at=existing.get("createdAt"),
    )
    if existing["sk"] == new_item["sk"]:
        table().put_item(Item=new_item)
        return new_item

    try:
        table().put_item(Item=new_item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateWorkflow(name) from exc
        raise
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return new_item


def delete_workflow(sub: str, workflow_id: str) -> dict[str, Any] | None:
    existing = get_workflow(sub, workflow_id)
    if existing is None:
        return None
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return existing


def count_workflows(sub: str) -> int:
    response = table().query(
        IndexName="byUser",
        KeyConditionExpression=f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        ExpressionAttributeValues={
            ":pk": user_pk(sub),
            ":prefix": WORKFLOW_PREFIX,
        },
        Select="COUNT",
    )
    return int(response.get("Count") or 0)


def mark_verified(sub: str, workflow_id: str, *, verified_at: str) -> None:
    existing = get_workflow(sub, workflow_id)
    if existing is None:
        return
    table().update_item(
        Key={"pk": existing["pk"], "sk": existing["sk"]},
        UpdateExpression="SET #status = :status, verifiedAt = :verified, updatedAt = :updated",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={
            ":status": "verified",
            ":verified": verified_at,
            ":updated": now_iso(),
        },
    )


def mark_run(sub: str, workflow_id: str, *, run_at: str) -> None:
    """Best-effort ``lastRunAt`` stamp (called by the runtime after a run)."""
    existing = get_workflow(sub, workflow_id)
    if existing is None:
        return
    table().update_item(
        Key={"pk": existing["pk"], "sk": existing["sk"]},
        UpdateExpression="SET lastRunAt = :run, updatedAt = :updated",
        ExpressionAttributeValues={":run": run_at, ":updated": now_iso()},
    )


def _get_by_id(workflow_id: str) -> dict[str, Any] | None:
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"{WORKFLOW_PREFIX}{workflow_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    return items[0] if items else None


def _is_conditional_failure(exc: BaseException) -> bool:
    from botocore.exceptions import ClientError

    return (
        isinstance(exc, ClientError)
        and exc.response.get("Error", {}).get("Code")
        == "ConditionalCheckFailedException"
    )

"""Schedule registry: the cron for every enabled agent/workflow schedule.

Each user entity (agent/workflow) stores its schedule inside ``config``. The
scheduler cannot scan every entity, so whenever an entity is saved the schedule
is mirrored here as one small item:

    USER#<userId> / SCHEDULE#<kind>#<targetId>

The item carries a GSI3 key (``gsi3pk = SCHEDULES#enabled``,
``gsi3sk = <nextRunAt>#<userId>``) so the scheduler finds every due schedule
across all users with one range query — never a Scan. Disabling or removing a
schedule deletes the row (sparse GSI3).

Access patterns:

* list due schedules   Query GSI3 on ``SCHEDULES#enabled`` where sk <= now
* one entity's schedule GetItem on the base table
"""

from __future__ import annotations

from typing import Any

from core import schedule as cron
from data.client import now_iso, table
from data.keys import (
    GSI3,
    SCHEDULE_DUE_PK,
    schedule_due_sk,
    schedule_sk,
    user_pk,
)

KIND_AGENT = "agent"
KIND_WORKFLOW = "workflow"
KINDS = (KIND_AGENT, KIND_WORKFLOW)


def get_schedule(user_id: str, kind: str, target_id: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": user_pk(user_id), "sk": schedule_sk(kind, target_id)}
    )
    return response.get("Item")


def delete_schedule(user_id: str, kind: str, target_id: str) -> None:
    table().delete_item(
        Key={"pk": user_pk(user_id), "sk": schedule_sk(kind, target_id)}
    )


def upsert_schedule(
    user_id: str,
    kind: str,
    target_id: str,
    *,
    name: str = "",
    expression: str = "",
    timezone: str = "UTC",
    enabled: bool = False,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Register (or clear) an entity's schedule.

    A disabled schedule, or one without a cron expression, is removed so the
    sparse GSI3 never carries a dead row. ``payload`` is the run input the
    scheduler passes to the runtime (e.g. ``{"query": "..."}``).
    """
    if not enabled or not str(expression or "").strip():
        delete_schedule(user_id, kind, target_id)
        return None

    next_run = cron.next_run_at(expression, timezone)
    existing = get_schedule(user_id, kind, target_id) or {}
    now = now_iso()
    item = {
        "pk": user_pk(user_id),
        "sk": schedule_sk(kind, target_id),
        "entity": "schedule",
        "userId": user_id,
        "kind": kind,
        "targetId": target_id,
        "name": name,
        "cron": expression,
        "timezone": timezone or "UTC",
        "enabled": True,
        "payload": payload or {},
        "nextRunAt": next_run,
        "lastRunAt": existing.get("lastRunAt"),
        "lastStatus": existing.get("lastStatus"),
        "lastError": existing.get("lastError"),
        "gsi3pk": SCHEDULE_DUE_PK,
        "gsi3sk": schedule_due_sk(next_run, user_id) if next_run else "",
        "createdAt": existing.get("createdAt") or now,
        "updatedAt": now,
    }
    table().put_item(Item=item)
    return item


def list_due(now_iso_value: str, limit: int = 50) -> list[dict[str, Any]]:
    """Every enabled schedule whose ``nextRunAt`` is at or before ``now``."""
    pk_name, sk_name = GSI3
    response = table().query(
        IndexName="byStatus",
        KeyConditionExpression=f"{pk_name} = :pk AND {sk_name} <= :now",
        ExpressionAttributeValues={":pk": SCHEDULE_DUE_PK, ":now": now_iso_value},
        Limit=limit,
    )
    return response.get("Items") or []


def record_run(
    user_id: str,
    kind: str,
    target_id: str,
    *,
    ran_at: str,
    status: str,
    error: str = "",
) -> None:
    """Stamp a schedule's outcome and compute its next firing time."""
    item = get_schedule(user_id, kind, target_id)
    if not item:
        return
    next_run = cron.next_run_at(
        str(item.get("cron") or ""), str(item.get("timezone") or "UTC")
    )
    # A no-longer-computable schedule drops off the sparse GSI3 (empty keys).
    table().update_item(
        Key={"pk": user_pk(user_id), "sk": schedule_sk(kind, target_id)},
        UpdateExpression=(
            "SET lastRunAt = :ran, lastStatus = :status, lastError = :error, "
            "nextRunAt = :next, #g3pk = :g3pk, gsi3sk = :g3sk, updatedAt = :now"
        ),
        ExpressionAttributeNames={"#g3pk": "gsi3pk"},
        ExpressionAttributeValues={
            ":ran": ran_at,
            ":status": status,
            ":error": error[:500],
            ":next": next_run,
            ":g3pk": SCHEDULE_DUE_PK if next_run else "",
            ":g3sk": schedule_due_sk(next_run, user_id) if next_run else "",
            ":now": now_iso(),
        },
    )


def due_check(now_iso_value: str = "") -> list[dict[str, Any]]:
    """Convenience wrapper used by tests and the scheduler handler."""
    return list_due(now_iso_value or now_iso())

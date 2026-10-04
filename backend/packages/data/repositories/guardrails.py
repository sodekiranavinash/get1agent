"""Per-user Amazon Bedrock guardrails.

One item per guardrail (``USER#<userId>`` / ``GUARDRAIL#<name>``). ``name`` is a
lowercase-hyphen slug (unique per user, the item key); the raw Bedrock guardrail
id lives in ``guardrailId`` and is what an agent/workflow stores to apply it. The
UI-shaped policy (content filters, denied topics, word filters, sensitive
information, contextual grounding) is kept in ``config`` so the editor can load
and update it; ``core.guardrails.policy_config_kwargs`` maps it to the Bedrock
request.

No GSI: the list is a base-table Query on the user's partition under the
``GUARDRAIL#`` prefix (a user has at most a couple of dozen), and lookups are a
``GetItem`` by name. The Bedrock guardrail id is deliberately *not* the key so a
user can rename the app-side label without touching the guardrail.
"""

from __future__ import annotations

from typing import Any

from data.client import is_conditional_failure, now_iso, table
from data.keys import GUARDRAIL_PREFIX, guardrail_sk, user_pk


class DuplicateGuardrail(Exception):
    """A guardrail with this name already exists for the user."""


def guardrail_item(
    *,
    user_id: str,
    name: str,
    description: str,
    guardrail_id: str,
    guardrail_arn: str,
    version: str,
    status: str,
    config: dict[str, Any],
    blocked_input: str,
    blocked_output: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "pk": user_pk(user_id),
        "sk": guardrail_sk(name),
        "entity": "guardrail",
        "userId": user_id,
        "name": name,
        "description": description,
        "guardrailId": guardrail_id,
        "guardrailArn": guardrail_arn,
        "version": version,
        "status": status,
        "config": config,
        "blockedInput": blocked_input,
        "blockedOutput": blocked_output,
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
    }


def create_guardrail(item: dict[str, Any]) -> dict[str, Any]:
    try:
        table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except Exception as exc:  # noqa: BLE001
        if is_conditional_failure(exc):
            raise DuplicateGuardrail(item.get("name")) from exc
        raise
    return item


def get_guardrail(user_id: str, name: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(user_id), "sk": guardrail_sk(name)})
    return response.get("Item")


def list_guardrails(user_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": GUARDRAIL_PREFIX,
        },
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: str(item.get("name", "")))


def count_guardrails(user_id: str) -> int:
    response = table().query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={
            ":pk": user_pk(user_id),
            ":prefix": GUARDRAIL_PREFIX,
        },
        Select="COUNT",
    )
    return int(response.get("Count") or 0)


def update_guardrail(
    user_id: str,
    name: str,
    *,
    description: str | None = None,
    guardrail_id: str | None = None,
    guardrail_arn: str | None = None,
    version: str | None = None,
    status: str | None = None,
    config: dict[str, Any] | None = None,
    blocked_input: str | None = None,
    blocked_output: str | None = None,
) -> dict[str, Any] | None:
    existing = get_guardrail(user_id, name)
    if existing is None:
        return None
    updated = dict(existing)
    if description is not None:
        updated["description"] = description
    if guardrail_id is not None:
        updated["guardrailId"] = guardrail_id
    if guardrail_arn is not None:
        updated["guardrailArn"] = guardrail_arn
    if version is not None:
        updated["version"] = version
    if status is not None:
        updated["status"] = status
    if config is not None:
        updated["config"] = config
    if blocked_input is not None:
        updated["blockedInput"] = blocked_input
    if blocked_output is not None:
        updated["blockedOutput"] = blocked_output
    updated["updatedAt"] = now_iso()
    table().put_item(Item=updated)
    return updated


def delete_guardrail(user_id: str, name: str) -> dict[str, Any] | None:
    existing = get_guardrail(user_id, name)
    if existing is None:
        return None
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return existing

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import GSI1, GSI2, META, SKILL_PREFIX, skill_sk, user_pk


class DuplicateSkill(Exception):
    pass


def _new_item(
    sub: str,
    *,
    skill_id: str,
    name: str,
    description: str,
    allowed_tools: list[str],
    content: str,
    source: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "pk": user_pk(sub),
        "sk": skill_sk(name),
        "entity": "skill",
        "skillId": skill_id,
        "userId": sub,
        "name": name,
        "description": description,
        "allowedTools": allowed_tools,
        "content": content,
        "source": source,
        "createdAt": created_at or timestamp,
        "updatedAt": timestamp,
        GSI1[0]: f"SKILL#{skill_id}",
        GSI1[1]: META,
        GSI2[0]: user_pk(sub),
        GSI2[1]: f"{SKILL_PREFIX}{name}",
    }


def create_skill(
    sub: str,
    *,
    skill_id: str,
    name: str,
    description: str,
    allowed_tools: list[str],
    content: str,
    source: str,
) -> dict[str, Any]:
    item = _new_item(
        sub,
        skill_id=skill_id,
        name=name,
        description=description,
        allowed_tools=allowed_tools,
        content=content,
        source=source,
    )
    try:
        table().put_item(
            Item=item, ConditionExpression="attribute_not_exists(pk)"
        )
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateSkill(name) from exc
        raise
    return item


def list_skills(sub: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(sub),
            ":prefix": SKILL_PREFIX,
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


def get_skill(sub: str, skill_id: str) -> dict[str, Any] | None:
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"SKILL#{skill_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    if not items:
        return None
    item = items[0]
    if item.get("userId") != sub:
        return None
    return item


def get_skill_by_name(sub: str, name: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": skill_sk(name)})
    return response.get("Item")


def update_skill(
    sub: str,
    skill_id: str,
    *,
    name: str,
    description: str,
    allowed_tools: list[str],
    content: str,
    source: str,
) -> dict[str, Any] | None:
    """Full replace. Renaming moves the item (name is part of the key)."""
    existing = get_skill(sub, skill_id)
    if existing is None:
        return None
    new_item = _new_item(
        sub,
        skill_id=skill_id,
        name=name,
        description=description,
        allowed_tools=allowed_tools,
        content=content,
        source=source,
        created_at=existing.get("createdAt"),
    )
    # Renaming needs a delete + conditional put; same-name is a plain put.
    if existing["sk"] != new_item["sk"]:
        table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    try:
        table().put_item(
            Item=new_item, ConditionExpression="attribute_not_exists(pk)"
        )
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateSkill(name) from exc
        raise
    return new_item


def delete_skill(sub: str, skill_id: str) -> dict[str, Any] | None:
    existing = get_skill(sub, skill_id)
    if existing is None:
        return None
    table().delete_item(Key={"pk": existing["pk"], "sk": existing["sk"]})
    return existing


def count_skills(sub: str) -> int:
    response = table().query(
        IndexName="byUser",
        KeyConditionExpression=f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        ExpressionAttributeValues={
            ":pk": user_pk(sub),
            ":prefix": SKILL_PREFIX,
        },
        Select="COUNT",
    )
    return int(response.get("Count") or 0)


def _is_conditional_failure(exc: BaseException) -> bool:
    from botocore.exceptions import ClientError

    return (
        isinstance(exc, ClientError)
        and exc.response.get("Error", {}).get("Code")
        == "ConditionalCheckFailedException"
    )

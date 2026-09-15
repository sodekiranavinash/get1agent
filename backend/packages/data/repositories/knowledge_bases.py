from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import GSI1, GSI2, KB_PREFIX, META, kb_sk, user_pk

KB_STATUSES = ("processing", "ready", "failed")


class DuplicateKnowledgeBase(Exception):
    pass


def _new_item(
    sub: str,
    *,
    kb_id: str,
    name: str,
    description: str | None,
    status: str,
    embed_model: str,
    image_embed_model: str,
    embedding_dim: int,
    chunk_size: int,
    chunk_overlap: int,
) -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "pk": user_pk(sub),
        "sk": kb_sk(name),
        "entity": "knowledgeBase",
        "kbId": kb_id,
        "userId": sub,
        "name": name,
        "description": description,
        "status": status,
        "embedModel": embed_model,
        "imageEmbedModel": image_embed_model,
        "embeddingDim": embedding_dim,
        "chunkSize": chunk_size,
        "chunkOverlap": chunk_overlap,
        "docCount": 0,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        GSI1[0]: f"KB#{kb_id}",
        GSI1[1]: META,
        GSI2[0]: user_pk(sub),
        GSI2[1]: f"{KB_PREFIX}{timestamp}#{name}",
    }


def create_kb(
    sub: str,
    *,
    kb_id: str,
    name: str,
    description: str | None,
    status: str,
    embed_model: str,
    image_embed_model: str,
    embedding_dim: int,
    chunk_size: int,
    chunk_overlap: int,
) -> dict[str, Any]:
    item = _new_item(
        sub,
        kb_id=kb_id,
        name=name,
        description=description,
        status=status,
        embed_model=embed_model,
        image_embed_model=image_embed_model,
        embedding_dim=embedding_dim,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    try:
        table().put_item(
            Item=item, ConditionExpression="attribute_not_exists(pk)"
        )
    except Exception as exc:  # noqa: BLE001
        if _is_conditional_failure(exc):
            raise DuplicateKnowledgeBase(name) from exc
        raise
    return item


def get_kb(sub: str, kb_id: str) -> dict[str, Any] | None:
    """Resolve a KB by UUID (GSI1) and confirm it belongs to the caller."""
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"KB#{kb_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    if not items:
        return None
    item = items[0]
    if item.get("userId") != sub:
        return None
    return item


def get_kb_by_name(sub: str, name: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": kb_sk(name)})
    return response.get("Item")


def list_kbs(sub: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        "ExpressionAttributeValues": {":pk": user_pk(sub), ":prefix": "KB#"},
        "ScanIndexForward": False,
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def update_kb(kb_id: str, *, status: str | None = None, **fields: Any) -> None:
    item = get_kb_by_id(kb_id)
    if item is None:
        return
    updates = ["updatedAt = :updated"]
    values: dict[str, Any] = {":updated": now_iso()}
    names: dict[str, str] = {}
    if status is not None:
        updates.append("#status = :status")
        names["#status"] = "status"
        values[":status"] = status
    for key, value in fields.items():
        if value is None:
            continue
        updates.append(f"#{key} = :{key}")
        names[f"#{key}"] = key
        values[f":{key}"] = value
    # Keep the GSI2 sort key (updatedAt#name) in sync with updatedAt.
    updates.append(f"{GSI2[1]} = :gsi2sk")
    values[":gsi2sk"] = f"{KB_PREFIX}{values[':updated']}#{item['name']}"
    table().update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression="SET " + ", ".join(updates),
        ExpressionAttributeValues=values,
        **({"ExpressionAttributeNames": names} if names else {}),
    )


def get_kb_by_id(kb_id: str) -> dict[str, Any] | None:
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"KB#{kb_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    return items[0] if items else None


def adjust_doc_count(kb_id: str, delta: int) -> None:
    if not delta:
        return
    item = get_kb_by_id(kb_id)
    if item is None:
        return
    timestamp = now_iso()
    table().update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression=(
            "SET updatedAt = :updated, "
            f"{GSI2[1]} = :gsi2sk ADD docCount :delta"
        ),
        ExpressionAttributeValues={
            ":delta": delta,
            ":updated": timestamp,
            ":gsi2sk": f"{KB_PREFIX}{timestamp}#{item['name']}",
        },
    )


def adjust_processing(kb_id: str, delta: int) -> int:
    """Move a KB in/out of ``processing`` based on its in-flight document count."""
    item = get_kb_by_id(kb_id)
    if item is None:
        return 0
    timestamp = now_iso()
    response = table().update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression=(
            "SET updatedAt = :updated, "
            + f"{GSI2[1]} = :gsi2sk ADD processingCount :delta"
        ),
        ExpressionAttributeValues={
            ":delta": delta,
            ":updated": timestamp,
            ":gsi2sk": f"{KB_PREFIX}{timestamp}#{item['name']}",
        },
        ReturnValues="UPDATED_NEW",
    )
    count = max(0, int((response.get("Attributes") or {}).get("processingCount") or 0))
    desired = "processing" if count > 0 else "ready"
    if item.get("status") != desired:
        table().update_item(
            Key={"pk": item["pk"], "sk": item["sk"]},
            UpdateExpression="SET #status = :status",
            ExpressionAttributeValues={":status": desired},
            ExpressionAttributeNames={"#status": "status"},
        )
    return count


def delete_kb(kb_id: str) -> dict[str, Any] | None:
    item = get_kb_by_id(kb_id)
    if item is None:
        return None
    table().delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
    return item


def _is_conditional_failure(exc: BaseException) -> bool:
    from botocore.exceptions import ClientError

    return (
        isinstance(exc, ClientError)
        and exc.response.get("Error", {}).get("Code")
        == "ConditionalCheckFailedException"
    )

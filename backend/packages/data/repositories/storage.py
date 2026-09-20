"""Standalone user file storage (separate from knowledge bases).

One item per uploaded file (``USER#<userId>`` / ``STORAGE#<fileId>``). The bytes
live in S3 under ``storage/<userId>/<fileId>/<fileName>``; this table only holds
small metadata so it can be listed and attached to agents later.
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import STORAGE_PREFIX, storage_sk, user_pk


def storage_item(
    *,
    file_id: str,
    user_id: str,
    file_name: str,
    s3_key: str,
    content_type: str | None,
    size_bytes: int,
    status: str = "ready",
    content_hash: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or now_iso()
    return {
        "pk": user_pk(user_id),
        "sk": storage_sk(file_id),
        "entity": "storageFile",
        "fileId": file_id,
        "userId": user_id,
        "fileName": file_name,
        "s3Key": s3_key,
        "contentType": content_type,
        "sizeBytes": size_bytes,
        "status": status,
        "contentHash": content_hash,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def put_file(item: dict[str, Any]) -> dict[str, Any]:
    table().put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    return item


def get_file(user_id: str, file_id: str) -> dict[str, Any] | None:
    response = table().get_item(Key={"pk": user_pk(user_id), "sk": storage_sk(file_id)})
    return response.get("Item")


def list_files(user_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": STORAGE_PREFIX,
        },
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: item.get("createdAt", ""), reverse=True)


def delete_file(user_id: str, file_id: str) -> dict[str, Any] | None:
    response = table().delete_item(
        Key={"pk": user_pk(user_id), "sk": storage_sk(file_id)},
        ReturnValues="ALL_OLD",
    )
    return response.get("Attributes")

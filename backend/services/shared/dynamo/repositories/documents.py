from __future__ import annotations

from typing import Any

from shared.dynamo.client import now_iso, table
from shared.dynamo.keys import DOC_PREFIX, GSI1, GSI3, META, doc_pk, doc_sk

DOCUMENT_SOURCES = ("upload", "inline")
DOCUMENT_STATUSES = ("pending", "uploaded", "processing", "ready", "failed")


def document_item(
    *,
    doc_id: str,
    kb_id: str,
    user_id: str,
    file_name: str,
    s3_key: str,
    content_type: str | None,
    size_bytes: int,
    source: str,
    status: str,
    content_hash: str | None = None,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or now_iso()
    file_key = doc_sk(file_name)
    return {
        "pk": doc_pk(kb_id),
        "sk": file_key,
        "entity": "document",
        "docId": doc_id,
        "kbId": kb_id,
        "userId": user_id,
        "fileName": file_name,
        "fileKey": file_key,
        "s3Key": s3_key,
        "contentType": content_type,
        "sizeBytes": size_bytes,
        "source": source,
        "status": status,
        "contentHash": content_hash,
        "chunkCount": 0,
        "imageCount": 0,
        "embedModel": None,
        "imageEmbedModel": None,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        GSI1[0]: f"DOC#{doc_id}",
        GSI1[1]: META,
        GSI3[0]: f"DOCSTATUS#{status}",
        GSI3[1]: f"{timestamp}#{doc_id}",
    }


def put_document(item: dict[str, Any], *, condition: str | None = None) -> None:
    kwargs: dict[str, Any] = {"Item": item}
    if condition:
        kwargs["ConditionExpression"] = condition
    table().put_item(**kwargs)


def get_document(kb_id: str, file_name: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": doc_pk(kb_id), "sk": doc_sk(file_name)}
    )
    return response.get("Item")


def get_document_by_id(doc_id: str) -> dict[str, Any] | None:
    response = table().query(
        IndexName="byId",
        KeyConditionExpression=f"{GSI1[0]} = :pk",
        ExpressionAttributeValues={":pk": f"DOC#{doc_id}"},
        Limit=1,
    )
    items = response.get("Items") or []
    return items[0] if items else None


def list_documents(kb_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {":pk": doc_pk(kb_id), ":prefix": DOC_PREFIX},
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def update_document(doc_id: str, **fields: Any) -> dict[str, Any] | None:
    item = get_document_by_id(doc_id)
    if item is None:
        return None
    timestamp = now_iso()
    updates = ["updatedAt = :updated"]
    values: dict[str, Any] = {":updated": timestamp}
    names: dict[str, str] = {}
    status = fields.get("status")
    for key, value in fields.items():
        updates.append(f"#{key} = :{key}")
        names[f"#{key}"] = key
        values[f":{key}"] = value
    # The status GSI must always point at the latest status + timestamp.
    if status is not None:
        updates.append(f"{GSI3[0]} = :gsi3pk")
        updates.append(f"{GSI3[1]} = :gsi3sk")
        values[":gsi3pk"] = f"DOCSTATUS#{status}"
        values[":gsi3sk"] = f"{timestamp}#{doc_id}"
    table().update_item(
        Key={"pk": item["pk"], "sk": item["sk"]},
        UpdateExpression="SET " + ", ".join(updates),
        ExpressionAttributeValues=values,
        **({"ExpressionAttributeNames": names} if names else {}),
    )
    item.update(fields)
    item["updatedAt"] = timestamp
    return item


def delete_document(doc_id: str) -> dict[str, Any] | None:
    item = get_document_by_id(doc_id)
    if item is None:
        return None
    table().delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
    return item


def find_by_status_older_than(status: str, cutoff_iso: str) -> list[dict[str, Any]]:
    response = table().query(
        IndexName="byStatus",
        KeyConditionExpression=f"{GSI3[0]} = :pk AND {GSI3[1]} < :cutoff",
        ExpressionAttributeValues={
            ":pk": f"DOCSTATUS#{status}",
            ":cutoff": cutoff_iso,
        },
    )
    return list(response.get("Items") or [])


def batch_get_documents(keys: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, Any]]:
    """BatchGet documents by their primary keys (max 100 per request)."""
    found: dict[tuple[str, str], dict[str, Any]] = {}
    unique = {(key["pk"], key["sk"]): key for key in keys}
    pending = list(unique.values())
    for start in range(0, len(pending), 100):
        batch = pending[start : start + 100]
        response = table().meta.client.batch_get_item(
            RequestItems={
                table().table_name: {
                    "Keys": [{"pk": key["pk"], "sk": key["sk"]} for key in batch],
                }
            }
        )
        for item in response.get("Responses", {}).get(table().table_name, []):
            found[(item["pk"], item["sk"])] = item
        unprocessed = (
            response.get("UnprocessedKeys", {}).get(table().table_name, {}).get("Keys")
        )
        if unprocessed:
            for key in unprocessed:
                found.setdefault((key["pk"], key["sk"]), {})
    return found

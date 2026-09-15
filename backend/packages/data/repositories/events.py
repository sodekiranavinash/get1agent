from __future__ import annotations

import uuid
from typing import Any

from data.client import now_iso, table, ttl_epoch
from data.repositories.documents import get_document_by_id
from data.keys import EVENT_PREFIX, GSI3, doc_ref_pk, event_sk

# Events are the UI timeline; keep 90 days and let DynamoDB TTL reap them.
EVENT_TTL_DAYS = 90


def emit_event(
    *,
    document_id: str,
    knowledge_base_id: str,
    user_id: str,
    stage: str,
    status: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
    file_name: str | None = None,
    file_key: str | None = None,
) -> dict[str, Any]:
    if file_name is None or file_key is None:
        document = get_document_by_id(document_id)
        if document:
            file_name = file_name or document.get("fileName")
            file_key = file_key or document.get("fileKey")
    created_at = now_iso()
    seq = uuid.uuid4().hex[:8]
    item = {
        "pk": doc_ref_pk(document_id),
        "sk": event_sk(created_at, seq),
        "entity": "event",
        "documentId": document_id,
        "knowledgeBaseId": knowledge_base_id,
        "userId": user_id,
        "fileName": file_name,
        "fileKey": file_key,
        "stage": stage,
        "status": status,
        "message": message,
        "details": details,
        "createdAt": created_at,
        "expiresAt": ttl_epoch(EVENT_TTL_DAYS),
        GSI3[0]: f"USER#{user_id}#EVENT",
        GSI3[1]: f"{created_at}#{document_id}",
    }
    table().put_item(Item=item)
    return item


def delete_events_for_document(doc_id: str) -> int:
    """Remove a document's timeline.

    Events live under ``pk=DOC#<docId>``; deleting the document item does not
    remove them, so the Activity feed would otherwise keep showing a file after
    it is removed from the knowledge base.
    """
    deleted = 0
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {":pk": doc_ref_pk(doc_id), ":prefix": EVENT_PREFIX},
    }
    while True:
        response = table().query(**kwargs)
        for item in response.get("Items") or []:
            table().delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
            deleted += 1
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return deleted


def list_events(
    sub: str, *, limit: int = 50, kb_id: str | None = None
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "IndexName": "byStatus",
        "KeyConditionExpression": f"{GSI3[0]} = :pk",
        "ExpressionAttributeValues": {":pk": f"USER#{sub}#EVENT"},
        "ScanIndexForward": False,
    }
    # When filtering by KB, keep paging until the limit is filled.
    while len(events) < limit:
        response = table().query(**kwargs)
        for item in response.get("Items") or []:
            if kb_id and item.get("knowledgeBaseId") != kb_id:
                continue
            events.append(item)
            if len(events) >= limit:
                break
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return events

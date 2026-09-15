from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import GSI2, TAG_PREFIX, doc_pk, doc_ref_pk, tag_sk, user_pk


def replace_tags(
    sub: str, doc_id: str, kb_id: str, file_key: str, tags: list[tuple[str, str]]
) -> None:
    """Replace a document's tag items and its denormalized tag list."""
    delete_tags_for_document(doc_id)
    timestamp = now_iso()
    serialized: list[dict[str, str]] = []
    for name, description in tags:
        serialized.append({"name": name, "description": description or ""})
        table().put_item(
            Item={
                "pk": doc_ref_pk(doc_id),
                "sk": tag_sk(name),
                "entity": "tag",
                "documentId": doc_id,
                "kbId": kb_id,
                "name": name,
                "description": description or None,
                "createdAt": timestamp,
                GSI2[0]: user_pk(sub),
                GSI2[1]: f"{TAG_PREFIX}{name.lower()}#{doc_id}",
            }
        )
    # Keep the document item's own tag list in sync so listing documents does
    # not fan out into one query per document.
    try:
        table().update_item(
            Key={"pk": doc_pk(kb_id), "sk": file_key},
            UpdateExpression="SET tags = :tags",
            ExpressionAttributeValues={":tags": serialized},
            ConditionExpression="attribute_exists(pk)",
        )
    except Exception:  # noqa: BLE001 - tags are best-effort denormalization
        pass


def delete_tags_for_document(doc_id: str) -> None:
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {":pk": doc_ref_pk(doc_id), ":prefix": TAG_PREFIX},
    }
    while True:
        response = table().query(**kwargs)
        for item in response.get("Items") or []:
            table().delete_item(Key={"pk": item["pk"], "sk": item["sk"]})
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]


def list_tags(sub: str) -> list[dict[str, str]]:
    """Distinct tag names the user has used (most recent description wins)."""
    seen: dict[str, dict[str, str]] = {}
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        "ExpressionAttributeValues": {":pk": user_pk(sub), ":prefix": TAG_PREFIX},
        "ScanIndexForward": False,
    }
    while True:
        response = table().query(**kwargs)
        for item in response.get("Items") or []:
            name = str(item.get("name") or "")
            if not name:
                continue
            seen.setdefault(
                name,
                {"name": name, "description": item.get("description") or ""},
            )
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(seen.values(), key=lambda item: item["name"].lower())


def list_tags_by_kb(sub: str) -> dict[str, list[dict[str, str]]]:
    """Tags grouped by the knowledge base they were used in (discovery tool)."""
    grouped: dict[str, dict[str, dict[str, str]]] = {}
    kwargs: dict[str, Any] = {
        "IndexName": "byUser",
        "KeyConditionExpression": f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        "ExpressionAttributeValues": {":pk": user_pk(sub), ":prefix": TAG_PREFIX},
    }
    while True:
        response = table().query(**kwargs)
        for item in response.get("Items") or []:
            kb_id = str(item.get("kbId") or "")
            name = str(item.get("name") or "")
            if not kb_id or not name:
                continue
            grouped.setdefault(kb_id, {}).setdefault(
                name,
                {"name": name, "description": item.get("description") or ""},
            )
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return {
        kb_id: sorted(tags.values(), key=lambda item: item["name"].lower())
        for kb_id, tags in grouped.items()
    }


def list_document_tags(doc_id: str) -> list[dict[str, str]]:
    """Tags attached to one document, in insertion order."""
    response = table().query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :prefix)",
        ExpressionAttributeValues={":pk": doc_ref_pk(doc_id), ":prefix": TAG_PREFIX},
    )
    items = response.get("Items") or []
    items.sort(key=lambda item: item.get("createdAt") or "")
    return [
        {"name": item.get("name"), "description": item.get("description") or ""}
        for item in items
    ]


def document_ids_for_tag(sub: str, name: str) -> set[str]:
    """Document ids that carry ``name`` (one tag → documents lookup)."""
    prefix = f"{TAG_PREFIX}{name.lower()}#"
    response = table().query(
        IndexName="byUser",
        KeyConditionExpression=f"{GSI2[0]} = :pk AND begins_with({GSI2[1]}, :prefix)",
        ExpressionAttributeValues={":pk": user_pk(sub), ":prefix": prefix},
    )
    return {str(item.get("documentId")) for item in response.get("Items") or []}

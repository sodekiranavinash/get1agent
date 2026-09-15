from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from data.client import now_iso, table
from data.keys import QUOTA_SK, user_pk

# User-level defaults. Rows in the quota item override these per user.
# Up to 10 knowledge bases x 25 files x 10 MB, capped at 100 MB storage/user.
DEFAULT_MAX_KNOWLEDGE_BASES = 10
DEFAULT_MAX_FILES_PER_KB = 25
DEFAULT_MAX_FILES_PER_USER = 250
DEFAULT_MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
DEFAULT_MAX_STORAGE_BYTES = 100 * 1024 * 1024  # 100 MB


@dataclass(frozen=True)
class Quota:
    max_file_bytes: int
    max_files_per_kb: int
    max_knowledge_bases: int
    max_files_per_user: int
    max_storage_bytes: int
    kb_count: int = 0
    file_count: int = 0
    storage_bytes: int = 0


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def ensure_quota(sub: str) -> None:
    timestamp = now_iso()
    try:
        table().put_item(
            Item={
                "pk": user_pk(sub),
                "sk": QUOTA_SK,
                "entity": "quota",
                "kbCount": 0,
                "fileCount": 0,
                "storageBytes": 0,
                "maxFileBytes": DEFAULT_MAX_FILE_BYTES,
                "maxFilesPerKb": DEFAULT_MAX_FILES_PER_KB,
                "maxKnowledgeBases": DEFAULT_MAX_KNOWLEDGE_BASES,
                "maxFilesPerUser": DEFAULT_MAX_FILES_PER_USER,
                "maxStorageBytes": DEFAULT_MAX_STORAGE_BYTES,
                "createdAt": timestamp,
                "updatedAt": timestamp,
            },
            ConditionExpression="attribute_not_exists(pk)",
        )
    except Exception:  # noqa: BLE001 - already exists
        pass


def get_quota(sub: str) -> Quota:
    response = table().get_item(Key={"pk": user_pk(sub), "sk": QUOTA_SK})
    item = response.get("Item") or {}
    return Quota(
        max_file_bytes=_to_int(item.get("maxFileBytes"), DEFAULT_MAX_FILE_BYTES),
        max_files_per_kb=_to_int(
            item.get("maxFilesPerKb"), DEFAULT_MAX_FILES_PER_KB
        ),
        max_knowledge_bases=_to_int(
            item.get("maxKnowledgeBases"), DEFAULT_MAX_KNOWLEDGE_BASES
        ),
        max_files_per_user=_to_int(
            item.get("maxFilesPerUser"), DEFAULT_MAX_FILES_PER_USER
        ),
        max_storage_bytes=_to_int(
            item.get("maxStorageBytes"), DEFAULT_MAX_STORAGE_BYTES
        ),
        kb_count=_to_int(item.get("kbCount"), 0),
        file_count=_to_int(item.get("fileCount"), 0),
        storage_bytes=_to_int(item.get("storageBytes"), 0),
    )


def adjust_counters(
    sub: str,
    *,
    kb_count: int = 0,
    file_count: int = 0,
    storage_bytes: int = 0,
) -> None:
    """Atomically add deltas to the user's counters (``ADD``)."""
    if not (kb_count or file_count or storage_bytes):
        return
    values: dict[str, Any] = {}
    updates: list[str] = []
    if kb_count:
        updates.append("kbCount :kb")
        values[":kb"] = kb_count
    if file_count:
        updates.append("fileCount :files")
        values[":files"] = file_count
    if storage_bytes:
        updates.append("storageBytes :storage")
        values[":storage"] = storage_bytes
    values[":updated"] = now_iso()
    table().update_item(
        Key={"pk": user_pk(sub), "sk": QUOTA_SK},
        UpdateExpression="SET updatedAt = :updated ADD " + ", ".join(updates),
        ExpressionAttributeValues=values,
    )

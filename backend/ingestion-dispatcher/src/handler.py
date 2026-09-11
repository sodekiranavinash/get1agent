from __future__ import annotations

import json
import os
import uuid
from typing import Any

import boto3

DERIVED_SEGMENT = ".derived"


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except (ValueError, TypeError):
        return False


def _parse_key(key: str) -> dict[str, str] | None:
    """Original uploads look like ``{user}/{kb}/{doc}/{filename}``."""
    if not key:
        return None
    parts = key.split("/", 3)
    if len(parts) != 4:
        return None
    user_id, kb_id, doc_id, file_name = parts
    if not (_is_uuid(user_id) and _is_uuid(kb_id) and _is_uuid(doc_id)):
        return None
    if file_name.startswith(".") or DERIVED_SEGMENT in parts:
        return None
    return {
        "userId": user_id,
        "knowledgeBaseId": kb_id,
        "documentId": doc_id,
        "fileName": file_name,
    }


def _detail(body: str) -> dict[str, str] | None:
    try:
        event = json.loads(body)
    except (TypeError, ValueError):
        return None
    if event.get("source") != "aws.s3" or event.get("detail-type") != "Object Created":
        return None
    detail = event.get("detail") or {}
    bucket = (detail.get("bucket") or {}).get("name")
    obj = detail.get("object") or {}
    key = obj.get("key")
    if not bucket or not key:
        return None
    return {
        "bucket": bucket,
        "key": key,
        "etag": str(obj.get("etag") or "").strip('"') or "unknown",
    }


def lambda_handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    state_machine_arn = os.environ.get("STATE_MACHINE_ARN")
    if not state_machine_arn:
        raise RuntimeError("STATE_MACHINE_ARN is not set")

    client = boto3.client(
        "stepfunctions", region_name=os.environ.get("AWS_REGION")
    )
    failures: list[dict[str, str]] = []

    for record in event.get("Records", []):
        message_id = str(record.get("messageId") or "")
        try:
            detail = _detail(record.get("body") or "")
            if detail is None:
                continue
            parsed = _parse_key(detail["key"])
            if parsed is None:
                continue

            payload = {
                **parsed,
                "s3Key": detail["key"],
                "contentHash": detail["etag"],
            }
            execution_name = f"ingest-{parsed['documentId']}-{detail['etag']}"
            try:
                client.start_execution(
                    stateMachineArn=state_machine_arn,
                    name=execution_name,
                    input=json.dumps(payload),
                )
            except client.exceptions.ExecutionAlreadyExists:
                print(f"ingestion execution already exists: {execution_name}")
        except Exception as exc:  # noqa: BLE001 - report for SQS retry
            print(f"dispatcher failed for message {message_id}: {exc}")
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}

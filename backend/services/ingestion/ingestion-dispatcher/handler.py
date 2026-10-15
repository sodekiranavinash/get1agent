from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

import boto3


def _execution_token(etag: str, event_id: str) -> str:
    """Stable per-object-event token for the Step Functions execution name.

    A STANDARD state machine keeps execution names unique for 90 days, so a
    re-upload of the same content must produce a new name or it would be
    silently ignored. The EventBridge event id changes on every upload, while
    redeliveries of the same SQS message keep it — so this is both
    re-upload-friendly and idempotent.
    """
    seed = f"{etag}:{event_id}".encode()
    return hashlib.sha256(seed).hexdigest()[:12]


def _log(level: str, message: str, **fields: Any) -> None:
    print(
        json.dumps({"level": level, "message": message, **fields}, default=str),
        flush=True,
    )


#: The id shape the pipeline routes on. Ordinary uploads use a uuid4 for both the
#: knowledge-base and the document id, but AI Assistant's reserved platform scope
#: deliberately uses fixed, human-readable ids (``kb_platform_docs_0001``,
#: ``ai-assistant-<slug>``) — so requiring a UUID dropped every platform document
#: on the floor. The S3 event fired, SQS delivered, this function was invoked and
#: returned success, and nothing was ever ingested: the corpus uploaded cleanly and
#: stayed ``processing`` until the watchdog failed it.
#:
#: The shape test is only a junk filter — no slashes, no traversal, bounded length.
#: Whether a document is real is decided by the extract stage, which reads the
#: document item; this function is a router, not the authority.
#:
#: The bound is 128 because a platform document id is ``ai-assistant-`` + a
#: 58-character slug = 71: a 64-character cap (the first version of this fix) refused
#: eight of the 47 corpus documents for their *length* alone, silently, exactly as
#: the UUID test had refused all 47.
_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")

#: Step Functions rejects an execution name longer than this.
_MAX_EXECUTION_NAME = 80


def _is_routable_id(value: str) -> bool:
    return bool(_ID_PATTERN.match(value))


def _execution_name(document_id: str, token: str) -> str:
    """A unique, <=80-character execution name.

    The token is what makes the name unique (and what makes a re-upload run at all,
    since a STANDARD state machine ignores a repeated name for 90 days), so the
    document id is what gets truncated. Un-truncated, a corpus document is
    ``ingest-`` + 71 + ``-`` + 12 = 91 characters, and ``start_execution`` raises
    ValidationException — the document is never ingested.
    """
    suffix = f"-{token}"
    return f"ingest-{document_id}"[: _MAX_EXECUTION_NAME - len(suffix)] + suffix


def _parse_key(key: str) -> dict[str, str] | None:
    """Original uploads look like ``raw/{user}/{kb}/{doc}/{filename}``.

    Only the ``raw/`` prefix triggers ingestion; derived and index writes live
    under other prefixes and never reach this function.
    """
    if not key:
        return None
    parts = key.split("/", 4)
    if len(parts) != 5 or parts[0] != "raw":
        return None
    _, user_id, kb_id, doc_id, file_name = parts
    if not (_is_routable_id(kb_id) and _is_routable_id(doc_id)):
        return None
    if not user_id or not file_name or file_name.startswith("."):
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
        "eventId": str(event.get("id") or obj.get("sequencer") or ""),
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
                # Never silent: a `raw/` key that reaches this function and is not
                # routed is a bug in the key layout or in the shape test, and the
                # symptom is otherwise a document that stays `processing` forever
                # with nothing in the logs to explain it.
                _log(
                    "warning",
                    "ignoring a raw/ key that does not look like an upload",
                    key=detail["key"],
                    messageId=message_id,
                )
                continue

            payload = {
                **parsed,
                "s3Key": detail["key"],
                "contentHash": detail["etag"],
            }
            execution_name = _execution_name(
                parsed["documentId"], _execution_token(detail["etag"], detail["eventId"])
            )
            try:
                client.start_execution(
                    stateMachineArn=state_machine_arn,
                    name=execution_name,
                    input=json.dumps(payload),
                )
                _log(
                    "info",
                    "started ingestion execution",
                    executionName=execution_name,
                    documentId=parsed["documentId"],
                    knowledgeBaseId=parsed["knowledgeBaseId"],
                )
            except client.exceptions.ExecutionAlreadyExists:
                _log(
                    "info",
                    "ingestion execution already exists",
                    executionName=execution_name,
                    documentId=parsed["documentId"],
                )
        except Exception as exc:  # noqa: BLE001 - report for SQS retry
            _log(
                "error",
                f"dispatcher failed: {exc}",
                messageId=message_id,
            )
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}

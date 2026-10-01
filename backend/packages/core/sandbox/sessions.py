"""DynamoDB-backed registry mapping a user (+ conversation) to a sandbox session.

AgentCore Code Interpreter sessions are isolated microVMs with a fixed TTL.
Reusing them keeps the number of sandboxes (and their cost) bounded, so this
module stores one row per ``(user, conversation)`` with an ``expiresAt`` TTL
attribute that DynamoDB deletes automatically.

Concurrency is handled two ways:

* a deterministic ``clientToken`` (``uuid5`` of user+conversation+TTL bucket) so
  two simultaneous Lambda invocations asking for the same sandbox get the *same*
  AgentCore session, and
* a conditional ``put_item`` so only one invocation wins the registry row.
"""

from __future__ import annotations

import hashlib
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any

_TOKEN_NAMESPACE = uuid.UUID("6f1c2f7a-2f0f-4d0e-9d3f-2b6a9c1e5a10")

DEFAULT_THREAD = "default"

_THREAD_RE = re.compile(r"[^A-Za-z0-9_.:-]+")

# Local (Floci) session registry. AgentCore is not emulated, so session reuse is
# tracked in-process to mirror the AgentCore/DynamoDB behaviour. It is warm
# container state only, which is enough to exercise the reuse path locally.
_LOCAL_SESSIONS: dict[str, int] = {}


@dataclass(frozen=True)
class SessionRef:
    """A resolved sandbox session."""

    session_id: str
    reused: bool


def _now() -> int:
    return int(time.time())


def partition_key(sub: str) -> str:
    return f"USER#{sub}"


def sort_key(thread: str, prefix: str = "CONV#") -> str:
    return f"{prefix}{thread}"


def sanitize_thread(conversation_id: str | None) -> str:
    """Coerce a caller-supplied conversation id into a safe session key."""
    raw = str(conversation_id or "").strip()
    if not raw:
        return DEFAULT_THREAD
    cleaned = _THREAD_RE.sub("-", raw)[:64].strip("-")
    return cleaned or DEFAULT_THREAD


def deterministic_token(sub: str, thread: str, now: int, ttl: int) -> str:
    """A stable idempotency token for a (user, conversation, TTL window)."""
    bucket = now // max(int(ttl), 1)
    return str(uuid.uuid5(_TOKEN_NAMESPACE, f"{sub}:{thread}:{bucket}"))


def local_resolve(
    sub: str, thread: str, ttl: int, now: int, namespace: str = ""
) -> "SessionRef":
    """Resolve an in-memory session for ``*_MODE=local``."""
    key = f"{namespace}:{sub}:{thread}" if namespace else f"{sub}:{thread}"
    session_id = "local-" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    expiry = _LOCAL_SESSIONS.get(key)
    if expiry and expiry > now:
        return SessionRef(session_id, reused=True)
    _LOCAL_SESSIONS[key] = now + int(ttl)
    return SessionRef(session_id, reused=False)


class SessionStore:
    """Thin DynamoDB wrapper (lazily creates its client so imports stay cheap)."""

    def __init__(self, table_name: str, region: str | None = None) -> None:
        self._table_name = table_name
        self._region = region
        self._table: Any = None

    def _get_table(self) -> Any:
        if self._table is None:
            import os

            import boto3

            kwargs: dict[str, Any] = {"region_name": self._region}
            endpoint = os.environ.get("DYNAMODB_ENDPOINT_URL")
            if endpoint:
                kwargs["endpoint_url"] = endpoint
            self._table = boto3.resource("dynamodb", **kwargs).Table(self._table_name)
        return self._table

    def get(self, pk: str, sk: str) -> dict[str, Any] | None:
        response = self._get_table().get_item(Key={"pk": pk, "sk": sk})
        return response.get("Item")

    def claim(self, item: dict[str, Any], now: int) -> bool:
        """Atomically write the row unless a live session already owns it."""
        from botocore.exceptions import ClientError

        try:
            self._get_table().put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) OR expiresAt <= :now",
                ExpressionAttributeValues={":now": now},
            )
            return True
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return False
            raise

    def touch(self, pk: str, sk: str, now: int) -> None:
        try:
            self._get_table().update_item(
                Key={"pk": pk, "sk": sk},
                UpdateExpression="SET lastUsedAt = :now",
                ExpressionAttributeValues={":now": now},
            )
        except Exception:  # noqa: BLE001 - best effort, never fail a request
            pass

    def delete(self, pk: str, sk: str) -> None:
        try:
            self._get_table().delete_item(Key={"pk": pk, "sk": sk})
        except Exception:  # noqa: BLE001 - best effort
            pass

    def list_active(self, pk: str, now: int) -> list[dict[str, Any]]:
        response = self._get_table().query(
            KeyConditionExpression="pk = :pk",
            FilterExpression="expiresAt > :now",
            ExpressionAttributeValues={":pk": pk, ":now": now},
        )
        return list(response.get("Items", []))


def new_item(pk: str, sk: str, session_id: str, ttl: int, now: int) -> dict[str, Any]:
    return {
        "pk": pk,
        "sk": sk,
        "sessionId": session_id,
        "expiresAt": now + int(ttl),
        "createdAt": now,
        "lastUsedAt": now,
    }

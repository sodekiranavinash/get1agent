"""Support conversations and one-way security reports.

Two related concerns live here, both small and metadata-only in DynamoDB:

* **Support** is a conversation between a user and the admins. A ticket's
  metadata is one item (``USER#<userId>`` / ``SUPPORT#<ticketId>``, projected
  onto GSI3 under ``SUPPORT#all`` for the admin inbox); its messages are
  separate items in their own partition (``SUPPORT#<ticketId>`` /
  ``MSG#<createdAt>#<seq>``) so a long thread never grows a single item.

* **Security reports** are one-way: the user describes an issue, the admins
  read it. One item per report (``USER#<userId>`` / ``SREPORT#<reportId>``,
  projected onto GSI3 under ``SREPORT#all``).

Neither ever holds blobs; bodies are capped by the API layer.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from data.client import now_iso, table
from data.keys import (
    GSI3,
    SECURITY_ALL_PK,
    SECURITY_REPORT_PREFIX,
    SUPPORT_ALL_PK,
    SUPPORT_PREFIX,
    security_all_sk,
    security_report_sk,
    support_all_sk,
    support_message_sk,
    support_partition_pk,
    support_ticket_sk,
    user_pk,
)

# --- limits (enforced by the API layer, kept here as the source of truth) -----

MAX_SUBJECT = 160
MAX_BODY = 8000
MAX_URL = 2000
MAX_PAGE = 160

TICKET_OPEN = "open"
TICKET_CLOSED = "closed"
TICKET_STATUSES = (TICKET_OPEN, TICKET_CLOSED)

# A ticket is ordinary support, or a formal data-rights grievance (DPDP). The
# kind lets the user filter their own list and the admins triage separately.
KIND_SUPPORT = "support"
KIND_GRIEVANCE = "grievance"

REPORT_NEW = "new"
REPORT_RESOLVED = "resolved"
REPORT_STATUSES = (REPORT_NEW, REPORT_RESOLVED)

AUTHOR_USER = "user"
AUTHOR_ADMIN = "admin"

# How much of the latest message to keep as a list preview.
_PREVIEW_CHARS = 240

_INDEX = "byStatus"


def _new_id() -> str:
    return uuid4().hex[:16]


def _preview(text: str) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= _PREVIEW_CHARS:
        return collapsed
    return collapsed[: _PREVIEW_CHARS - 1].rstrip() + "…"


# --- support ------------------------------------------------------------------


def _put_message(
    ticket_id: str,
    *,
    author: str,
    author_name: str,
    body: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    timestamp = created_at or now_iso()
    message: dict[str, Any] = {
        "pk": support_partition_pk(ticket_id),
        "sk": support_message_sk(timestamp, uuid4().hex[:8]),
        "entity": "supportMessage",
        "messageId": _new_id(),
        "ticketId": ticket_id,
        "author": author,
        "authorName": author_name,
        "body": body,
        "createdAt": timestamp,
    }
    table().put_item(Item=message)
    return message


def create_ticket(
    user_id: str,
    *,
    user_email: str,
    subject: str,
    body: str,
    kind: str = KIND_SUPPORT,
    request_type: str | None = None,
) -> dict[str, Any]:
    """Open a ticket with its first (user) message."""
    timestamp = now_iso()
    ticket_id = _new_id()
    ticket: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": support_ticket_sk(ticket_id),
        "entity": "supportTicket",
        "ticketId": ticket_id,
        "userId": user_id,
        "userEmail": user_email,
        "subject": subject,
        "kind": kind,
        "status": TICKET_OPEN,
        "messageCount": 1,
        "lastAuthor": AUTHOR_USER,
        "lastMessage": _preview(body),
        "createdAt": timestamp,
        "updatedAt": timestamp,
        GSI3[0]: SUPPORT_ALL_PK,
        GSI3[1]: support_all_sk(timestamp, ticket_id),
    }
    if request_type:
        ticket["requestType"] = request_type
    table().put_item(Item=ticket)
    _put_message(
        ticket_id,
        author=AUTHOR_USER,
        author_name=user_email or user_id,
        body=body,
        created_at=timestamp,
    )
    return ticket


def add_message(
    user_id: str,
    ticket_id: str,
    *,
    author: str,
    author_name: str,
    body: str,
) -> dict[str, Any]:
    """Append a message and bump the ticket's recency (user or admin)."""
    timestamp = now_iso()
    table().update_item(
        Key={"pk": user_pk(user_id), "sk": support_ticket_sk(ticket_id)},
        UpdateExpression=(
            "SET updatedAt = :u, lastAuthor = :a, lastMessage = :m, "
            f"{GSI3[0]} = :g, {GSI3[1]} = :s "
            "ADD messageCount :one"
        ),
        ExpressionAttributeValues={
            ":u": timestamp,
            ":a": author,
            ":m": _preview(body),
            ":g": SUPPORT_ALL_PK,
            ":s": support_all_sk(timestamp, ticket_id),
            ":one": 1,
        },
    )
    return _put_message(
        ticket_id,
        author=author,
        author_name=author_name,
        body=body,
        created_at=timestamp,
    )


def get_ticket(user_id: str, ticket_id: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": user_pk(user_id), "sk": support_ticket_sk(ticket_id)}
    )
    return response.get("Item")


def list_tickets(user_id: str) -> list[dict[str, Any]]:
    """A user's own tickets, most recently updated first (base-table Query)."""
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": SUPPORT_PREFIX,
        },
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: item.get("updatedAt", ""), reverse=True)


def list_messages(ticket_id: str) -> list[dict[str, Any]]:
    """One thread's messages, oldest first."""
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": support_partition_pk(ticket_id),
            ":prefix": "MSG#",
        },
        "ScanIndexForward": True,
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return items


def set_ticket_status(user_id: str, ticket_id: str, status: str) -> dict[str, Any] | None:
    timestamp = now_iso()
    table().update_item(
        Key={"pk": user_pk(user_id), "sk": support_ticket_sk(ticket_id)},
        UpdateExpression="SET #status = :status, updatedAt = :u",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":status": status, ":u": timestamp},
    )
    return get_ticket(user_id, ticket_id)


def list_all_tickets(
    limit: int = 25, exclusive_start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Admin inbox: every ticket, newest activity first (GSI3, never a Scan)."""
    kwargs: dict[str, Any] = {
        "IndexName": _INDEX,
        "KeyConditionExpression": f"{GSI3[0]} = :pk",
        "ExpressionAttributeValues": {":pk": SUPPORT_ALL_PK},
        "ScanIndexForward": False,
        "Limit": max(1, min(int(limit), 100)),
    }
    if exclusive_start_key:
        kwargs["ExclusiveStartKey"] = exclusive_start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")


# --- security reports ---------------------------------------------------------


def create_security_report(
    user_id: str,
    *,
    user_email: str,
    url: str,
    page: str,
    body: str,
) -> dict[str, Any]:
    timestamp = now_iso()
    report_id = _new_id()
    report: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": security_report_sk(report_id),
        "entity": "securityReport",
        "reportId": report_id,
        "userId": user_id,
        "userEmail": user_email,
        "url": url,
        "page": page,
        "body": body,
        "status": REPORT_NEW,
        "createdAt": timestamp,
        "updatedAt": timestamp,
        GSI3[0]: SECURITY_ALL_PK,
        GSI3[1]: security_all_sk(timestamp, report_id),
    }
    table().put_item(Item=report)
    return report


def get_security_report(user_id: str, report_id: str) -> dict[str, Any] | None:
    response = table().get_item(
        Key={"pk": user_pk(user_id), "sk": security_report_sk(report_id)}
    )
    return response.get("Item")


def list_security_reports(user_id: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    kwargs: dict[str, Any] = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :prefix)",
        "ExpressionAttributeValues": {
            ":pk": user_pk(user_id),
            ":prefix": SECURITY_REPORT_PREFIX,
        },
    }
    while True:
        response = table().query(**kwargs)
        items.extend(response.get("Items") or [])
        if "LastEvaluatedKey" not in response:
            break
        kwargs["ExclusiveStartKey"] = response["LastEvaluatedKey"]
    return sorted(items, key=lambda item: item.get("createdAt", ""), reverse=True)


def set_report_status(
    user_id: str, report_id: str, status: str
) -> dict[str, Any] | None:
    timestamp = now_iso()
    table().update_item(
        Key={"pk": user_pk(user_id), "sk": security_report_sk(report_id)},
        UpdateExpression="SET #status = :status, updatedAt = :u",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues={":status": status, ":u": timestamp},
    )
    return get_security_report(user_id, report_id)


def list_all_security_reports(
    limit: int = 25, exclusive_start_key: dict[str, Any] | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Admin inbox: every security report, newest first (GSI3, never a Scan)."""
    kwargs: dict[str, Any] = {
        "IndexName": _INDEX,
        "KeyConditionExpression": f"{GSI3[0]} = :pk",
        "ExpressionAttributeValues": {":pk": SECURITY_ALL_PK},
        "ScanIndexForward": False,
        "Limit": max(1, min(int(limit), 100)),
    }
    if exclusive_start_key:
        kwargs["ExclusiveStartKey"] = exclusive_start_key
    response = table().query(**kwargs)
    return response.get("Items") or [], response.get("LastEvaluatedKey")

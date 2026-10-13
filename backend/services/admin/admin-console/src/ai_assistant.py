"""Admin → AI Assistant routes (``/v1/admin/ai-assistant/*``).

The admin surface for the in-product assistant: the kill switch and the model
pickers, the rate limits, the feedback table, the AI Assistant traces and conversations,
the evaluation history and the platform corpus status.

Two deliberate design points:

* **AI Assistant data is owner-scoped, like everything else in the table.** AI Assistant feedback,
  traces and conversations key off ``USER#<userId>`` with an AI Assistant prefix, so the
  admin view takes a ``userId`` and issues one Query — it never Scans. The
  operator reaches it from the admin users list or from a conversation.
* **This module is configuration and reporting only.** Starting an evaluation run
  is delegated to the evaluation worker (the same background-invocation pattern
  the Playground uses), because a real run outlives API Gateway's 30 s cap.

Routes:
    GET    /v1/admin/ai-assistant                              config + catalogue + defaults
    POST   /v1/admin/ai-assistant                              update config
    GET    /v1/admin/ai-assistant/feedback?userId=&value=      one user's feedback
    DELETE /v1/admin/ai-assistant/feedback/{userId}/{runId}    remove one feedback item
    GET    /v1/admin/ai-assistant/traces?userId=               one user's AI Assistant traces
    GET    /v1/admin/ai-assistant/traces/{userId}/{traceId}    one observation tree
    GET    /v1/admin/ai-assistant/conversations?userId=        one user's conversations
    GET    /v1/admin/ai-assistant/conversations/{userId}/{id}  one transcript
    GET    /v1/admin/ai-assistant/evaluations?userId=          evaluation run history
    GET    /v1/admin/ai-assistant/knowledge                    platform corpus status
"""

from __future__ import annotations

import json
from typing import Any

from data.repositories import ai_assistant as ai_assistant_repo
from data.repositories import ai_assistant_settings

#: Fields an operator may change. Anything else is rejected rather than stored, so
#: a typo cannot add junk attributes to the settings item.
EDITABLE = tuple(ai_assistant_settings.FIELDS)


def _json(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json", "cache-control": "no-store"},
        "body": json.dumps(body, default=str),
    }


def _actor(claims: dict[str, Any]) -> str:
    return str(
        claims.get("name")
        or claims.get("https://get1agent.com/email")
        or claims.get("email")
        or "admin"
    )


def _int(raw: Any, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def _scoped(
    what: str, user_id: str, render: Any
) -> dict[str, Any]:
    """Run an owner-scoped read, or explain what the operator must supply."""
    user_id = str(user_id or "").strip()
    if not user_id:
        return _json(
            200,
            {
                "items": [],
                "note": f"AI Assistant {what} are owner-scoped. Pass userId=<internal id> — "
                "open it from a user in the Users list.",
            },
        )
    items, cursor = render(user_id)
    return _json(200, {"items": items, "cursor": cursor, "userId": user_id})


def route(
    claims: dict[str, Any],
    method: str,
    segments: list[str],
    body: dict[str, Any],
    query: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Dispatch an ``/v1/admin/ai-assistant/*`` request; ``None`` when unmatched."""
    query = query or {}
    rest = segments[3:]
    if not rest:
        return _settings(claims, method, body)

    head, tail = rest[0], rest[1:]
    user_id = str(query.get("userId") or body.get("userId") or "")

    if head == "feedback":
        return _feedback(method, tail, body, user_id, query)
    if head == "traces":
        if tail:
            return _trace(tail[0], tail[1] if len(tail) > 1 else "")
        return _scoped(
            "traces", user_id, lambda uid: ai_assistant_repo.list_traces(uid, limit=50)
        )
    if head == "conversations":
        if tail:
            user_id = tail[0]
            conversation_id = tail[1] if len(tail) > 1 else ""
            return _conversation(user_id, conversation_id)
        return _scoped(
            "conversations", user_id, lambda uid: ai_assistant_repo.list_conversations(uid, limit=50)
        )
    if head == "evaluations":
        return _scoped(
            "evaluation runs", user_id, lambda uid: ai_assistant_repo.list_eval_runs(uid, limit=20)
        )
    if head == "knowledge":
        return _knowledge(method)
    return _json(404, {"error": "Not found"})


# --- config -------------------------------------------------------------------


def _settings(
    claims: dict[str, Any], method: str, body: dict[str, Any]
) -> dict[str, Any]:
    if method == "GET":
        return _json(200, {**ai_assistant_settings.snapshot(), "editable": list(EDITABLE)})
    if method != "POST":
        return _json(405, {"error": f"Method not allowed: {method}"})

    patch = {field: body[field] for field in EDITABLE if field in body}
    if not patch:
        return _json(400, {"error": f"provide at least one of: {', '.join(EDITABLE)}"})
    try:
        updated = ai_assistant_settings.update_settings(patch, updated_by=_actor(claims))
    except ValueError as exc:
        return _json(400, {"error": str(exc)})
    return _json(200, {"settings": updated, "updatedBy": _actor(claims)})


# --- feedback -----------------------------------------------------------------


def _feedback(
    method: str,
    tail: list[str],
    body: dict[str, Any],
    user_id: str,
    query: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if method == "GET":
        # Filters ride in the query string (`?value=up&limit=20`); the body is
        # accepted too so a POST-style client keeps working.
        params = {**(body or {}), **(query or {})}
        return _scoped(
            "feedback",
            user_id,
            lambda uid: ai_assistant_repo.list_feedback(
                uid,
                limit=_int(params.get("limit"), 50, minimum=1, maximum=100),
                value=(str(params.get("value") or "") or None),
            ),
        )
    if method == "DELETE":
        # /v1/admin/ai-assistant/feedback/{userId}/{runId}
        if len(tail) >= 2:
            user_id, run_id = tail[0], tail[1]
        else:
            run_id = str(body.get("runId") or "")
        if not user_id or not run_id:
            return _json(400, {"error": "userId and runId are required"})
        ai_assistant_repo.delete_feedback(user_id, run_id)
        return _json(200, {"deleted": True})
    return _json(405, {"error": f"Method not allowed: {method}"})


# --- traces and conversations -------------------------------------------------


def _trace(user_id: str, trace_id: str) -> dict[str, Any]:
    if not user_id or not trace_id:
        return _json(400, {"error": "userId and traceId are required"})
    item = ai_assistant_repo.get_trace(user_id, trace_id)
    if not item:
        return _json(404, {"error": "Trace not found"})
    return _json(200, item)


def _conversation(user_id: str, conversation_id: str) -> dict[str, Any]:
    if not user_id or not conversation_id:
        return _json(400, {"error": "userId and conversationId are required"})
    item = ai_assistant_repo.get_conversation(user_id, conversation_id)
    if not item:
        return _json(404, {"error": "Conversation not found"})
    transcript = ai_assistant_repo.get_transcript(user_id, conversation_id)
    return _json(200, {"conversation": item, "turns": transcript.get("turns") or []})


# --- knowledge ----------------------------------------------------------------


def _knowledge(method: str) -> dict[str, Any]:
    """The platform corpus status: how many documents are indexed and ready."""
    if method != "GET":
        return _json(405, {"error": f"Method not allowed: {method}"})
    return _json(200, _knowledge_payload())


def _knowledge_payload() -> dict[str, Any]:
    """Read the reserved scope's documents so an operator can see the corpus."""
    import os  # noqa: PLC0415 - only needed on this admin path

    from data.repositories import documents as docs_repo

    scope = str(os.environ.get("AI_ASSISTANT_SCOPE") or "platform").strip()
    kb_id = str(os.environ.get("AI_ASSISTANT_KB_ID") or "kb_platform_docs_0001").strip()
    rebuild = "make ai-assistant-knowledge && make ai-assistant-upload"
    try:
        items = docs_repo.list_documents(kb_id)
    except Exception as exc:  # noqa: BLE001 - report status, never fail the page
        return {
            "scope": scope,
            "kbId": kb_id,
            "count": 0,
            "statuses": {},
            "documents": [],
            "error": str(exc)[:300],
            "rebuildCommand": rebuild,
        }

    statuses: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1

    return {
        "scope": scope,
        "kbId": kb_id,
        "count": len(items),
        "statuses": statuses,
        "documents": [
            {
                "fileName": item.get("fileName"),
                "status": item.get("status"),
                "chunkCount": item.get("chunkCount"),
                "updatedAt": item.get("updatedAt"),
            }
            for item in items[:200]
        ],
        "rebuildCommand": rebuild,
    }

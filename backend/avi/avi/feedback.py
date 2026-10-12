"""Avi feedback (signed-in callers only).

An Avi feedback item is deliberately richer than the platform's agent feedback:
it carries the question that produced the answer, a preview of the answer, the
sources used, the classifier's verdict, and the cost and latency of the turn. The
reason is operational — the admin table must be able to answer *"which questions
do people rate badly, and was it a content problem or a routing problem?"* without
joining three other stores.

Guests have no account to attach feedback to, and the guest path stores nothing,
so feedback from a guest is accepted and discarded (`stored: false`).

The body → item normalizer lives in ``data.repositories.avi.record_feedback`` and
is **shared with user-api**, which owns the route the browser actually calls
(`POST /v1/avi/feedback`): the browser cannot mint the MicroVM ingress token, so
the agent service's own ``POST /feedback`` is only reachable from inside the
MicroVM. Two normalizers would drift; there is one.
"""

from __future__ import annotations

from typing import Any

from data.repositories import avi as avi_repo


def record_feedback(user_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Store one thumb, with everything the admin table needs to explain it."""
    return avi_repo.record_feedback(user_id, body)


def list_feedback(
    user_id: str, *, limit: int = 50, value: str | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    """A user's Avi feedback, newest first (the admin page's table)."""
    items, cursor = avi_repo.list_feedback(user_id, limit=limit, value=value)
    return items, avi_repo.encode_cursor(cursor)


def delete_feedback(user_id: str, run_id: str) -> None:
    avi_repo.delete_feedback(user_id, run_id)

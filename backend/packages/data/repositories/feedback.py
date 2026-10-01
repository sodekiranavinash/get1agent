"""Per-run user feedback (thumbs + comment) on agent runs.

One small item per run (``USER#<userId>`` / ``FEEDBACK#<runId>``). Feedback is
addressed by the run id (unique per turn) so it works the same in the chat and
the builder history. The API layer mirrors it to Langfuse as a score.
"""

from __future__ import annotations

from typing import Any

from data.client import now_iso, table
from data.keys import feedback_sk, user_pk

VALUE_UP = "up"
VALUE_DOWN = "down"
VALUES = (VALUE_UP, VALUE_DOWN)

MAX_COMMENT = 2000
MAX_CATEGORIES = 12


def upsert_feedback(
    user_id: str,
    run_id: str,
    *,
    value: str,
    comment: str = "",
    categories: list[str] | None = None,
    trace_id: str | None = None,
    conversation_id: int | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "pk": user_pk(user_id),
        "sk": feedback_sk(run_id),
        "entity": "feedback",
        "runId": run_id,
        "value": value,
        "comment": comment,
        "categories": categories or [],
        "updatedAt": now_iso(),
    }
    if trace_id:
        item["traceId"] = trace_id
    if conversation_id is not None:
        item["conversationId"] = conversation_id
    if agent_id:
        item["agentId"] = agent_id
    table().put_item(Item=item)
    return item


def delete_feedback(user_id: str, run_id: str) -> None:
    table().delete_item(Key={"pk": user_pk(user_id), "sk": feedback_sk(run_id)})


def get_feedback_many(user_id: str, run_ids: list[str]) -> dict[str, dict[str, Any]]:
    """BatchGet feedback for many runs (max 100 keys per request)."""
    found: dict[str, dict[str, Any]] = {}
    unique = [run_id for run_id in dict.fromkeys(run_ids) if run_id]
    for start in range(0, len(unique), 100):
        batch = unique[start : start + 100]
        response = table().meta.client.batch_get_item(
            RequestItems={
                table().table_name: {
                    "Keys": [
                        {"pk": user_pk(user_id), "sk": feedback_sk(run_id)}
                        for run_id in batch
                    ],
                }
            }
        )
        for item in response.get("Responses", {}).get(table().table_name, []):
            found[item["runId"]] = item
    return found

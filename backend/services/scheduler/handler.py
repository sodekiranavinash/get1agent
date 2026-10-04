"""Scheduled agent/workflow runs.

EventBridge fires this once a minute. It reads every due schedule from the
sparse GSI3 (``SCHEDULES#enabled``) — one range query across all users, never a
Scan — and for each one:

1. creates a conversation (so the run shows up in the chat sidebar / history);
2. runs the agent or workflow as the platform service (``core.agent_runner``);
3. records ``lastRunAt`` and the next firing time.

One schedule failing never blocks the others.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from data.client import now_iso
from data.repositories import agents as agents_repo
from data.repositories import conversations as conversations_repo
from data.repositories import notifications as notifications_repo
from data.repositories import schedules as schedules_repo
from data.repositories import workflows as workflows_repo


def _notify(user_id: str, *, kind: str, title: str, detail: str, link: str | None) -> None:
    """Best-effort user notification for a scheduled run."""
    if not user_id:
        return
    try:
        notifications_repo.create_notification(
            user_id, kind=kind, title=title, detail=detail, link=link
        )
    except Exception:  # noqa: BLE001 - notifications are best effort
        pass


def _input_text(schedule: dict[str, Any]) -> str:
    payload = schedule.get("payload")
    if isinstance(payload, dict):
        query = str(payload.get("query") or "").strip()
        if query:
            return query
    return f"Run the scheduled task for {schedule.get('name') or 'this target'}."


def _mark_entity(user_id: str, kind: str, target_id: str, ran_at: str) -> None:
    """Stamp the entity's ``lastRunAt`` so the Schedules page reflects the run."""
    try:
        if kind == "workflow":
            workflows_repo.mark_run(user_id, target_id, run_at=ran_at)
        else:
            agents_repo.mark_run(user_id, target_id, run_at=ran_at)
    except Exception:  # noqa: BLE001 - the registry already recorded the run
        pass


def _run_schedule(schedule: dict[str, Any]) -> dict[str, Any]:
    user_id = str(schedule.get("userId") or "")
    kind = str(schedule.get("kind") or "agent")
    target_id = str(schedule.get("targetId") or "")
    name = str(schedule.get("name") or target_id)
    if not (user_id and target_id):
        return {"ok": False, "error": "schedule is missing userId/targetId"}

    ran_at = now_iso()
    try:
        # A fresh conversation per run, so each scheduled execution is a readable
        # transcript the user can open in chat.
        conversation = conversations_repo.create_conversation(
            user_id=user_id,
            agent_id=target_id,
            agent_name=name,
            kind=conversations_repo.KIND_RUN,
            title=f"Scheduled · {name}",
            target_type=kind,
        )
        from core import agent_runner

        result = agent_runner.run_turn(
            user_id=user_id,
            target_id=target_id,
            target_type=kind,
            input_text=_input_text(schedule),
            conversation_id=conversation["conversationId"],
        )
        schedules_repo.record_run(
            user_id,
            kind,
            target_id,
            ran_at=ran_at,
            status="completed",
            error=str(result.get("error") or ""),
        )
        _mark_entity(user_id, kind, target_id, ran_at)
        error_text = str(result.get("error") or "")
        _notify(
            user_id,
            kind="schedule_failed" if error_text else "schedule_completed",
            title="Scheduled run failed" if error_text else "Scheduled run finished",
            detail=f"{name} · {kind}",
            link=f"/chat/conversation/{conversation['conversationId']}",
        )
        return {"ok": True, "conversationId": conversation["conversationId"]}
    except Exception as exc:  # noqa: BLE001 - one schedule must not block the rest
        print(
            json.dumps(
                {
                    "level": "error",
                    "message": "Scheduled run failed",
                    "schedule": f"{kind}#{target_id}",
                    "error": str(exc),
                }
            ),
            file=sys.stderr,
        )
        try:
            schedules_repo.record_run(
                user_id, kind, target_id, ran_at=ran_at, status="failed", error=str(exc)
            )
        except Exception:  # noqa: BLE001 - recording the failure is best effort
            pass
        _mark_entity(user_id, kind, target_id, ran_at)
        _notify(
            user_id,
            kind="schedule_failed",
            title="Scheduled run failed",
            detail=f"{name} · {kind}",
            link="/scheduled-jobs",
        )
        return {"ok": False, "error": str(exc)}


def lambda_handler(event: dict[str, Any] | None, _context: Any = None) -> dict[str, Any]:
    now = now_iso()
    try:
        due = schedules_repo.list_due(now)
    except Exception as exc:  # noqa: BLE001
        print(f"scheduler: could not list due schedules: {exc!r}", file=sys.stderr)
        traceback.print_exc()
        return {"ok": False, "error": "list failed"}

    results = [_run_schedule(item) for item in due]
    fired = sum(1 for result in results if result.get("ok"))
    print(
        json.dumps({"level": "info", "message": "scheduler tick", "due": len(due), "fired": fired})
    )
    return {"ok": True, "due": len(due), "fired": fired}

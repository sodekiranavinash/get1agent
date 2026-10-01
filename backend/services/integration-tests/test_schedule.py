"""Cron scheduling: the engine and the scheduler registry (moto DynamoDB)."""

from __future__ import annotations

from datetime import datetime, timezone

from core import schedule as cron
from data.repositories import schedules

USER = "u_7k3f9qz2mpx8n4rq"


class TestCronEngine:
    def test_daily_next_run_respects_timezone(self) -> None:
        # 09:30 New York = 13:30 UTC in winter (EST, UTC-5).
        after = datetime(2026, 1, 5, 9, 0, tzinfo=timezone.utc)
        nxt = cron.next_run_at("30 9 * * *", "America/New_York", after=after)
        assert nxt.startswith("2026-01-05T14:30")  # 09:30 EST == 14:30 UTC

    def test_weekdays_skip_the_weekend(self) -> None:
        # Saturday 2026-01-03 -> next weekday is Monday 2026-01-05.
        after = datetime(2026, 1, 3, 12, 0, tzinfo=timezone.utc)
        nxt = cron.next_run("0 9 * * 1-5", "UTC", after=after)
        assert nxt is not None
        assert (nxt.year, nxt.month, nxt.day) == (2026, 1, 5)

    def test_hourly_step_and_lists(self) -> None:
        after = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
        nxt = cron.next_run("*/15 * * * *", "UTC", after=after)
        assert nxt is not None and nxt.minute == 15
        listed = cron.next_run("5 1,13 * * *", "UTC", after=after)
        assert listed is not None and (listed.hour, listed.minute) == (1, 5)

    def test_invalid_expression(self) -> None:
        assert cron.validate("not a cron") is False
        assert cron.next_run_at("99 99 * * *", "UTC") == ""
        assert cron.next_run_at("0 9 * * 1-5", "UTC") != ""


def test_schedule_registry_lifecycle() -> None:
    # Enabling registers a due row; the next run is in the future.
    item = schedules.upsert_schedule(
        USER,
        "agent",
        "agent-1",
        name="daily",
        expression="0 9 * * *",
        timezone="UTC",
        enabled=True,
    )
    assert item is not None and item["gsi3pk"] == "SCHEDULES#enabled"
    assert item["nextRunAt"]
    assert schedules.list_due("1970-01-01T00:00:00+00:00") == []

    # A due schedule (nextRunAt <= now) is returned by the range query.
    due = schedules.list_due("2999-01-01T00:00:00+00:00")
    assert [entry["targetId"] for entry in due] == ["agent-1"]

    # Recording a run advances nextRunAt and keeps the row due-able.
    schedules.record_run(USER, "agent", "agent-1", ran_at="2026-01-01T09:00:00+00:00", status="completed")
    updated = schedules.get_schedule(USER, "agent", "agent-1")
    assert updated and updated["lastRunAt"] == "2026-01-01T09:00:00+00:00"
    assert updated["lastStatus"] == "completed"

    # Disabling removes it from the registry (sparse GSI3).
    schedules.upsert_schedule(
        USER, "agent", "agent-1", expression="0 9 * * *", enabled=False
    )
    assert schedules.get_schedule(USER, "agent", "agent-1") is None
    assert schedules.list_due("2999-01-01T00:00:00+00:00") == []


def test_workflow_schedules_are_registered_too() -> None:
    schedules.upsert_schedule(
        USER,
        "workflow",
        "wf-1",
        name="hourly",
        expression="0 * * * *",
        timezone="UTC",
        enabled=True,
    )
    due = schedules.list_due("2999-01-01T00:00:00+00:00")
    assert [entry["kind"] for entry in due] == ["workflow"]

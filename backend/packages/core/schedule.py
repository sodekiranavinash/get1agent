"""Timezone-aware 5-field cron parsing and next-run computation.

The builders store a schedule as ``{enabled, cron, timezone}``. The scheduler
needs to know when a schedule is next due and must respect the schedule's own
timezone (DST included). No third-party cron library: the expressions the UI
produces are simple, and a bounded day scan is cheap and correct.

Supported fields: ``*``, lists (``1,2,3``), ranges (``1-5``), steps
(``*/5``, ``1-30/10``), and the usual ``0-6`` weekdays (``7`` == Sunday).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from zoneinfo import ZoneInfo

MAX_DAYS = 366

_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))


class CronError(ValueError):
    """The cron expression is malformed."""


def _expand(field: str, minimum: int, maximum: int) -> set[int]:
    values: set[int] = set()
    for part in field.split(","):
        part = part.strip()
        if not part:
            raise CronError("empty cron field")
        step = 1
        if "/" in part:
            part, _, step_text = part.partition("/")
            try:
                step = int(step_text)
            except ValueError as exc:
                raise CronError(f"invalid step {step_text!r}") from exc
            if step <= 0:
                raise CronError("step must be positive")
        if part == "*":
            start, end = minimum, maximum
        elif "-" in part:
            start_text, _, end_text = part.partition("-")
            try:
                start, end = int(start_text), int(end_text)
            except ValueError as exc:
                raise CronError(f"invalid range {part!r}") from exc
        else:
            try:
                start = end = int(part)
            except ValueError as exc:
                raise CronError(f"invalid value {part!r}") from exc
        if start > end or start < minimum or end > maximum:
            raise CronError(f"value out of range: {part!r}")
        values.update(range(start, end + 1, step))
    # Cron treats 7 as Sunday.
    if maximum == 6 and 7 in values:
        values.discard(7)
        values.add(0)
    return values


class Cron:
    """A parsed 5-field cron expression."""

    def __init__(self, expression: str) -> None:
        fields = str(expression or "").split()
        if len(fields) != 5:
            raise CronError("a schedule needs a 5-field cron expression")
        self.minutes = _expand(fields[0], *_FIELD_RANGES[0])
        self.hours = _expand(fields[1], *_FIELD_RANGES[1])
        self.days = _expand(fields[2], *_FIELD_RANGES[2])
        self.months = _expand(fields[3], *_FIELD_RANGES[3])
        self.weekdays = _expand(fields[4], *_FIELD_RANGES[4])
        # Standard cron: when both day-of-month and day-of-week are restricted,
        # a day matches if EITHER matches.
        self._dom_restricted = fields[2] != "*"
        self._dow_restricted = fields[4] != "*"

    def _day_matches(self, year: int, month: int, day: int, weekday: int) -> bool:
        if month not in self.months:
            return False
        dom = day in self.days
        dow = weekday in self.weekdays
        if self._dom_restricted and self._dow_restricted:
            return dom or dow
        if self._dom_restricted:
            return dom
        if self._dow_restricted:
            return dow
        return True

    def next_run(
        self, timezone: str, *, after: datetime | None = None
    ) -> datetime | None:
        """The next firing instant (UTC), or ``None`` within a year."""
        try:
            zone = ZoneInfo(timezone or "UTC")
        except Exception:  # noqa: BLE001 - an unknown zone falls back to UTC
            zone = ZoneInfo("UTC")
        now = after or datetime.now(dt_timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=dt_timezone.utc)

        local = now.astimezone(zone)
        start_day = local.date()
        hours = sorted(self.hours)
        minutes = sorted(self.minutes)

        for offset in range(0, MAX_DAYS + 1):
            day = start_day + timedelta(days=offset)
            # A scheduling timezone with a UTC offset shift can make an instant
            # repeat; comparing full instants after the fact handles that.
            if not self._day_matches(day.year, day.month, day.day, (day.weekday() + 1) % 7):
                continue
            for hour in hours:
                for minute in minutes:
                    candidate = datetime(
                        day.year, day.month, day.day, hour, minute, tzinfo=zone
                    ).astimezone(dt_timezone.utc)
                    if candidate > now:
                        return candidate
        return None


def validate(expression: str) -> bool:
    """True when ``expression`` is a parseable 5-field cron expression."""
    try:
        Cron(expression)
        return True
    except CronError:
        return False


def next_run(
    expression: str, timezone: str, *, after: datetime | None = None
) -> datetime | None:
    """The next firing instant (UTC), or ``None`` when invalid/too far out."""
    try:
        return Cron(expression).next_run(timezone, after=after)
    except CronError:
        return None


def next_run_at(expression: str, timezone: str, *, after: datetime | None = None) -> str:
    """The next firing time as an ISO-8601 UTC string ('' when unschedulable)."""
    found = next_run(expression, timezone, after=after)
    return found.isoformat() if found else ""

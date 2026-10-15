"""Rate limiting: the burst window is what a real visitor meets.

The product promises a guest "ten questions in three minutes", and the complaint
that produced this window was the opposite: six questions an hour (the old
default) meant a visitor was told *"try again in about 16 min"* after a handful of
questions, because the shortest window was an hour.

So these tests pin the contract, not the integers:

* a guest gets **at least ten** questions inside the burst window, and the
  refusal that follows tells them to wait **under three minutes** — never most of
  an hour;
* the burst window is the *first* thing checked, so the short refusal is what a
  normal visitor sees;
* the outer windows still bound a loop (hour) and a patient script (day);
* a signed-in caller has no burst cap by default, so the "unlimited" surface does
  not become stricter than it was;
* every window at zero still means "no cap configured".
"""

from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

AI_ASSISTANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ASSISTANT))
sys.path.insert(0, str(AI_ASSISTANT.parent / "packages"))

from data.repositories import ai_assistant_settings as config_defaults  # noqa: E402
from src import limits  # noqa: E402


class _FixedWindowCounter:
    """In-memory stand-in for `core.ratelimit`'s DynamoDB counter.

    Mimics the real semantics exactly: one atomic increment per call, allowed while
    the count is within the limit for the current fixed window.
    """

    def __init__(self) -> None:
        self.counts: dict[tuple[str, str, int], int] = {}
        self.windows_asked: list[tuple[str, int]] = []

    def allow(self, user_id: str, *, kind: str, limit: int, window_seconds: int) -> bool:
        window = int(time.time() // window_seconds)
        key = (user_id, kind, window)
        self.counts[key] = self.counts.get(key, 0) + 1
        self.windows_asked.append((kind, window_seconds))
        return self.counts[key] <= limit

    def current(self, user_id: str, *, kind: str, window_seconds: int) -> int:
        window = int(time.time() // window_seconds)
        return self.counts.get((user_id, kind, window), 0)


GUEST_DEFAULTS = {
    "guestPerBurst": config_defaults.DEFAULT_GUEST_PER_BURST,
    "guestPerHour": config_defaults.DEFAULT_GUEST_PER_HOUR,
    "guestPerDay": config_defaults.DEFAULT_GUEST_PER_DAY,
}
USER_DEFAULTS = {
    "userPerBurst": config_defaults.DEFAULT_USER_PER_BURST,
    "userPerHour": config_defaults.DEFAULT_USER_PER_HOUR,
    "userPerDay": config_defaults.DEFAULT_USER_PER_DAY,
}


def _ask(surface: str, config: dict, times: int) -> tuple[list[tuple[bool, int]], _FixedWindowCounter]:
    counter = _FixedWindowCounter()
    caller = limits.Caller(key="caller-1", surface=surface)
    with mock.patch.object(limits.settings, "live", lambda: config), mock.patch.object(
        limits, "ratelimit", SimpleNamespace(allow=counter.allow, current=counter.current)
    ):
        results = [limits.check_and_count(caller) for _ in range(times)]
    return results, counter


class GuestBurstWindowTest(unittest.TestCase):
    def test_the_defaults_promise_ten_questions_in_three_minutes(self) -> None:
        # The contract, stated once: if this changes, the product claim and the
        # generated limits document change with it.
        self.assertGreaterEqual(config_defaults.DEFAULT_GUEST_PER_BURST, 10)
        self.assertEqual(limits.BURST_WINDOW_SECONDS, 180)

    def test_ten_questions_are_allowed_and_the_eleventh_waits_under_three_minutes(self) -> None:
        results, counter = _ask("guest", GUEST_DEFAULTS, 11)

        allowed = [ok for ok, _ in results]
        self.assertEqual(allowed[:10], [True] * 10, "ten questions in three minutes")
        self.assertFalse(allowed[10], "the eleventh is refused")
        self.assertLessEqual(
            results[10][1], limits.BURST_WINDOW_SECONDS, "and told to wait under three minutes"
        )
        self.assertEqual(counter.windows_asked[0], ("ai-assistant-burst", 180))

    def test_the_burst_window_is_checked_before_the_hour(self) -> None:
        _ask("guest", GUEST_DEFAULTS, 1)
        # Order matters: the shortest window is what a normal visitor trips, and it
        # is the one whose retry_after the widget shows.
        self.assertEqual([kind for kind, _ in _ask("guest", GUEST_DEFAULTS, 1)[1].windows_asked],
                         ["ai-assistant-burst", "ai-assistant-hour", "ai-assistant-day"])

    def test_the_hour_still_bounds_a_loop(self) -> None:
        # Burst off, so only the hour window can refuse — and its refusal is honest
        # about being an hour.
        config = {"guestPerBurst": 0, "guestPerHour": 5, "guestPerDay": 100}
        results, _ = _ask("guest", config, 6)
        self.assertFalse(results[5][0])
        self.assertGreater(results[5][1], limits.BURST_WINDOW_SECONDS)
        self.assertLessEqual(results[5][1], limits.HOUR_WINDOW_SECONDS)

    def test_the_day_still_bounds_a_patient_script(self) -> None:
        config = {"guestPerBurst": 0, "guestPerHour": 0, "guestPerDay": 3}
        results, _ = _ask("guest", config, 4)
        self.assertFalse(results[3][0])
        self.assertGreater(results[3][1], limits.HOUR_WINDOW_SECONDS)
        self.assertLessEqual(results[3][1], limits.DAY_WINDOW_SECONDS)

    def test_all_windows_zero_means_no_cap_configured(self) -> None:
        config = {"guestPerBurst": 0, "guestPerHour": 0, "guestPerDay": 0}
        results, counter = _ask("guest", config, 25)
        self.assertEqual([ok for ok, _ in results], [True] * 25)
        self.assertEqual(counter.windows_asked, [], "nothing is counted when no cap is set")

    def test_an_evaluation_run_is_exempt(self) -> None:
        results, counter = _ask("eval", {"guestPerBurst": 0, "guestPerHour": 0, "guestPerDay": 0}, 3)
        self.assertEqual(results, [(True, 0)] * 3)
        self.assertEqual(counter.windows_asked, [])


class SignedInTest(unittest.TestCase):
    def test_there_is_no_burst_cap_for_a_signed_in_caller_by_default(self) -> None:
        # "Effectively unlimited" must not become stricter than it was: a run of 40
        # questions is bounded by the hour window, not by a new short one.
        results, counter = _ask("user", USER_DEFAULTS, 40)
        self.assertEqual([ok for ok, _ in results], [True] * 40)
        self.assertNotIn("ai-assistant-burst", [kind for kind, _ in counter.windows_asked])

    def test_a_configured_burst_cap_applies_when_an_admin_sets_one(self) -> None:
        config = {"userPerBurst": 3, "userPerHour": 120, "userPerDay": 1000}
        results, _ = _ask("user", config, 4)
        self.assertEqual([ok for ok, _ in results], [True, True, True, False])


class UsageTest(unittest.TestCase):
    def test_usage_reports_every_window(self) -> None:
        counter = _FixedWindowCounter()
        caller = limits.Caller(key="caller-1", surface="guest")
        with mock.patch.object(limits.settings, "live", lambda: GUEST_DEFAULTS), mock.patch.object(
            limits, "ratelimit", SimpleNamespace(allow=counter.allow, current=counter.current)
        ):
            limits.check_and_count(caller)
            report = limits.usage(caller)

        self.assertEqual(report["scope"], "guest")
        self.assertEqual(report["burstLimit"], config_defaults.DEFAULT_GUEST_PER_BURST)
        self.assertEqual(report["burstUsed"], 1)
        self.assertEqual(report["hourUsed"], 1)
        self.assertEqual(report["dayUsed"], 1)


if __name__ == "__main__":
    unittest.main()

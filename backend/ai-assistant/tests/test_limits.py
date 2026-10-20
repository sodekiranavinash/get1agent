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
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

AI_ASSISTANT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ASSISTANT))
sys.path.insert(0, str(AI_ASSISTANT.parent / "packages"))

from data.repositories import ai_assistant_settings as config_defaults  # noqa: E402
from src import limits  # noqa: E402


class _GcraCounter:
    """In-memory stand-in for `core.ratelimit`'s Redis GCRA check.

    Mimics the real semantics the AI Assistant relies on:

    * all windows are consumed in **one** call, in the order given;
    * the first window with nothing left is the one that refuses, and its wait
      is the emission interval (`window / limit`) — the time until one slot
      frees, exactly what GCRA reports;
    * a refusal consumes nothing.
    """

    def __init__(self) -> None:
        self.buckets: dict[tuple[str, str, int], int] = {}
        self.windows_asked: list[tuple[str, int]] = []

    def check_windows(self, identity, windows, *, policy="", scope="user"):
        self.windows_asked.extend((window.name, window.seconds) for window in windows)
        allowed = True
        retry = 0
        denied = ""
        limit = 0
        for window in windows:
            key = (identity, window.name, window.seconds)
            used = self.buckets.get(key, 0)
            if used >= window.limit:
                if allowed:
                    allowed = False
                    retry = max(1, -(-window.seconds // max(window.limit, 1)))
                    denied = window.name
                    limit = window.limit
        if allowed:
            for window in windows:
                key = (identity, window.name, window.seconds)
                self.buckets[key] = self.buckets.get(key, 0) + 1
        return SimpleNamespace(
            allowed=allowed,
            retry_after=retry,
            window=denied,
            limit=limit,
            remaining=0,
            backend="test",
        )

    def current(self, identity, *, kind, window_seconds, limit=0, policy=""):
        return self.buckets.get((identity, kind, window_seconds), 0)


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


def _ask(surface: str, config: dict, times: int) -> tuple[list[tuple[bool, int]], _GcraCounter]:
    counter = _GcraCounter()
    caller = limits.Caller(key="caller-1", surface=surface)
    with mock.patch.object(limits.settings, "live", lambda: config), mock.patch.object(
        limits,
        "ratelimit",
        SimpleNamespace(check_windows=counter.check_windows, current=counter.current),
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
        counter = _GcraCounter()
        caller = limits.Caller(key="caller-1", surface="guest")
        with mock.patch.object(limits.settings, "live", lambda: GUEST_DEFAULTS), mock.patch.object(
            limits,
            "ratelimit",
            SimpleNamespace(check_windows=counter.check_windows, current=counter.current),
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

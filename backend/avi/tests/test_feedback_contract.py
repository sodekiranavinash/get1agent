"""Avi feedback must be one implementation, reachable from two surfaces.

The browser cannot mint the MicroVM ingress token, so the agent service's own
``POST /feedback`` is unreachable from the widget; ``user-api`` owns
``POST /v1/avi/feedback`` instead. Both call
``data.repositories.avi.record_feedback`` — this test pins that normalizer (and
the delegation from ``avi.feedback``) so the admin feedback table cannot end up
with two different item shapes depending on which surface recorded the thumb.

No AWS calls: ``upsert_feedback`` is replaced with a recorder.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parent / "packages"
for entry in (str(SERVICE_ROOT), str(PACKAGES)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from avi import feedback as avi_feedback  # noqa: E402
from data.repositories import avi as avi_repo  # noqa: E402


class _Recorder:
    """Stands in for ``upsert_feedback`` and captures its keyword arguments."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return {"runId": kwargs.get("run_id") or (args[1] if len(args) > 1 else "")}


class FeedbackNormalizerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = _Recorder()
        self._original = avi_repo.upsert_feedback
        avi_repo.upsert_feedback = self.recorder  # type: ignore[assignment]

    def tearDown(self) -> None:
        avi_repo.upsert_feedback = self._original  # type: ignore[assignment]

    def test_rejects_a_missing_or_unknown_thumb(self) -> None:
        for body in ({}, {"value": "sideways", "runId": "r1"}):
            with self.assertRaises(ValueError):
                avi_repo.record_feedback("u_test", body)
        self.assertEqual(self.recorder.calls, [])

    def test_requires_a_run_id(self) -> None:
        with self.assertRaises(ValueError):
            avi_repo.record_feedback("u_test", {"value": "up"})
        self.assertEqual(self.recorder.calls, [])

    def test_normalises_the_body_the_admin_table_reads(self) -> None:
        avi_repo.record_feedback(
            "u_test",
            {
                "runId": "avirun_1",
                "value": "DOWN",
                "comment": "wrong page",
                "categories": ["content", "", "routing"],
                "question": "how do I rotate a key?",
                "answer": "the fallback preview field",
                "conversationId": "avi_1",
                "model": "nvidia.nemotron-nano-3-30b",
                "classifierKind": "platform",
                "intent": "howto",
                "latencyMs": "1234",
                "tokensIn": 10,
                "tokensOut": 20,
                "sources": [
                    {"title": "Vault", "route": "/vault"},
                    {"title": "Docs", "route": "/docs", "ignored": "extra"},
                    "not-a-dict",
                ],
            },
        )
        self.assertEqual(len(self.recorder.calls), 1)
        args, kwargs = self.recorder.calls[0]
        self.assertEqual(args, ("u_test", "avirun_1"))
        self.assertEqual(kwargs["value"], "down")
        self.assertEqual(kwargs["comment"], "wrong page")
        self.assertEqual(kwargs["categories"], ["content", "routing"])
        # ``answer`` is the widget's legacy field name for the same thing.
        self.assertEqual(kwargs["answer_preview"], "the fallback preview field")
        self.assertEqual(kwargs["latency_ms"], 1234)
        self.assertEqual(kwargs["tokens_in"], 10)
        self.assertEqual(kwargs["sources"], [{"title": "Vault", "route": "/vault"}, {"title": "Docs", "route": "/docs"}])

    def test_an_unparseable_number_is_dropped_not_fatal(self) -> None:
        avi_repo.record_feedback("u_test", {"value": "up", "runId": "r", "latencyMs": "soon"})
        _, kwargs = self.recorder.calls[0]
        self.assertIsNone(kwargs["latency_ms"])


class DelegationTest(unittest.TestCase):
    """``avi.feedback`` and user-api must call the same normalizer."""

    def test_avi_feedback_delegates_to_the_repository(self) -> None:
        recorder = _Recorder()
        original = avi_repo.upsert_feedback
        avi_repo.upsert_feedback = recorder  # type: ignore[assignment]
        try:
            item = avi_feedback.record_feedback("u_test", {"value": "up", "runId": "r9"})
        finally:
            avi_repo.upsert_feedback = original  # type: ignore[assignment]
        self.assertEqual(item["runId"], "r9")
        self.assertEqual(len(recorder.calls), 1)


if __name__ == "__main__":
    unittest.main()

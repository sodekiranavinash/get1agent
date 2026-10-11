"""Unit tests for the automatic ("auto") model routing decision.

The classifier model and candidates are stubbed so the tests never reach
Bedrock; they cover the decision plumbing and the fail-open fallbacks.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import models, routing  # noqa: E402


class _FakeCandidate:
    def __init__(self, name: str) -> None:
        self.name = name
        self.model = object()


class _FakeStrategy:
    """Stands in for ``strands.models.ClassifierStrategy``."""

    chosen: object | None = None
    seen_prompt: str | None = None

    def __init__(self, model, *, system_prompt=None, timeout=None) -> None:
        _FakeStrategy.seen_prompt = system_prompt

    async def select(self, context):
        return _FakeStrategy.chosen


class _FakePolicy:
    def __init__(self, enabled: bool = True) -> None:
        self._enabled = enabled

    def __call__(self) -> bool:
        return self._enabled


class ChooseModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidates = (
            _FakeCandidate("zai.glm-4.7-flash"),
            _FakeCandidate("deepseek.v3.2"),
        )
        _FakeStrategy.chosen = None

    def _run(self, **kwargs):
        patches = [
            mock.patch.object(routing, "routing_enabled", return_value=True),
            mock.patch.object(routing, "build_model", return_value=object()),
            mock.patch.object(
                routing, "_candidates", return_value=self.candidates
            ),
            mock.patch("strands.models.ClassifierStrategy", _FakeStrategy),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        return asyncio.run(routing.choose_model(object(), "hello", **kwargs))

    def test_returns_classifier_choice(self) -> None:
        _FakeStrategy.chosen = self.candidates[1]
        self.assertEqual(self._run(), "deepseek.v3.2")

    def test_declines_to_default(self) -> None:
        _FakeStrategy.chosen = None
        self.assertEqual(self._run(), models.DEFAULT_MODEL)

    def test_unknown_choice_falls_back(self) -> None:
        _FakeStrategy.chosen = _FakeCandidate("mystery-model")
        self.assertEqual(self._run(), models.DEFAULT_MODEL)

    def test_empty_request_skips_classifier(self) -> None:
        self.assertEqual(
            asyncio.run(routing.choose_model(object(), "   ")), models.DEFAULT_MODEL
        )

    def test_disabled_skips_classifier(self) -> None:
        with mock.patch.object(routing, "routing_enabled", return_value=False):
            self.assertEqual(
                asyncio.run(routing.choose_model(object(), "hello")),
                models.DEFAULT_MODEL,
            )

    def test_classifier_error_falls_back(self) -> None:
        class _Boom(_FakeStrategy):
            async def select(self, context):
                raise RuntimeError("classifier down")

        with mock.patch.object(
            routing, "routing_enabled", return_value=True
        ), mock.patch.object(
            routing, "build_model", return_value=object()
        ), mock.patch.object(
            routing, "_candidates", return_value=self.candidates
        ), mock.patch(
            "strands.models.ClassifierStrategy", _Boom
        ):
            self.assertEqual(
                asyncio.run(routing.choose_model(object(), "hello")),
                models.DEFAULT_MODEL,
            )


class ProfileTests(unittest.TestCase):
    def test_every_supported_model_has_a_profile(self) -> None:
        for model_id in models.SUPPORTED_MODELS:
            profile = routing.MODEL_PROFILES.get(model_id)
            self.assertIsNotNone(profile, model_id)
            assert profile is not None
            self.assertTrue(profile.get("description"))
            self.assertTrue(profile.get("metadata"))

    def test_router_model_is_supported(self) -> None:
        self.assertIn(routing.router_model_id(), models.SUPPORTED_MODELS)

    def test_timeout_is_positive(self) -> None:
        self.assertGreater(routing.router_timeout_seconds(), 0)


if __name__ == "__main__":
    unittest.main()

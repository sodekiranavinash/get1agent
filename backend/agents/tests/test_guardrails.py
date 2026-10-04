"""Unit tests for the Bedrock Guardrails helper (no AWS calls)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))

from core import guardrails  # noqa: E402


class GuardrailConfigTests(unittest.TestCase):
    def test_disabled_without_id(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GUARDRAIL_ID", None)
            self.assertFalse(guardrails.enabled())
            self.assertIsNone(guardrails.guardrail_config())

    def test_config_with_id_and_version(self) -> None:
        env = {"GUARDRAIL_ID": "gr-123", "GUARDRAIL_VERSION": "3"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertTrue(guardrails.enabled())
            self.assertEqual(
                guardrails.guardrail_config(),
                {
                    "guardrailIdentifier": "gr-123",
                    "guardrailVersion": "3",
                    "trace": "enabled",
                },
            )

    def test_default_version_is_draft(self) -> None:
        with mock.patch.dict(os.environ, {"GUARDRAIL_ID": "gr-1"}, clear=False):
            os.environ.pop("GUARDRAIL_VERSION", None)
            self.assertEqual(guardrails.guardrail_version(), "DRAFT")


class ApplyTests(unittest.TestCase):
    def test_apply_requires_config(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GUARDRAIL_ID", None)
            with self.assertRaises(RuntimeError):
                guardrails.apply("hello")

    def test_apply_maps_intervention(self) -> None:
        class _Client:
            def apply_guardrail(self, **kwargs):
                return {
                    "action": "GUARDRAIL_INTERVENED",
                    "outputs": [{"text": "blocked"}],
                    "assessments": [{"contentPolicy": {}}],
                }

        with mock.patch.dict(os.environ, {"GUARDRAIL_ID": "gr-1"}, clear=False):
            with mock.patch.object(guardrails, "_client", lambda: _Client()):
                result = guardrails.apply("bad", source="INPUT")
        self.assertTrue(result["intervened"])
        self.assertEqual(result["output"], "blocked")
        self.assertEqual(result["assessments"], [{"contentPolicy": {}}])


if __name__ == "__main__":
    unittest.main()

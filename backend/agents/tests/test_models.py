"""Unit tests for the model-id resolver (legacy model fallback)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import models  # noqa: E402


class ResolveModelIdTests(unittest.TestCase):
    def test_supported_passthrough(self) -> None:
        self.assertEqual(
            models.resolve_model_id("deepseek.v3.2"),
            "deepseek.v3.2",
        )

    def test_legacy_model_falls_back(self) -> None:
        self.assertEqual(models.resolve_model_id("mimo-v2.5"), models.DEFAULT_MODEL)
        self.assertEqual(models.resolve_model_id("claude-sonnet-4"), models.DEFAULT_MODEL)

    def test_empty_falls_back(self) -> None:
        self.assertEqual(models.resolve_model_id(None), models.DEFAULT_MODEL)
        self.assertEqual(models.resolve_model_id("  "), models.DEFAULT_MODEL)

    def test_auto_resolves_to_default(self) -> None:
        # The run intercepts "auto" and routes it; the resolver only provides a
        # safe fallback when routing is unavailable.
        self.assertEqual(models.resolve_model_id("auto"), models.DEFAULT_MODEL)

    def test_is_auto_model(self) -> None:
        self.assertTrue(models.is_auto_model("auto"))
        self.assertTrue(models.is_auto_model("  AUTO "))
        self.assertFalse(models.is_auto_model("deepseek.v3.2"))
        self.assertFalse(models.is_auto_model(None))


if __name__ == "__main__":
    unittest.main()


class CacheAndTierEnvTests(unittest.TestCase):
    """The runtime's knobs also accept the platform-wide BEDROCK_* names.

    Infrastructure sets BEDROCK_PROMPT_CACHE/_TTL/_SERVICE_TIER (shared with the
    Lab Lambdas through core.bedrock_chat); the runtime must honour them, or the
    documented cost/latency levers never reach an actual run.
    """

    KEYS = (
        "AGENT_PROMPT_CACHE",
        "AGENT_PROMPT_CACHE_TTL",
        "AGENT_SERVICE_TIER",
        "BEDROCK_PROMPT_CACHE",
        "BEDROCK_PROMPT_CACHE_TTL",
        "BEDROCK_SERVICE_TIER",
    )

    def setUp(self) -> None:
        self._saved = {key: os.environ.get(key) for key in self.KEYS}
        for key in self.KEYS:
            os.environ.pop(key, None)

    def tearDown(self) -> None:
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_bedrock_alias_disables_caching(self) -> None:
        os.environ["BEDROCK_PROMPT_CACHE"] = "off"
        self.assertIsNone(models.cache_config())

    def test_agent_name_wins_over_alias(self) -> None:
        os.environ["BEDROCK_PROMPT_CACHE"] = "off"
        os.environ["AGENT_PROMPT_CACHE"] = "auto"
        self.assertIsNotNone(models.cache_config())

    def test_bedrock_alias_sets_the_service_tier(self) -> None:
        os.environ["BEDROCK_SERVICE_TIER"] = "flex"
        self.assertEqual(models.service_tier(), "flex")
        os.environ["AGENT_SERVICE_TIER"] = "priority"
        self.assertEqual(models.service_tier(), "priority")

    def test_unknown_tier_is_ignored(self) -> None:
        os.environ["BEDROCK_SERVICE_TIER"] = "turbo"
        self.assertIsNone(models.service_tier())

    def test_platform_standard_maps_to_the_api_default(self) -> None:
        # The platform (and Terraform) call the default tier "standard", but the
        # Bedrock API only accepts "default" — passing "standard" through would
        # make every runtime call fail validation.
        os.environ["BEDROCK_SERVICE_TIER"] = "standard"
        self.assertEqual(models.service_tier(), "default")
        os.environ["AGENT_SERVICE_TIER"] = "flex"
        self.assertEqual(models.service_tier(), "flex")

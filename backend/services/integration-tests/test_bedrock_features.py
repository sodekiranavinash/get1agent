"""Bedrock cost/latency levers: prompt caching, tiers, routing, profiles."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))

from core import bedrock_features as bf  # noqa: E402

_KEYS = (
    "BEDROCK_PROMPT_CACHE",
    "BEDROCK_PROMPT_CACHE_TTL",
    "BEDROCK_SERVICE_TIER",
    "BEDROCK_PROMPT_ROUTER_ARN",
    "BEDROCK_PROFILE_CHAT",
    "BEDROCK_PROFILE_EVAL",
    "BEDROCK_PROFILE_INGESTION",
)


def _clear(monkeypatch) -> None:
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)


class PromptCacheTests(unittest.TestCase):
    def test_default_is_auto(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BEDROCK_PROMPT_CACHE", None)
            self.assertEqual(bf.prompt_cache(), {"strategy": "auto", "ttl": None})

    def test_ttl_maps(self) -> None:
        env = {"BEDROCK_PROMPT_CACHE": "anthropic", "BEDROCK_PROMPT_CACHE_TTL": "1h"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertEqual(
                bf.prompt_cache(), {"strategy": "anthropic", "ttl": "1h"}
            )

    def test_off_disables(self) -> None:
        with mock.patch.dict(os.environ, {"BEDROCK_PROMPT_CACHE": "off"}, clear=False):
            self.assertIsNone(bf.prompt_cache())


class ServiceTierTests(unittest.TestCase):
    def test_valid_tiers(self) -> None:
        for tier in ("standard", "flex", "priority"):
            with mock.patch.dict(os.environ, {"BEDROCK_SERVICE_TIER": tier}, clear=False):
                self.assertEqual(bf.service_tier(), tier)

    def test_invalid_is_none(self) -> None:
        with mock.patch.dict(os.environ, {"BEDROCK_SERVICE_TIER": "turbo"}, clear=False):
            self.assertIsNone(bf.service_tier())


class RoutingTests(unittest.TestCase):
    def test_router_used_when_set(self) -> None:
        env = {"BEDROCK_PROMPT_ROUTER_ARN": "arn:aws:bedrock:ap-south-1:1:prompt-router/x"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("BEDROCK_PROFILE_CHAT", None)
            self.assertTrue(bf.routing_enabled())
            self.assertTrue(bf.resolve_model("zai.glm-4.7-flash").endswith("router/x"))

    def test_profile_wins_over_router(self) -> None:
        env = {
            "BEDROCK_PROMPT_ROUTER_ARN": "arn:aws:bedrock:1:prompt-router/x",
            "BEDROCK_PROFILE_CHAT": "arn:aws:bedrock:1:application-inference-profile/chat",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertTrue(bf.resolve_model("m").endswith("profile/chat"))

    def test_model_passthrough(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            for key in _KEYS:
                os.environ.pop(key, None)
            self.assertEqual(bf.resolve_model("zai.glm-4.7-flash"), "zai.glm-4.7-flash")

    def test_profile_is_per_workload(self) -> None:
        env = {"BEDROCK_PROFILE_EVAL": "arn:aws:bedrock:1:application-inference-profile/eval"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertTrue(bf.resolve_model("m", workload="eval").endswith("profile/eval"))
            self.assertEqual(bf.resolve_model("m", workload="chat"), "m")


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the Vault provider presets and connection tester.

Run with: ``make -C backend/services/user-api test``
"""

from __future__ import annotations

import ipaddress
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from src.vault import providers, tester  # noqa: E402


class ProviderPresetTests(unittest.TestCase):
    def test_known_ids_and_custom_fallback(self) -> None:
        self.assertEqual(providers.get_provider("openai")["id"], "openai")
        self.assertEqual(providers.normalize_provider("nope")["id"], "custom")
        self.assertEqual(providers.normalize_provider(None)["id"], "custom")

    def test_auth_styles(self) -> None:
        self.assertEqual(providers.auth_style("openai"), "bearer")
        self.assertEqual(providers.auth_style("anthropic"), "x-api-key")

    def test_public_list_shape(self) -> None:
        listed = {provider["id"] for provider in providers.provider_public_list()}
        self.assertIn("openai", listed)
        self.assertIn("openrouter", listed)
        self.assertIn("custom", listed)

    def test_presets_offer_models(self) -> None:
        openai = providers.get_provider("openai")
        self.assertIsInstance(openai["models"], list)
        self.assertIn(openai["defaultModel"], openai["models"])
        # Every public preset carries a models list (custom may be empty).
        for provider in providers.provider_public_list():
            self.assertIsInstance(provider["models"], list)

    def test_ollama_does_not_require_a_key(self) -> None:
        self.assertFalse(providers.get_provider("ollama")["requiresKey"])


class SsrfGuardTests(unittest.TestCase):
    def test_is_blocked_covers_internal_ranges(self) -> None:
        blocked = ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "::1"]
        for value in blocked:
            self.assertTrue(tester._is_blocked(ipaddress.ip_address(value)), value)
        self.assertFalse(tester._is_blocked(ipaddress.ip_address("8.8.8.8")))

    def test_private_allowed_when_opted_in(self) -> None:
        with mock.patch.dict(os.environ, {"VAULT_ALLOW_PRIVATE_URLS": "true"}):
            self.assertFalse(tester._is_blocked(ipaddress.ip_address("127.0.0.1")))

    def test_rejects_bad_urls_without_dns(self) -> None:
        for value in ("", "ftp://example.com", "https://user:pass@example.com"):
            with self.assertRaises(tester.TestError):
                tester._validate_base_url(value)


class ListModelsTests(unittest.TestCase):
    def test_returns_model_ids(self) -> None:
        with mock.patch.object(tester, "_validate_base_url", return_value="https://api.openai.com/v1"), \
             mock.patch.object(
                 tester, "_request", return_value=(200, {"data": [{"id": "a"}, {"id": "b"}]}, "")
             ):
            result = tester.list_models(
                provider_id="openai", base_url="https://api.openai.com/v1", api_key="sk"
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["models"], ["a", "b"])

    def test_rejected_key_is_reported(self) -> None:
        with mock.patch.object(tester, "_validate_base_url", return_value="https://api.openai.com/v1"), \
             mock.patch.object(tester, "_request", return_value=(401, None, "nope")):
            result = tester.list_models(
                provider_id="openai", base_url="https://api.openai.com/v1", api_key="sk"
            )
        self.assertFalse(result["ok"])
        self.assertEqual(result["models"], [])


class ResponseParsingTests(unittest.TestCase):
    def test_model_ids(self) -> None:
        payload = {"data": [{"id": "a"}, "b", {"nope": 1}]}
        self.assertEqual(tester._model_ids(payload), ["a", "b"])
        self.assertEqual(tester._model_ids(None), [])

    def test_auth_messages(self) -> None:
        self.assertIn("rejected", tester._auth_message(401))
        self.assertIn("rate limiting", tester._auth_message(429))


class TestProviderTests(unittest.TestCase):
    def _call(self, **overrides):
        params = {
            "provider_id": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": "sk-test",
            "model": "gpt-4o-mini",
        }
        params.update(overrides)
        return tester.test_provider(**params)

    def test_models_only_success(self) -> None:
        with mock.patch.object(tester, "_validate_base_url", return_value="https://api.openai.com/v1"), \
             mock.patch.object(tester, "_request", return_value=(200, {"data": [{"id": "gpt-4o-mini"}]}, "")):
            result = self._call(model="")
        self.assertTrue(result["ok"])
        self.assertEqual(result["models"], ["gpt-4o-mini"])
        self.assertIn("model(s)", result["message"])

    def test_rejected_key_raises(self) -> None:
        with mock.patch.object(tester, "_validate_base_url", return_value="https://api.openai.com/v1"), \
             mock.patch.object(tester, "_request", return_value=(401, None, "nope")):
            with self.assertRaises(tester.TestError):
                self._call()

    def test_chat_probe_reports_sample(self) -> None:
        responses = [
            (200, {"data": [{"id": "gpt-4o-mini"}]}, ""),
            (200, {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 3}}, ""),
        ]
        with mock.patch.object(tester, "_validate_base_url", return_value="https://api.openai.com/v1"), \
             mock.patch.object(tester, "_request", side_effect=responses):
            result = self._call()
        self.assertTrue(result["ok"])
        self.assertEqual(result["sample"], "ok")
        self.assertEqual(result["usage"]["total_tokens"], 3)

    def test_key_required(self) -> None:
        with self.assertRaises(tester.TestError):
            tester.test_provider(provider_id="openai", base_url="https://api.openai.com/v1", api_key="")


if __name__ == "__main__":
    unittest.main()

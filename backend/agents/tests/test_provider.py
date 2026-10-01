"""Unit tests for resolving a Vault provider secret into model client args."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from unittest import mock

_AGENTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_AGENTS))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))

from agentflow import models, provider  # noqa: E402
from agentflow.config import load_config  # noqa: E402


class ResolveModelProviderTests(unittest.TestCase):
    def test_empty_id_is_none(self) -> None:
        self.assertIsNone(provider.resolve_model_provider("u_x", ""))
        self.assertIsNone(provider.resolve_model_provider("u_x", None))

    def test_missing_secret_raises(self) -> None:
        with mock.patch.object(provider.vault_repo, "get_secret", return_value=None):
            with self.assertRaises(provider.ProviderError):
                provider.resolve_model_provider("u_x", "abc")

    def test_non_provider_kind_raises(self) -> None:
        with mock.patch.object(
            provider.vault_repo, "get_secret", return_value={"kind": "generic"}
        ):
            with self.assertRaises(provider.ProviderError):
                provider.resolve_model_provider("u_x", "abc")

    def test_incomplete_provider_raises(self) -> None:
        item = {"kind": "provider", "baseUrl": "https://x/v1", "secretId": "abc"}
        with mock.patch.object(provider.vault_repo, "get_secret", return_value=item), \
             mock.patch.object(provider.vault_repo, "open_payload", return_value={}):
            with self.assertRaises(provider.ProviderError):
                provider.resolve_model_provider("u_x", "abc")

    def test_happy_path(self) -> None:
        item = {
            "kind": "provider",
            "baseUrl": "https://api.example.com/v1",
            "secretId": "abc",
            "name": "my-key",
            "defaultModel": "gpt-4o-mini",
        }
        with mock.patch.object(provider.vault_repo, "get_secret", return_value=item), \
             mock.patch.object(
                 provider.vault_repo, "open_payload", return_value={"apiKey": "sk-secret"}
             ):
            resolved = provider.resolve_model_provider("u_x", "abc")
        self.assertEqual(resolved["apiKey"], "sk-secret")
        self.assertEqual(resolved["baseUrl"], "https://api.example.com/v1")
        self.assertEqual(resolved["defaultModel"], "gpt-4o-mini")

    def test_record_usage_is_best_effort(self) -> None:
        with mock.patch.object(provider.vault_repo, "record_run") as record:
            provider.record_provider_usage(
                "u_x", "abc", {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15}, "m"
            )
        record.assert_called_once()
        kwargs = record.call_args.kwargs
        self.assertEqual(kwargs["total_tokens"], 15)

        # A failure here must never propagate to the run.
        with mock.patch.object(
            provider.vault_repo, "record_run", side_effect=RuntimeError("boom")
        ):
            provider.record_provider_usage("u_x", "abc", {"totalTokens": 1}, "m")


class BuildModelProviderTests(unittest.TestCase):
    def _fake_strands(self) -> type:
        class FakeOpenAIModel:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        strands = sys.modules.setdefault("strands", types.ModuleType("strands"))
        models_pkg = sys.modules.setdefault("strands.models", types.ModuleType("strands.models"))
        openai_mod = types.ModuleType("strands.models.openai")
        openai_mod.OpenAIModel = FakeOpenAIModel
        sys.modules["strands.models.openai"] = openai_mod
        strands.models = models_pkg
        models_pkg.openai = openai_mod
        return FakeOpenAIModel

    def test_provider_uses_own_key_and_base_url(self) -> None:
        fake = self._fake_strands()
        try:
            config = load_config()
            built = models.build_model(
                config,
                "gpt-4o-mini",
                "session-1",
                provider={
                    "apiKey": "sk-user",
                    "baseUrl": "https://api.example.com/v1",
                    "defaultModel": "gpt-4o-mini",
                },
            )
        finally:
            sys.modules.pop("strands.models.openai", None)
        self.assertIsInstance(built, fake)
        self.assertEqual(built.kwargs["model_id"], "gpt-4o-mini")
        self.assertEqual(built.kwargs["client_args"]["api_key"], "sk-user")
        self.assertEqual(built.kwargs["client_args"]["base_url"], "https://api.example.com/v1")


if __name__ == "__main__":
    unittest.main()

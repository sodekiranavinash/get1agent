"""Unit tests for the run guardrail resolver (no AWS calls)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import guardrails as resolver  # noqa: E402


def _settings(settings):
    return mock.patch.object(
        resolver.settings_repo, "get_settings", lambda _uid: settings or {}
    )


class LoadDefaultTests(unittest.TestCase):
    def test_workspace_default(self) -> None:
        with _settings({"guardrailId": "gr-ws"}):
            self.assertEqual(
                resolver.load_default_guardrail("u_1"),
                {"id": "gr-ws", "version": "DRAFT"},
            )

    def test_env_fallback(self) -> None:
        env = {"GUARDRAIL_ID": "gr-env", "GUARDRAIL_VERSION": "3"}
        with mock.patch.dict(os.environ, env, clear=False):
            with _settings({}):
                self.assertEqual(
                    resolver.load_default_guardrail("u_1"),
                    {"id": "gr-env", "version": "3"},
                )

    def test_none_when_unconfigured(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GUARDRAIL_ID", None)
            with _settings({}):
                self.assertIsNone(resolver.load_default_guardrail("u_1"))


class ResolveGuardrailTests(unittest.TestCase):
    def test_disabled_opts_out(self) -> None:
        self.assertIsNone(
            resolver.resolve_guardrail(
                {"enabled": False, "id": "gr-1"}, default={"id": "gr-ws", "version": "DRAFT"}
            )
        )

    def test_explicit_id_wins(self) -> None:
        self.assertEqual(
            resolver.resolve_guardrail(
                {"enabled": True, "id": "gr-agent"},
                default={"id": "gr-ws", "version": "DRAFT"},
            ),
            {"id": "gr-agent", "version": "DRAFT"},
        )

    def test_default_used_when_block_empty(self) -> None:
        self.assertEqual(
            resolver.resolve_guardrail(
                {"enabled": True, "id": ""}, default={"id": "gr-ws", "version": "DRAFT"}
            ),
            {"id": "gr-ws", "version": "DRAFT"},
        )

    def test_workflow_fallback_for_member(self) -> None:
        self.assertEqual(
            resolver.resolve_guardrail(
                {},
                {"enabled": True, "id": "gr-flow"},
                default={"id": "gr-ws", "version": "DRAFT"},
            ),
            {"id": "gr-flow", "version": "DRAFT"},
        )

    def test_member_disabled_ignores_workflow(self) -> None:
        self.assertIsNone(
            resolver.resolve_guardrail(
                {"enabled": False},
                {"enabled": True, "id": "gr-flow"},
                default={"id": "gr-ws", "version": "DRAFT"},
            )
        )

    def test_no_guardrail_anywhere(self) -> None:
        self.assertIsNone(resolver.resolve_guardrail({}))


if __name__ == "__main__":
    unittest.main()

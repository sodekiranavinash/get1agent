"""Unit tests for the model-id resolver (legacy model fallback)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import models  # noqa: E402


class ResolveModelIdTests(unittest.TestCase):
    def test_supported_passthrough(self) -> None:
        self.assertEqual(
            models.resolve_model_id("deepseek-v4-flash-vision-exp"),
            "deepseek-v4-flash-vision-exp",
        )

    def test_legacy_model_falls_back(self) -> None:
        self.assertEqual(models.resolve_model_id("claude-sonnet-4"), models.DEFAULT_MODEL)

    def test_empty_falls_back(self) -> None:
        self.assertEqual(models.resolve_model_id(None), models.DEFAULT_MODEL)
        self.assertEqual(models.resolve_model_id("  "), models.DEFAULT_MODEL)


if __name__ == "__main__":
    unittest.main()

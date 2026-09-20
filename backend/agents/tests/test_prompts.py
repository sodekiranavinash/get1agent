"""Unit tests for system-prompt assembly."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import prompts  # noqa: E402


class BuildSystemPromptTests(unittest.TestCase):
    def test_prompt_and_output_format(self) -> None:
        prompt = prompts.build_system_prompt(
            {
                "prompt": "You are a bot.",
                "output": {"format": "json", "instructions": "Be terse."},
            },
            [],
        )
        self.assertIn("You are a bot.", prompt)
        self.assertIn("Respond in JSON.", prompt)
        self.assertIn("Be terse.", prompt)

    def test_skills_are_injected(self) -> None:
        prompt = prompts.build_system_prompt(
            {"prompt": "p"},
            [{"name": "pdf", "description": "Read PDFs", "content": "Use pymupdf."}],
        )
        self.assertIn("### Skill: pdf", prompt)
        self.assertIn("Use pymupdf.", prompt)

    def test_default_prompt_when_empty(self) -> None:
        prompt = prompts.build_system_prompt({}, [])
        self.assertTrue(prompt)

    def test_reasoning_is_excluded_from_the_answer(self) -> None:
        prompt = prompts.build_system_prompt({"prompt": "p"}, [])
        self.assertIn("Never include your internal reasoning", prompt)


if __name__ == "__main__":
    unittest.main()

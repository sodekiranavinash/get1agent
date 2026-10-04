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

    def test_skills_use_progressive_disclosure(self) -> None:
        prompt = prompts.build_system_prompt(
            {"prompt": "p"},
            [{"name": "pdf", "description": "Read PDFs", "content": "Use pymupdf."}],
        )
        # The skill body must NOT be pasted into the prompt — only guidance to
        # activate it, so the agent decides when the skill applies.
        self.assertNotIn("Use pymupdf.", prompt)
        self.assertNotIn("### Skill: pdf", prompt)
        self.assertIn("`skills` tool", prompt)
        self.assertIn("available_skills", prompt)

    def test_answer_mode_controls_depth(self) -> None:
        summarize = prompts.build_system_prompt({"prompt": "p", "answerMode": "summarize"}, [])
        self.assertIn("Answer mode: SUMMARIZE", summarize)
        normal = prompts.build_system_prompt({"prompt": "p", "answerMode": "normal"}, [])
        self.assertIn("Answer mode: NORMAL", normal)
        detailed = prompts.build_system_prompt({"prompt": "p", "answerMode": "detailed"}, [])
        self.assertIn("Answer mode: DETAILED", detailed)

    def test_answer_mode_legacy_values(self) -> None:
        # Values saved before the rename still map to their meaning.
        self.assertIn(
            "Answer mode: NORMAL",
            prompts.build_system_prompt({"prompt": "p", "answerMode": "medium"}, []),
        )
        self.assertIn(
            "Answer mode: DETAILED",
            prompts.build_system_prompt({"prompt": "p", "answerMode": "deep"}, []),
        )

    def test_answer_mode_defaults_to_summarize(self) -> None:
        prompt = prompts.build_system_prompt({"prompt": "p"}, [])
        self.assertIn("Answer mode: SUMMARIZE", prompt)

    def test_high_reasoning_adds_a_hint(self) -> None:
        prompt = prompts.build_system_prompt({"prompt": "p", "reasoning": "high"}, [])
        self.assertIn("Reasoning effort: HIGH", prompt)
        medium = prompts.build_system_prompt({"prompt": "p", "reasoning": "medium"}, [])
        self.assertNotIn("Reasoning effort", medium)

    def test_default_prompt_when_empty(self) -> None:
        prompt = prompts.build_system_prompt({}, [])
        self.assertTrue(prompt)

    def test_knowledge_bases_are_the_primary_source(self) -> None:
        prompt = prompts.build_system_prompt(
            {"prompt": "p", "knowledgeBaseIds": ["kb1"]}, []
        )
        self.assertIn("KNOWLEDGE BASES (primary source)", prompt)
        self.assertIn("search-user-knowledge-bases", prompt)
        # Absent when the agent has no knowledge bases attached.
        self.assertNotIn(
            "KNOWLEDGE BASES (primary source)",
            prompts.build_system_prompt({"prompt": "p"}, []),
        )

    def test_answers_are_grounded_in_tools_only(self) -> None:
        prompt = prompts.build_system_prompt({"prompt": "p"}, [])
        self.assertIn("GROUNDING (mandatory)", prompt)
        self.assertIn("Do NOT use your own or training knowledge", prompt)
        # The old escape hatch (answer from your own memory) is gone.
        self.assertNotIn("from your own knowledge and say so", prompt)

    def test_reasoning_is_excluded_from_the_answer(self) -> None:
        prompt = prompts.build_system_prompt({"prompt": "p"}, [])
        self.assertIn("Never include your internal reasoning", prompt)


if __name__ == "__main__":
    unittest.main()

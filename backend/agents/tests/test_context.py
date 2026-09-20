"""Unit tests for the tool-result trimming that bounds the model context."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import context  # noqa: E402


def _pair(use_id: str, tool: str, text: str) -> list[dict]:
    return [
        {"role": "assistant", "content": [{"toolUse": {"toolUseId": use_id, "name": tool}}]},
        {
            "role": "user",
            "content": [{"toolResult": {"toolUseId": use_id, "content": [{"text": text}]}}],
        },
    ]


def _text_of(message: dict) -> str:
    for block in message["content"]:
        if "toolResult" in block:
            return block["toolResult"]["content"][0]["text"]
    return ""


class TrimToolResultsTests(unittest.TestCase):
    def test_truncates_old_keeps_recent(self) -> None:
        messages = (
            _pair("a", "web-search", "A" * 5000)
            + _pair("b", "web-search", "B" * 5000)
            + _pair("c", "web-search", "C" * 5000)
        )
        trimmed = context.trim_tool_results(messages, max_chars=100, keep_full=2)
        # The oldest result is truncated; the last two are untouched.
        self.assertTrue(_text_of(trimmed[1]).endswith(context.TRUNCATION_MARKER))
        self.assertLessEqual(len(_text_of(trimmed[1])), 100 + len(context.TRUNCATION_MARKER))
        self.assertEqual(_text_of(trimmed[3]), "B" * 5000)
        self.assertEqual(_text_of(trimmed[5]), "C" * 5000)

    def test_knowledge_is_exempt(self) -> None:
        messages = (
            _pair("k", "search-user-knowledge-bases", "K" * 5000)
            + _pair("a", "web-search", "A" * 5000)
            + _pair("b", "web-search", "B" * 5000)
        )
        trimmed = context.trim_tool_results(messages, max_chars=100, keep_full=1)
        # Knowledge result stays full even though it is the oldest.
        self.assertEqual(_text_of(trimmed[1]), "K" * 5000)
        # The web result that is not among the last 1 is truncated.
        self.assertTrue(_text_of(trimmed[3]).endswith(context.TRUNCATION_MARKER))

    def test_short_result_untouched(self) -> None:
        messages = _pair("a", "web-search", "short") + _pair("b", "web-search", "also short")
        trimmed = context.trim_tool_results(messages, max_chars=100, keep_full=0)
        self.assertEqual(_text_of(trimmed[1]), "short")
        self.assertEqual(_text_of(trimmed[3]), "also short")

    def test_original_messages_not_mutated(self) -> None:
        messages = _pair("a", "web-search", "A" * 5000)
        context.trim_tool_results(messages, max_chars=10, keep_full=0)
        self.assertEqual(_text_of(messages[1]), "A" * 5000)


if __name__ == "__main__":
    unittest.main()

"""Avi's SSE frames must match the platform's wire contract exactly.

This is the test that would have caught the worst Avi bug so far: ``FrameWriter``
emitted ``{"type": "text", "text": "…"}`` while ``lib/runState.ts`` appends
``event.data`` to the answer. Every answer chunk was therefore concatenated as the
literal string ``undefined``, and the widget rendered ``undefinedundefined…``.

The wire contract is owned by ``backend/agents/agentflow/events.py`` and consumed
by ``frontend/src/lib/{agentRun,runState}.ts``; Avi reuses it rather than defining
its own. Keeping this test in lockstep with those three files is the point — a
rename on either side must fail here rather than in front of a user.

No AWS calls and no LangChain import: ``avi.frames`` is deliberately stdlib-only.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from avi.frames import FrameWriter, sse  # noqa: E402

#: Repository root — ``backend/avi/tests/test_frames_contract.py`` → four levels up.
REPO_ROOT = Path(__file__).resolve().parents[3]

#: Frame types the shared reducer understands, plus Avi's own ``avi.*`` namespace.
PLATFORM_FRAME_TYPES = {
    "run.started",
    "skills",
    "attachments",
    "plan.started",
    "plan",
    "text",
    "tool.start",
    "tool.input",
    "tool.stream",
    "tool.result",
    "question",
    "run.completed",
    "trace",
    "context",
    "run.error",
}


class TextFrameContract(unittest.TestCase):
    def setUp(self) -> None:
        self.writer = FrameWriter(run_id="avirun_test", model="test-model")

    def test_text_delta_uses_data_not_text(self) -> None:
        """The answer chunk field is ``data``; ``text`` would render as undefined."""
        frame = self.writer.text_delta("hello")
        self.assertIsNotNone(frame)
        assert frame is not None
        self.assertEqual(frame["type"], "text")
        self.assertEqual(frame["data"], "hello")
        self.assertNotIn("text", frame)

    def test_empty_delta_emits_no_frame(self) -> None:
        """A falsy chunk must not become a frame at all."""
        self.assertIsNone(self.writer.text_delta(""))

    def test_answer_accumulates_from_deltas(self) -> None:
        for chunk in ("Hel", "lo", " world"):
            self.writer.text_delta(chunk)
        self.assertEqual(self.writer.answer, "Hello world")

    def test_a_tool_call_discards_the_preamble(self) -> None:
        """Text before a tool call is narration, not the answer.

        ``runState.applyToolStart`` blanks the client's answer on ``tool.start``,
        so the server must agree: otherwise ``run.completed.text`` — the fallback
        the widget adopts when its own answer was blanked — would carry preamble
        glued onto the real answer.
        """
        self.writer.text_delta("Let me check the docs.")
        frame = self.writer.tool_start("tool-1", "search_platform_docs")
        self.assertIsNotNone(frame)
        self.assertEqual(self.writer.answer, "")
        self.writer.text_delta("Here is the answer.")
        self.assertEqual(self.writer.answer, "Here is the answer.")

    def test_completed_text_is_the_post_tool_answer(self) -> None:
        self.writer.text_delta("Searching…")
        self.writer.tool_start("tool-1", "search_platform_docs")
        self.writer.tool_result("tool-1", "search_platform_docs", "[]")
        self.writer.text_delta("You can rotate a key in Vault.")
        frame = self.writer.completed()
        self.assertEqual(frame["text"], "You can rotate a key in Vault.")

    def test_note_is_not_a_text_frame(self) -> None:
        """``avi.note`` is its own type; the reducer ignores it by default."""
        frame = self.writer.note("Looking that up…")
        self.assertEqual(frame["type"], "avi.note")
        self.assertNotEqual(frame["type"], "text")


class ToolResultFrameContract(unittest.TestCase):
    def setUp(self) -> None:
        self.writer = FrameWriter(run_id="avirun_test", model="test-model")
        self.writer.tool_start("tool-1", "search_platform_docs")

    def test_tool_result_carries_status_and_string_data(self) -> None:
        frame = self.writer.tool_result("tool-1", "search_platform_docs", [{"title": "x"}])
        self.assertEqual(frame["type"], "tool.result")
        self.assertEqual(frame["status"], "success")
        self.assertEqual(frame["toolUseId"], "tool-1")
        # ``runState`` treats ``data`` as a string and renders it as tool output.
        self.assertIsInstance(frame["data"], str)
        self.assertEqual(json.loads(frame["data"]), [{"title": "x"}])

    def test_tool_result_passes_a_string_through_unchanged(self) -> None:
        frame = self.writer.tool_result("tool-1", "find_page", "No page matched.")
        self.assertEqual(frame["data"], "No page matched.")

    def test_tool_result_forwards_sources(self) -> None:
        source = {"kind": "knowledge", "index": 1, "title": "Docs", "route": "/docs"}
        frame = self.writer.tool_result("tool-1", "search_platform_docs", "[]", sources=[source])
        self.assertEqual(frame["sources"], [source])


class WholeRunFrameContract(unittest.TestCase):
    """Every frame a turn can emit must be well formed for the shared reducer."""

    def _run_frames(self) -> list[dict]:
        writer = FrameWriter(run_id="avirun_test", model="test-model", conversation_id="conv-1")
        frames: list[dict] = [writer.run_started(), *writer.plan([{"id": "q1", "query": "x"}])]
        frames.append(writer.text_delta("part one"))
        frames.append(writer.tool_start("tool-1", "search_platform_docs"))
        frames.append(writer.tool_input("tool-1", {"query": "x"}))
        frames.append(writer.tool_result("tool-1", "search_platform_docs", "[]"))
        frames.append(writer.text_delta("part two"))
        frames.append(writer.completed())
        return [frame for frame in frames if frame is not None]

    def test_run_started_shape(self) -> None:
        frame = self._run_frames()[0]
        self.assertEqual(frame["type"], "run.started")
        # The widget reads all three: runId keys feedback, sessionId continues the
        # conversation, agentId is the transcript's target.
        for key in ("runId", "agentId", "sessionId"):
            self.assertIn(key, frame)

    def test_every_frame_is_reduced_or_explicitly_namespaced(self) -> None:
        for frame in self._run_frames():
            kind = frame["type"]
            self.assertTrue(
                kind in PLATFORM_FRAME_TYPES or kind.startswith("avi."),
                f"unexpected frame type: {kind}",
            )

    def test_no_frame_claims_to_be_text_without_data(self) -> None:
        """The exact regression: a ``text`` frame whose payload is under another key."""
        for frame in self._run_frames():
            if frame["type"] == "text":
                self.assertIsInstance(frame.get("data"), str)
                self.assertTrue(frame["data"])

    def test_completed_frame_keeps_the_persistence_fields(self) -> None:
        """``conversations.summarise_frames`` reads these off ``run.completed``."""
        writer = FrameWriter(run_id="avirun_test", model="test-model")
        writer.text_delta("the answer")
        frame = writer.completed(stop_reason="end_turn")
        self.assertEqual(frame["text"], "the answer")
        self.assertEqual(frame["stopReason"], "end_turn")
        self.assertEqual(
            set(frame["usage"]), {"inputTokens", "outputTokens", "totalTokens"}
        )

    def test_frames_survive_sse_serialisation(self) -> None:
        for frame in self._run_frames():
            payload = sse(frame)
            self.assertTrue(payload.startswith("data: "))
            self.assertTrue(payload.endswith("\n\n"))
            decoded = json.loads(payload[len("data: ") :].strip())
            self.assertEqual(decoded, frame)


class FrontendContractIsPinned(unittest.TestCase):
    """Cross-language pin: the client's field names must match what we emit.

    A comment claiming the frames are shared is not a contract; this reads the
    TypeScript so a rename on the client side fails here instead of shipping.
    """

    def test_client_declares_text_data(self) -> None:
        source = (REPO_ROOT / "frontend/src/lib/agentRun.ts").read_text(encoding="utf-8")
        self.assertIn("type: 'text'; data: string", source)

    def test_reducer_appends_data(self) -> None:
        source = (REPO_ROOT / "frontend/src/lib/runState.ts").read_text(encoding="utf-8")
        self.assertIn("state.answer + text", source)


if __name__ == "__main__":
    unittest.main()

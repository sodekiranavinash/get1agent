"""AI Assistant's live-progress frames: the work log must describe real work.

The widget renders `ai-assistant.stage` frames as a live list ("Searching the platform
docs", "Locating the page you need", …). That only earns its place if every line
is emitted at the moment the turn actually reaches that milestone — a log driven by
timers would be theatre. These tests pin the emit points, the one-shot compose
stage, and the fact that a stage carries the literal detail behind it (the tool
name, the matched-page count).

No AWS calls: retrieval is recorded with a stub and the agent harness is absent, so
a turn ends harmlessly after the stages under test.
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parent / "packages"
for entry in (str(SERVICE_ROOT), str(PACKAGES)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from src import agent, retrieval  # noqa: E402
from src.frames import (  # noqa: E402
    FRAME_STAGE,
    STAGE_COMPOSE,
    STAGE_INTENT,
    STAGE_KNOWLEDGE,
    STAGE_LINKS,
    STAGE_PLAN,
    FrameWriter,
)


class _PlatformVerdict:
    kind = "platform"
    intent = "howto"
    confidence = 1.0
    stage = "rules"
    examples: tuple[str, ...] = ()
    is_platform = True
    is_smalltalk = False

    def to_frame(self) -> dict:
        return {
            "type": "ai-assistant.intent",
            "kind": self.kind,
            "intent": self.intent,
            "confidence": self.confidence,
            "stage": self.stage,
            "examples": [],
        }


class _SearchRecorder:
    """Returns one passage, so the 'choosing pages' stage has something to report."""

    def __init__(self, passages: list | None = None) -> None:
        self.calls: list[dict] = []
        self.passages = passages if passages is not None else [_passage()]

    def __call__(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return list(self.passages), {"stage": "test", "count": len(self.passages)}


def _passage() -> retrieval.Passage:
    return retrieval.Passage(
        index=1,
        title="Knowledge bases",
        route="/docs#knowledge-bases",
        content="body",
        matched="body",
        snippet="body",
        score=0.9,
    )


def _stages(frames: list[dict]) -> list[dict]:
    return [frame for frame in frames if frame.get("type") == FRAME_STAGE]


def _run(request: agent.TurnRequest, frames: int = 12) -> list[dict]:
    async def drive() -> list[dict]:
        out: list[dict] = []
        agen = agent.run_turn(request, verdict=_PlatformVerdict())
        try:
            async for frame in agen:
                out.append(frame)
                if len(out) >= frames:
                    break
        finally:
            await agen.aclose()
        return out

    return asyncio.run(drive())


class _SmalltalkVerdict(_PlatformVerdict):
    """A greeting: on-topic enough to answer, but nothing to look up."""

    kind = "platform"
    intent = "smalltalk"
    is_platform = True
    is_smalltalk = True


async def _fake_direct(writer, model_id, system_prompt, user_text, *, note=""):
    """The real ``_stream_direct``, minus the model.

    Mirrors its compose-then-text behaviour so the stage log under test is the one
    production produces, without importing the agent framework.
    """
    frame = writer.text_delta("Hello! Ask me about the platform.")
    if frame:
        compose = writer.composing()
        if compose:
            yield compose
        yield frame


class SmalltalkShortCircuitTest(unittest.TestCase):
    """A greeting must not search the docs — the log would expose the lie."""

    def setUp(self) -> None:
        self.recorder = _SearchRecorder()
        self._original_search = retrieval.search
        self._original_direct = agent._stream_direct
        retrieval.search = self.recorder  # type: ignore[assignment]
        agent._stream_direct = _fake_direct  # type: ignore[assignment]

    def tearDown(self) -> None:
        retrieval.search = self._original_search  # type: ignore[assignment]
        agent._stream_direct = self._original_direct  # type: ignore[assignment]

    def _greeting(self) -> list[dict]:
        async def drive() -> list[dict]:
            out: list[dict] = []
            agen = agent.run_turn(
                agent.TurnRequest(question="hi", run_id="greet"), verdict=_SmalltalkVerdict()
            )
            try:
                async for frame in agen:
                    out.append(frame)
            finally:
                await agen.aclose()
            return out

        return asyncio.run(drive())

    def test_a_greeting_never_calls_retrieval(self) -> None:
        self._greeting()
        self.assertEqual(self.recorder.calls, [])

    def test_a_greeting_logs_only_intent_and_compose(self) -> None:
        keys = [stage["stage"] for stage in _stages(self._greeting())]
        self.assertEqual(keys, [STAGE_INTENT, STAGE_COMPOSE])

    def test_a_greeting_emits_exactly_one_compose_stage(self) -> None:
        keys = [stage["stage"] for stage in _stages(self._greeting())]
        self.assertEqual(keys.count(STAGE_COMPOSE), 1)


class StageFrameShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.writer = FrameWriter(run_id="r", model="m")

    def test_a_stage_names_itself_and_carries_its_detail(self) -> None:
        frame = self.writer.stage(STAGE_KNOWLEDGE, "Searching the platform docs")
        self.assertEqual(frame["type"], FRAME_STAGE)
        self.assertEqual(frame["stage"], STAGE_KNOWLEDGE)
        self.assertEqual(frame["label"], "Searching the platform docs")
        # Absent, not empty: the client branches on presence.
        self.assertNotIn("detail", frame)
        self.assertNotIn("tool", frame)

    def test_detail_and_tool_are_carried_when_present(self) -> None:
        frame = self.writer.stage(
            "tool", "Locating the page you need", detail="Vault", tool="find_page"
        )
        self.assertEqual(frame["detail"], "Vault")
        self.assertEqual(frame["tool"], "find_page")

    def test_composing_fires_exactly_once(self) -> None:
        first = self.writer.composing()
        self.assertIsNotNone(first)
        assert first is not None
        self.assertEqual(first["stage"], STAGE_COMPOSE)
        self.assertIsNone(self.writer.composing())
        self.assertIsNone(self.writer.composing())


class StageSequenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = _SearchRecorder()
        self._original = retrieval.search
        retrieval.search = self.recorder  # type: ignore[assignment]

    def tearDown(self) -> None:
        retrieval.search = self._original  # type: ignore[assignment]

    def test_a_platform_question_announces_each_milestone_in_order(self) -> None:
        frames = _run(agent.TurnRequest(question="where do I rotate a key?", run_id="r1"))
        keys = [stage["stage"] for stage in _stages(frames)]
        # Intent before the classifier call, knowledge before the awaited search,
        # links once passages came back, plan before the agent loop.
        self.assertEqual(keys[:4], [STAGE_INTENT, STAGE_KNOWLEDGE, STAGE_LINKS, STAGE_PLAN])

    def test_intent_is_announced_before_the_verdict_frame(self) -> None:
        """The user is waiting on the classifier, so the stage must precede it."""
        frames = _run(agent.TurnRequest(question="q", run_id="r2"))
        kinds = [frame.get("type") for frame in frames]
        self.assertLess(kinds.index(FRAME_STAGE), kinds.index("ai-assistant.intent"))

    def test_knowledge_is_announced_before_retrieval_completes(self) -> None:
        """Order matters here: the stage is what the user reads *while* it runs."""
        frames = _run(agent.TurnRequest(question="q", run_id="r3"))
        kinds = [frame.get("type") for frame in frames]
        knowledge = next(
            index
            for index, frame in enumerate(frames)
            if frame.get("type") == FRAME_STAGE and frame.get("stage") == STAGE_KNOWLEDGE
        )
        self.assertLess(knowledge, len(kinds))
        self.assertEqual(len(self.recorder.calls), 1)

    def test_the_links_stage_reports_how_many_pages_matched(self) -> None:
        self.recorder.passages = [_passage(), _passage()]
        frames = _run(agent.TurnRequest(question="q", run_id="r4"))
        links = next(
            stage for stage in _stages(frames) if stage["stage"] == STAGE_LINKS
        )
        self.assertEqual(links["detail"], "2 matched")

    def test_a_search_that_matches_nothing_claims_nothing(self) -> None:
        self.recorder.passages = []
        frames = _run(agent.TurnRequest(question="q", run_id="r5"))
        self.assertNotIn(STAGE_LINKS, [stage["stage"] for stage in _stages(frames)])

    def test_no_compose_stage_before_any_text_arrives(self) -> None:
        """Claiming the answer is being written while the model still decides is a lie."""
        frames = _run(agent.TurnRequest(question="q", run_id="r6"))
        self.assertNotIn(STAGE_COMPOSE, [stage["stage"] for stage in _stages(frames)])


class ToolStageTest(unittest.TestCase):
    def test_every_tool_has_a_plain_language_label(self) -> None:
        for name in ("search_platform_docs", "find_page", "escalate_to_support"):
            label = agent._tool_label(name)
            self.assertTrue(label)
            # The label describes the job; the raw name rides in `tool`.
            self.assertNotEqual(label, name)

    def test_an_unknown_tool_still_gets_a_label(self) -> None:
        self.assertIn("custom-thing", agent._tool_label("custom-thing"))

    def test_the_detail_is_the_arg_that_matters(self) -> None:
        self.assertEqual(agent._tool_detail('{"query": "rotate a key"}'), "rotate a key")
        self.assertEqual(agent._tool_detail('{"feature": "Vault"}'), "Vault")

    def test_a_half_streamed_argument_yields_no_detail(self) -> None:
        """Tool arguments arrive as partial JSON; a broken value is worse than none."""
        self.assertEqual(agent._tool_detail('{"query": "rot'), "")
        self.assertEqual(agent._tool_detail(""), "")
        self.assertEqual(agent._tool_detail(None), "")


if __name__ == "__main__":
    unittest.main()

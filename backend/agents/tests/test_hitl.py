"""Unit tests for the human-in-the-loop helpers (pure, no Strands runtime)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import hitl, prompts  # noqa: E402


class QuestionFromInterruptTests(unittest.TestCase):
    def test_parses_question_options_and_custom_flag(self) -> None:
        interrupt = SimpleNamespace(
            id="v1:tool_call:abc:xyz",
            name=hitl.ASK_USER_TOOL,
            reason={
                "question": "Which region?",
                "options": ["us", "eu"],
                "allowCustom": False,
            },
        )
        parsed = hitl.question_from_interrupt(interrupt)
        self.assertEqual(parsed["question"], "Which region?")
        self.assertEqual(parsed["options"], ["us", "eu"])
        self.assertFalse(parsed["allowCustom"])
        self.assertEqual(parsed["questionId"], "v1:tool_call:abc:xyz")

    def test_ignores_other_interrupts(self) -> None:
        interrupt = SimpleNamespace(id="other", name="for_delete", reason={})
        self.assertIsNone(hitl.question_from_interrupt(interrupt))

    def test_string_reason_falls_back_to_a_question(self) -> None:
        interrupt = SimpleNamespace(id="q", name=hitl.ASK_USER_TOOL, reason="Pick one")
        parsed = hitl.question_from_interrupt(interrupt)
        self.assertEqual(parsed["question"], "Pick one")
        self.assertEqual(parsed["options"], [])
        self.assertTrue(parsed["allowCustom"])


class ToolUseIdTests(unittest.TestCase):
    def test_extracts_tool_use_id(self) -> None:
        self.assertEqual(
            hitl.tool_use_id_from_interrupt_id("v1:tool_call:toolu_123:deadbeef"),
            "toolu_123",
        )

    def test_hook_scoped_id_has_none(self) -> None:
        self.assertEqual(
            hitl.tool_use_id_from_interrupt_id("v1:middleware_agent_stream:abc"), ""
        )


class InterruptResponsesTests(unittest.TestCase):
    def test_converts_to_strands_shape(self) -> None:
        responses = hitl.interrupt_responses(
            {"interruptResponses": [{"interruptId": "i1", "response": "eu"}]}
        )
        self.assertEqual(
            responses,
            [{"interruptResponse": {"interruptId": "i1", "response": "eu"}}],
        )

    def test_empty_or_invalid_yields_none(self) -> None:
        self.assertIsNone(hitl.interrupt_responses({}))
        self.assertIsNone(
            hitl.interrupt_responses({"interruptResponses": [{"response": "x"}]})
        )


class PendingInterruptRecoveryTests(unittest.TestCase):
    def test_builds_skip_responses_for_pending_interrupts(self) -> None:
        owner = SimpleNamespace(
            _interrupt_state=SimpleNamespace(
                activated=True,
                interrupts={"i1": SimpleNamespace(id="i1", response=None)},
            )
        )
        responses = hitl.pending_interrupt_responses(owner, "Do something else")
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["interruptResponse"]["interruptId"], "i1")
        self.assertIn("Do something else", responses[0]["interruptResponse"]["response"])

    def test_none_when_not_activated(self) -> None:
        owner = SimpleNamespace(
            _interrupt_state=SimpleNamespace(activated=False, interrupts={})
        )
        self.assertIsNone(hitl.pending_interrupt_responses(owner, "hi"))

    def test_none_when_no_pending(self) -> None:
        owner = SimpleNamespace(
            _interrupt_state=SimpleNamespace(
                activated=True,
                interrupts={"i1": SimpleNamespace(id="i1", response="already")},
            )
        )
        self.assertIsNone(hitl.pending_interrupt_responses(owner, "hi"))


class WorkflowInterruptTests(unittest.TestCase):
    def test_node_interrupt_becomes_a_question_frame(self) -> None:
        from workflow import events as workflow_events

        frames = workflow_events.normalize(
            {
                "type": "multiagent_node_interrupt",
                "node_id": "host-synth",
                "interrupts": [
                    SimpleNamespace(
                        id="i1",
                        name=hitl.ASK_USER_TOOL,
                        reason={"question": "Q?", "options": ["a"], "allowCustom": True},
                    )
                ],
            }
        )
        self.assertEqual(frames[0]["type"], "question")
        self.assertEqual(frames[0]["questionId"], "i1")
        self.assertEqual(frames[0]["nodeId"], "host-synth")

    def test_other_interrupts_are_dropped(self) -> None:
        from workflow import events as workflow_events

        frames = workflow_events.normalize(
            {
                "type": "multiagent_node_interrupt",
                "node_id": "host",
                "interrupts": [SimpleNamespace(id="x", name="approve", reason={})],
            }
        )
        self.assertEqual(frames, [])


class StoredResponseTests(unittest.TestCase):
    """The anti-loop cap: a resumed run must not raise a *new* question."""

    def test_reads_the_stored_answer_for_a_replayed_call(self) -> None:
        interrupt = SimpleNamespace(response="eu")
        agent = SimpleNamespace(
            _interrupt_state=SimpleNamespace(interrupts={"iid": interrupt})
        )
        context = SimpleNamespace(_interrupt_id=lambda name: "iid", agent=agent)
        self.assertEqual(hitl._stored_response(context), "eu")

    def test_none_for_a_brand_new_call(self) -> None:
        agent = SimpleNamespace(_interrupt_state=SimpleNamespace(interrupts={}))
        context = SimpleNamespace(_interrupt_id=lambda name: "new", agent=agent)
        self.assertIsNone(hitl._stored_response(context))

    def test_none_when_state_is_unavailable(self) -> None:
        self.assertIsNone(hitl._stored_response(SimpleNamespace()))


class PromptInjectionTests(unittest.TestCase):
    def test_ask_mode_tells_the_agent_to_use_ask_user(self) -> None:
        prompt = prompts.build_system_prompt({"prompt": "p"}, [], human_in_loop=True)
        self.assertIn("`ask_user`", prompt)

    def test_assume_mode_tells_the_agent_not_to_ask(self) -> None:
        prompt = prompts.build_system_prompt({"prompt": "p"}, [], human_in_loop=False)
        self.assertIn("auto-approve", prompt)
        self.assertNotIn("`ask_user`", prompt)

    def test_ask_mode_is_restrictive(self) -> None:
        # HITL is only for genuine blocking choices, never for open-ended
        # "tell me more" questions (which must be answered, not asked back).
        prompt = prompts.build_system_prompt({"prompt": "p"}, [], human_in_loop=True)
        self.assertIn("open-ended", prompt)
        self.assertIn("at most ONE question", prompt)

    def test_default_omits_hitl_instructions(self) -> None:
        prompt = prompts.build_system_prompt({"prompt": "p"}, [])
        self.assertNotIn("`ask_user`", prompt)
        self.assertNotIn("auto-approve", prompt)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the workflow runtime (events, config merge, answer derivation)."""

from __future__ import annotations

import sys
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "packages"))

from workflow import events  # noqa: E402
from workflow.build import _graph_block, _host_config, _memory_tools, _team_block  # noqa: E402
from workflow.run import _final_answer, _node_payload, _sink_nodes  # noqa: E402
from workflow.store import merge_config, resolve_agent_nodes  # noqa: E402


class MemoryToolTests(unittest.TestCase):
    """Every workflow node shares the user's memory, so each one needs its tools.

    The managed store has no add tool of its own, so a node on that backend must
    be given one — otherwise a member agent cannot act on "remember this" at all,
    and the prompt's save instruction would name a tool that does not exist.
    """

    class _Manager:
        def __init__(self, *tool_names: str) -> None:
            from types import SimpleNamespace

            self.tools = [SimpleNamespace(tool_name=name) for name in tool_names]

    def test_no_memory_means_no_tools(self) -> None:
        self.assertEqual(_memory_tools(None, "u_1"), ([], False))

    def test_a_node_without_a_user_id_gets_nothing(self) -> None:
        self.assertEqual(_memory_tools(self._Manager("add_memory"), ""), ([], False))

    def test_local_manager_supplies_its_own_save_tool(self) -> None:
        tools, can_save = _memory_tools(self._Manager("search_memory", "add_memory"), "u_1")

        self.assertTrue(can_save)
        self.assertEqual([tool.tool_name for tool in tools], ["forget_memory"])

    def test_managed_backend_gets_an_explicit_save_tool(self) -> None:
        with mock.patch(
            "agentflow.memory.core_memory.is_agentcore", return_value=True
        ):
            tools, can_save = _memory_tools(self._Manager("search_memory"), "u_1")

        self.assertTrue(can_save)
        self.assertEqual(
            [tool.tool_name for tool in tools], ["forget_memory", "add_memory"]
        )

    def test_a_managed_manager_without_the_capability_is_not_promised_one(self) -> None:
        # AgentCore store, but the tool could not be built: never claim a save
        # tool the node does not have.
        with mock.patch(
            "agentflow.memory.core_memory.is_agentcore", return_value=False
        ):
            tools, can_save = _memory_tools(self._Manager("search_memory"), "u_1")

        self.assertFalse(can_save)
        self.assertEqual([tool.tool_name for tool in tools], ["forget_memory"])


class WorkflowEventTests(unittest.TestCase):
    META = {"research": {"agentName": "Researcher"}}

    def test_node_start(self) -> None:
        self.assertEqual(
            events.normalize({"type": "multiagent_node_start", "node_id": "research"}, self.META),
            [
                {
                    "type": "node.started",
                    "nodeId": "research",
                    "nodeName": "Researcher",
                    "agentName": "Researcher",
                }
            ],
        )

    def test_handoff(self) -> None:
        self.assertEqual(
            events.normalize(
                {
                    "type": "multiagent_handoff",
                    "from_node_ids": ["a"],
                    "to_node_ids": ["b"],
                    "message": "needs math",
                }
            ),
            [
                {
                    "type": "node.handoff",
                    "from": ["a"],
                    "to": ["b"],
                    "message": "needs math",
                }
            ],
        )

    def test_node_completed(self) -> None:
        class _Status:
            value = "completed"

        class _Usage:
            inputTokens = 10
            outputTokens = 5
            totalTokens = 15

        class _NodeResult:
            status = _Status()
            accumulated_usage = _Usage()

        frame = events.normalize(
            {
                "type": "multiagent_node_stop",
                "node_id": "a",
                "node_result": _NodeResult(),
            }
        )[0]
        self.assertEqual(frame["type"], "node.completed")
        self.assertEqual(frame["status"], "completed")
        self.assertEqual(frame["usage"]["totalTokens"], 15)

    def test_node_stream_nests_inner_frames(self) -> None:
        frames = events.normalize(
            {
                "type": "multiagent_node_stream",
                "node_id": "a",
                "event": {"data": "hello"},
            }
        )
        self.assertEqual(
            frames, [{"type": "node.stream", "nodeId": "a", "event": {"type": "text", "data": "hello"}}]
        )

    def test_node_stream_drops_inner_result(self) -> None:
        class _Result:
            pass

        frames = events.normalize(
            {
                "type": "multiagent_node_stream",
                "node_id": "a",
                "event": {"result": _Result()},
            }
        )
        self.assertEqual(frames, [])

    def test_unknown_event_is_ignored(self) -> None:
        self.assertEqual(events.normalize({"type": "something_else"}), [])
        self.assertEqual(events.normalize("nope"), [])


class MergeConfigTests(unittest.TestCase):
    def test_inherits_unset_fields(self) -> None:
        base = {"model": "mimo-v2.5", "prompt": "base", "servers": [{"id": "s1"}]}
        self.assertEqual(merge_config(base, {}), base)

    def test_overrides_only_changed_fields(self) -> None:
        base = {"model": "mimo-v2.5", "prompt": "base", "reasoning": "medium"}
        merged = merge_config(base, {"model": "kimi-k2.6", "prompt": None})
        self.assertEqual(merged["model"], "kimi-k2.6")
        self.assertEqual(merged["prompt"], "base")

    def test_overrides_list_fields(self) -> None:
        base = {"servers": [{"id": "s1"}], "skillIds": ["a"]}
        merged = merge_config(base, {"servers": [{"id": "s2"}], "skillIds": []})
        self.assertEqual(merged["servers"], [{"id": "s2"}])
        self.assertEqual(merged["skillIds"], [])


class SinkNodeTests(unittest.TestCase):
    def test_sinks_are_agents_with_no_agent_out_edge(self) -> None:
        config = {
            "nodes": [
                {"id": "in", "type": "input"},
                {"id": "a", "type": "agent"},
                {"id": "b", "type": "agent"},
                {"id": "c", "type": "agent"},
                {"id": "out", "type": "output"},
            ],
            "edges": [
                {"source": "in", "target": "a"},
                {"source": "a", "target": "b"},
                {"source": "b", "target": "c"},
                {"source": "c", "target": "out"},
            ],
        }
        self.assertEqual(_sink_nodes(config), ["c"])


class FinalAnswerTests(unittest.TestCase):
    def test_host_answer_wins(self) -> None:
        text = {"host": "final", "other": "scratch"}
        self.assertEqual(_final_answer("swarm", "host", [], text, ["other", "host"]), "final")

    def test_graph_falls_back_to_sinks(self) -> None:
        text = {"a": "first", "b": "second"}
        self.assertEqual(
            _final_answer("graph", "host-synth", ["a", "b"], text, ["a", "b"]),
            "first\n\nsecond",
        )

    def test_falls_back_to_last_node(self) -> None:
        text = {"a": "only"}
        self.assertEqual(_final_answer("graph", "host-synth", [], text, ["a"]), "only")


class NodePayloadTests(unittest.TestCase):
    def test_node_ids_and_host_stage_are_emitted(self) -> None:
        payload = _node_payload(
            [
                {
                    "nodeId": "host",
                    "agentName": "Host",
                    "model": "mimo-v2.5",
                    "role": "host",
                    "stage": "dispatch",
                },
                {
                    "nodeId": "testing-agent-3",
                    "agentName": "testing-agent",
                    "model": "mimo-v2.5",
                    "role": "agent",
                },
            ]
        )
        # The client keys nodes by `id`; `nodeId` is the internal frame name.
        self.assertEqual([node["id"] for node in payload], ["host", "testing-agent-3"])
        self.assertNotIn("nodeId", payload[0])
        self.assertEqual(payload[0]["stage"], "dispatch")
        self.assertEqual(payload[1]["role"], "agent")
        self.assertIsNone(payload[1]["stage"])


class HostConfigTests(unittest.TestCase):
    def test_host_overrides_apply_to_the_host(self) -> None:
        base, _ = _host_config(
            {"input": {"prompt": "x"}},
            "markdown",
            {"answerMode": "detailed", "reasoning": "high"},
        )
        self.assertEqual(base["answerMode"], "detailed")
        self.assertEqual(base["reasoning"], "high")

    def test_host_without_overrides_is_left_default(self) -> None:
        base, _ = _host_config({"input": {"prompt": "x"}}, "markdown", None)
        self.assertNotIn("answerMode", base)
        self.assertNotIn("reasoning", base)


class AgentSelectionTests(unittest.TestCase):
    WORKFLOW = {
        "nodes": [
            {"id": "research", "type": "agent", "data": {"agentId": "a1"}},
            {"id": "writer", "type": "agent", "data": {"agentId": "a2"}},
        ],
        "edges": [],
    }

    AGENTS = {
        "a1": {"agentId": "a1", "name": "Research", "config": {"prompt": "p"}},
        "a2": {"agentId": "a2", "name": "Writer", "config": {"prompt": "p"}},
        "a3": {"agentId": "a3", "name": "New Agent", "config": {"prompt": "p"}},
    }

    def _resolve(self, agent_ids):
        with mock.patch(
            "workflow.store.agents_repo.get_agent",
            side_effect=lambda _user, agent_id: self.AGENTS.get(agent_id),
        ):
            return resolve_agent_nodes("u_1", self.WORKFLOW, agent_ids)

    def test_without_override_uses_saved_nodes(self) -> None:
        specs = self._resolve(None)
        self.assertEqual([spec["nodeId"] for spec in specs], ["research", "writer"])

    def test_override_removes_and_adds_agents(self) -> None:
        specs = self._resolve(["a2", "a3"])
        # Existing agent keeps its node id; a new one gets a slug id.
        self.assertEqual([spec["nodeId"] for spec in specs], ["writer", "new-agent"])
        self.assertEqual([spec["agentId"] for spec in specs], ["a2", "a3"])

    def test_override_empty_runs_nobody(self) -> None:
        self.assertEqual(self._resolve([]), [])


class PromptBlockTests(unittest.TestCase):
    def test_team_block_lists_teammates(self) -> None:
        specs = [
            {"nodeId": "researcher", "agentName": "Researcher", "description": "researches"},
            {"nodeId": "writer", "agentName": "Writer", "description": "writes"},
        ]
        block = _team_block(specs)
        self.assertIn("`researcher` — Researcher — researches", block)
        self.assertIn("`writer` — Writer — writes", block)

    def test_graph_block_mentions_handoff_of_output(self) -> None:
        self.assertIn("passed to the next step", _graph_block())


if __name__ == "__main__":
    unittest.main()

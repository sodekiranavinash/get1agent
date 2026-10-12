"""Trace builders: the multi-agent projection and the enrichment fields.

Multi-agent workflow runs used to persist no trace at all, so they were missing
from the Traces page. These cover the projection plus the per-span cost, run
error detail and system-prompt capture the viewer relies on.

Run with: ``make -C backend/services/apis/user-api test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
for candidate in (ROOT / 'agents', ROOT / 'backend' / 'packages'):
    sys.path.insert(0, str(candidate))

from agentflow.traces import build_trace, build_workflow_trace  # noqa: E402

WORKFLOW_EVENTS = [
    {"type": "node.started", "nodeId": "researcher", "agentName": "Researcher", "_at": 1000},
    {
        "type": "node.stream",
        "nodeId": "researcher",
        "_at": 1100,
        "event": {
            "type": "tool.start",
            "toolUseId": "t1",
            "name": "http-fetch",
            "input": {"url": "x"},
        },
    },
    {
        "type": "node.stream",
        "nodeId": "researcher",
        "_at": 1400,
        "event": {
            "type": "tool.result",
            "toolUseId": "t1",
            "data": {"ok": True},
            "status": "success",
        },
    },
    {
        "type": "node.completed",
        "nodeId": "researcher",
        "status": "success",
        "usage": {"inputTokens": 10},
        "_at": 1500,
    },
    {"type": "node.handoff", "from": ["researcher"], "to": ["writer"], "message": "go", "_at": 1600},
    {"type": "node.started", "nodeId": "writer", "agentName": "Writer", "_at": 1700},
    {"type": "node.completed", "nodeId": "writer", "status": "success", "_at": 2000},
]


class WorkflowTraceTests(unittest.TestCase):
    """A workflow run produces a run -> node -> tool tree."""

    def _trace(self):
        return build_workflow_trace(
            trace_id="tr1",
            run_id="r1",
            user_id="u1",
            workflow_id="wf1",
            workflow_name="Research flow",
            model="m1",
            provider=None,
            conversation_id="c1",
            mode="graph",
            question="q",
            answer="a",
            status="completed",
            started_at="2026-10-11T10:00:00+00:00",
            ended_at="2026-10-11T10:00:05+00:00",
            events=WORKFLOW_EVENTS,
            usage={"inputTokens": 100, "outputTokens": 50},
            nodes=[{"id": "researcher", "name": "Researcher"}],
        )

    def test_trace_shape(self) -> None:
        trace = self._trace()
        self.assertEqual(trace["name"], "workflow:Research flow")
        self.assertEqual(trace["targetType"], "workflow")
        self.assertEqual(trace["observationCount"], 6)
        self.assertEqual(trace["summary"]["typeCounts"]["TOOL"], 1)
        self.assertEqual(trace["summary"]["errorCount"], 0)
        self.assertGreaterEqual(trace["costMicroUsd"], 0)
        self.assertEqual(trace["observations"][0]["metadata"]["mode"], "graph")

    def test_spans_nest_and_timings_are_real(self) -> None:
        trace = self._trace()
        observations = trace["observations"]
        tool = next(o for o in observations if o["type"] == "TOOL")
        researcher = next(o for o in observations if o["name"] == "Researcher")
        self.assertEqual(tool["parentObservationId"], researcher["id"])
        self.assertEqual(tool["durationMs"], 300)
        self.assertEqual(researcher["durationMs"], 500)


class AgentTraceTests(unittest.TestCase):
    """The single-agent builder records the error detail and system prompt."""

    def test_error_and_system_prompt_are_captured(self) -> None:
        trace = build_trace(
            trace_id="tr2",
            run_id="r2",
            user_id="u1",
            agent_id="a1",
            agent_name="A",
            model="m1",
            provider="bedrock",
            conversation_id="c1",
            question="q",
            answer="a",
            status="error",
            started_at="2026-10-11T10:00:00+00:00",
            ended_at="2026-10-11T10:00:02+00:00",
            events=[
                {
                    "type": "run.error",
                    "message": "boom",
                    "errorKind": "ValueError",
                    "detail": "ValueError('boom')",
                    "stack": "Traceback...",
                    "_at": 1500,
                }
            ],
            usage={"inputTokens": 10, "outputTokens": 5},
            tags=["t"],
            system_prompt_text="You are helpful.",
        )
        self.assertGreaterEqual(trace["summary"]["errorCount"], 1)
        self.assertEqual(trace["statusMessage"], "boom")
        error = next(o for o in trace["observations"] if o["name"] == "error")
        self.assertEqual(error["metadata"]["stack"], "Traceback...")
        root = trace["observations"][0]
        self.assertEqual(root["metadata"]["systemPrompt"], "You are helpful.")
        self.assertGreaterEqual(root["costMicroUsd"], 0)


if __name__ == "__main__":
    unittest.main()

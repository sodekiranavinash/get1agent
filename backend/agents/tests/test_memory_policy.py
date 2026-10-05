"""Unit tests for the memory backend switch + the policy guard."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "packages"))

from agentflow import memory  # noqa: E402


def _config(**overrides):
    from agentflow.config import RuntimeConfig

    base = dict(
        bedrock_region="ap-south-1",
        dynamodb_table="get1agent",
        s3_bucket="b",
        s3_region="ap-south-1",
        vector_store="s3vectors",
        s3_vector_bucket="vb",
        knowledge_function="",
        code_interpreter_function="",
        http_fetch_function="",
        storage_function="",
        browser_function="",
        remote_function="",
        custom_tools_function="",
        session_prefix="agent-sessions/",
        max_turns=40,
        planner_model="zai.glm-4.7-flash",
        planner_enabled=True,
        memory_backend="dynamo",
        memory_id="",
        policy_engine="",
        mcp_transport="aggregator",
        gateway_url="",
        web_search_gateway_tool="web-search___WebSearch",
        web_search_gateway_url="",
        web_search_gateway_region="",
    )
    base.update(overrides)
    return RuntimeConfig(**base)


class MemoryBackendTests(unittest.TestCase):
    def test_dynamo_is_default(self) -> None:
        manager = memory.build_memory_manager(_config(), "u_1", session_id="7")
        self.assertIsInstance(manager._stores[0], memory.DynamoMemoryStore)

    def test_agentcore_without_id_is_a_hard_error(self) -> None:
        with self.assertRaises(RuntimeError):
            memory.build_memory_manager(
                _config(memory_backend="agentcore", memory_id=""), "u_1", session_id="7"
            )

    def test_agentcore_uses_managed_store(self) -> None:
        class _StoreStub:
            writable = True
            name = "user_memory"
            description = ""
            max_search_results = 5
            extraction = True

            async def add(self, *_args, **_kwargs):
                return ""

            async def search(self, *_args, **_kwargs):
                return []

        sentinel = _StoreStub()
        with mock.patch(
            "bedrock_agentcore.memory.integrations.strands.memorystore.AgentCoreMemoryStore",
            return_value=sentinel,
        ) as ctor:
            manager = memory.build_memory_manager(
                _config(memory_backend="agentcore", memory_id="mem-123"),
                "u_1",
                session_id="7",
            )
        self.assertIs(manager._stores[0], sentinel)
        kwargs = ctor.call_args.kwargs
        self.assertEqual(kwargs["memory_id"], "mem-123")
        self.assertEqual(kwargs["actor_id"], "u_1")
        self.assertEqual(kwargs["session_id"], "7")
        # User-scoped namespace (no session/agent component) -> cross-session recall.
        self.assertEqual(kwargs["namespace_path"], "/users/{actorId}/")
        self.assertTrue(kwargs["writable"])

    def test_dynamo_backend_is_opt_in(self) -> None:
        manager = memory.build_memory_manager(
            _config(memory_backend="dynamo"), "u_1", session_id="7"
        )
        self.assertIsInstance(manager._stores[0], memory.DynamoMemoryStore)


class GuardTests(unittest.TestCase):
    def test_no_checker_admits_everything(self) -> None:
        guard = memory.build_guard(None)
        self.assertEqual(guard("anything", {"a": 1}), (True, ""))

    def test_guard_fails_closed_on_error(self) -> None:
        def boom(_name, _args):
            raise RuntimeError("policy engine down")

        allowed, reason = memory.build_guard(boom)("web-search", {})
        self.assertFalse(allowed)
        self.assertIn("fail", reason.lower())

    def test_guard_forwards_decision(self) -> None:
        guard = memory.build_guard(lambda name, _args: (name != "bad", "nope"))
        allowed, _reason = guard("good", {})
        self.assertTrue(allowed)
        allowed, reason = guard("bad", {})
        self.assertFalse(allowed)
        self.assertEqual(reason, "nope")


class PolicyConfigTests(unittest.TestCase):
    def test_disabled_without_engine(self) -> None:
        from core import policy

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_POLICY_ENGINE", None)
            self.assertFalse(policy.enabled())
            self.assertIsNone(policy.build_evaluator())

    def test_deny_list_blocks(self) -> None:
        from core import policy

        env = {"AGENT_POLICY_ENGINE": "pe-1", "AGENT_POLICY_DENY_TOOLS": "http-fetch, browser"}
        with mock.patch.dict(os.environ, env, clear=False):
            evaluate = policy.build_evaluator()
            self.assertTrue(evaluate("web-search", {})[0])
            self.assertFalse(evaluate("http-fetch", {})[0])
            self.assertFalse(evaluate("browser", {})[0])

    def test_allow_list_restricts(self) -> None:
        from core import policy

        env = {"AGENT_POLICY_ENGINE": "pe-1", "AGENT_POLICY_ALLOW_TOOLS": "web-search"}
        with mock.patch.dict(os.environ, env, clear=False):
            os.environ.pop("AGENT_POLICY_DENY_TOOLS", None)
            evaluate = policy.build_evaluator()
            self.assertTrue(evaluate("web-search", {})[0])
            self.assertFalse(evaluate("code-interpreter", {})[0])

    def test_report_mode_never_blocks(self) -> None:
        from core import policy

        env = {
            "AGENT_POLICY_ENGINE": "pe-1",
            "AGENT_POLICY_DENY_TOOLS": "http-fetch",
            "AGENT_POLICY_MODE": "report",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            evaluate = policy.build_evaluator()
            allowed, _ = policy.evaluate_or_report("http-fetch", {}, evaluate)
        self.assertTrue(allowed)


if __name__ == "__main__":
    unittest.main()

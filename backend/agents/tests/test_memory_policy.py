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

    def test_memory_is_injected_on_every_model_call(self) -> None:
        # Strands' default trigger, "userTurn", folds the memory block into the
        # latest user *ask* only. A run's final answer follows a tool result, so
        # with the default the model wrote that answer having never seen the
        # memory — and reported "I couldn't find it" while the block held the
        # fact. Every question about the user that also consulted a tool was
        # affected, which is why this is pinned for both backends.
        dynamo = memory.build_memory_manager(_config(), "u_1", session_id="7")
        self.assertEqual(dynamo._injection_config["trigger"], "everyTurn")
        self.assertIs(dynamo._injection_config["query"], memory._memory_injection_query)

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

        with mock.patch(
            "bedrock_agentcore.memory.integrations.strands.memorystore.AgentCoreMemoryStore",
            return_value=_StoreStub(),
        ):
            managed = memory.build_memory_manager(
                _config(memory_backend="agentcore", memory_id="mem-123"),
                "u_1",
                session_id="7",
            )
        self.assertEqual(managed._injection_config["trigger"], "everyTurn")


class MemoryCanSaveTests(unittest.TestCase):
    """Only a manager with a real add tool may be advertised as saving memory.

    The save instruction tells the model to call ``add_memory``, so it is added to
    the prompt only when that tool exists. The Dynamo backend has it; the
    AgentCore store does not (``add_messages`` + server-side extraction instead),
    so a prod run must never be told to call it.
    """

    @staticmethod
    def _manager(*tool_names: str):
        from types import SimpleNamespace

        return SimpleNamespace(tools=[SimpleNamespace(tool_name=n) for n in tool_names])

    def test_true_when_an_add_tool_is_registered(self) -> None:
        self.assertTrue(
            memory.memory_can_save(self._manager("search_memory", "add_memory"))
        )

    def test_false_without_an_add_tool(self) -> None:
        self.assertFalse(memory.memory_can_save(self._manager("search_memory")))

    def test_false_for_none_and_a_manager_without_tools(self) -> None:
        self.assertFalse(memory.memory_can_save(None))
        self.assertFalse(memory.memory_can_save(object()))

    def test_dynamo_backend_exposes_the_add_tool(self) -> None:
        # The local/dev backend has extraction off, so `add_memory` is the only
        # write path — nothing is remembered without it.
        manager = memory.build_memory_manager(
            _config(memory_backend="dynamo"), "u_1", session_id="7"
        )
        self.assertTrue(memory.memory_can_save(manager))

    def test_agentcore_store_does_not_advertise_saving(self) -> None:
        class _StoreStub:
            writable = True
            name = "user_memory"
            description = ""
            max_search_results = 5
            extraction = True

            async def add_messages(self, *_args, **_kwargs):
                return ""

            async def search(self, *_args, **_kwargs):
                return []

        with mock.patch(
            "bedrock_agentcore.memory.integrations.strands.memorystore.AgentCoreMemoryStore",
            return_value=_StoreStub(),
        ):
            manager = memory.build_memory_manager(
                _config(memory_backend="agentcore", memory_id="mem-123"),
                "u_1",
                session_id="7",
            )
        self.assertFalse(memory.memory_can_save(manager))


class SaveMemoriesTests(unittest.TestCase):
    """The explicit save path for the managed backend.

    ``AgentCoreMemoryStore`` has no ``add`` — it ingests invocations and waits for
    asynchronous extraction — so on that backend the runtime supplies its own
    ``add_memory`` tool that writes a consolidated record directly.
    """

    def test_writes_each_entry_with_the_kind(self) -> None:
        recorded: list[tuple[str, str, str]] = []

        def fake_save(user_id, text, kind="preference"):
            recorded.append((user_id, text, kind))
            return {"id": "mem-1", "failed": []}

        with mock.patch.object(memory.core_memory, "save_record", side_effect=fake_save):
            out = memory.save_memories(
                "u_1", ["  The user likes red.  ", "The user is in Mumbai."], kind="fact"
            )

        self.assertEqual(out, {"saved": 2})
        self.assertEqual(
            recorded,
            [
                ("u_1", "The user likes red.", "fact"),
                ("u_1", "The user is in Mumbai.", "fact"),
            ],
        )

    def test_one_failure_does_not_lose_the_rest(self) -> None:
        def flaky(_user_id, text, kind="preference"):
            if "bad" in text:
                raise RuntimeError("boom")
            return {"id": "mem-1", "failed": []}

        with mock.patch.object(memory.core_memory, "save_record", side_effect=flaky):
            out = memory.save_memories("u_1", ["good one", "bad one"])

        self.assertEqual(out["saved"], 1)
        self.assertIn("boom", out["error"])

    def test_a_rejected_record_is_reported(self) -> None:
        with mock.patch.object(
            memory.core_memory,
            "save_record",
            return_value={"id": "", "failed": [{"requestIdentifier": "x"}]},
        ):
            out = memory.save_memories("u_1", ["The user likes red."])

        self.assertEqual(out["saved"], 0)
        self.assertIn("memory write failed", out["error"])

    def test_an_already_saved_memory_counts_as_saved(self) -> None:
        # The service deduplicates a replayed write via the token; the memory is
        # there, so the model must not be told the save failed.
        with mock.patch.object(
            memory.core_memory,
            "save_record",
            return_value={"id": "", "text": "x", "failed": [], "duplicate": True},
        ):
            out = memory.save_memories("u_1", ["The user likes red."])

        self.assertEqual(out, {"saved": 1})

    def test_no_entries_is_an_error_not_a_write(self) -> None:
        with mock.patch.object(memory.core_memory, "save_record") as save:
            out = memory.save_memories("u_1", ["   ", ""])

        save.assert_not_called()
        self.assertEqual(out, {"saved": 0, "error": "entries is required"})

    def test_no_save_tool_on_the_local_backend(self) -> None:
        # The Dynamo backend's manager already registers its own `add_memory`;
        # a second tool with that name would collide.
        with mock.patch.object(memory.core_memory, "is_agentcore", return_value=False):
            self.assertIsNone(memory.build_save_memory_tool("u_1"))

    def test_save_tool_is_add_memory_on_the_managed_backend(self) -> None:
        with mock.patch.object(memory.core_memory, "is_agentcore", return_value=True):
            tool_obj = memory.build_save_memory_tool("u_1")

        self.assertEqual(tool_obj.tool_name, "add_memory")
        # `entries` is the same primary argument the manager's own add tool takes,
        # so the model's call shape is identical on both backends.
        schema = tool_obj.tool_spec["inputSchema"]
        inner = schema.get("json") or schema
        self.assertEqual(inner["required"], ["entries"])
        self.assertIn("kind", inner["properties"])

    def test_tool_writes_through_with_the_bound_user(self) -> None:
        import asyncio

        recorded: list[tuple[str, str, str]] = []

        def fake_save(user_id, text, kind="preference"):
            recorded.append((user_id, text, kind))
            return {"id": "mem-1", "failed": []}

        with mock.patch.object(
            memory.core_memory, "is_agentcore", return_value=True
        ), mock.patch.object(memory.core_memory, "save_record", side_effect=fake_save):
            tool_obj = memory.build_save_memory_tool("u_1")

            async def run() -> None:
                tool_use = {
                    "toolUseId": "1",
                    "name": "add_memory",
                    "input": {"entries": ["The user likes red."]},
                }
                async for _ in tool_obj.stream(tool_use, {}):
                    pass

            asyncio.run(run())

        self.assertEqual(recorded, [("u_1", "The user likes red.", "preference")])


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
            # The guard itself is mode-aware, so the runtimes that call
            # build_evaluator() honor `report` without extra wiring.
            evaluate = policy.build_evaluator()
            allowed, _ = evaluate("http-fetch", {})
            # Wrapping again stays idempotent.
            allowed_again, _ = policy.evaluate_or_report("http-fetch", {}, evaluate)
        self.assertTrue(allowed)
        self.assertTrue(allowed_again)

    def test_enforce_mode_still_blocks(self) -> None:
        from core import policy

        env = {
            "AGENT_POLICY_ENGINE": "pe-1",
            "AGENT_POLICY_DENY_TOOLS": "http-fetch",
            "AGENT_POLICY_MODE": "enforce",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            allowed, reason = policy.build_evaluator()("http-fetch", {})
        self.assertFalse(allowed)
        self.assertIn("denied", reason)


class MemoryInjectionQueryTests(unittest.TestCase):
    """The injection query must come from the user's ask, not the last tool step.

    Strands' default derives it from the most recent *assistant* message on a
    tool-result turn — a tool-use step carrying no text — so the query was empty
    and injection was skipped on the very call that writes the answer.
    """

    @staticmethod
    def _context(*messages):
        from types import SimpleNamespace

        return SimpleNamespace(messages=list(messages))

    def test_uses_the_users_ask_not_the_last_tool_step(self) -> None:
        context = self._context(
            {"role": "user", "content": [{"text": "what is my dog's name?"}]},
            {"role": "assistant", "content": [{"toolUse": {"name": "search"}}]},
            {"role": "user", "content": [{"toolResult": {"content": []}}]},
        )
        self.assertEqual(
            memory._memory_injection_query(context), "what is my dog's name?"
        )

    def test_takes_the_latest_ask(self) -> None:
        context = self._context(
            {"role": "user", "content": [{"text": "first"}]},
            {"role": "assistant", "content": [{"text": "ok"}]},
            {"role": "user", "content": [{"text": "second"}]},
        )
        self.assertEqual(memory._memory_injection_query(context), "second")

    def test_no_user_message_yields_no_query(self) -> None:
        context = self._context({"role": "assistant", "content": [{"text": "hi"}]})
        self.assertEqual(memory._memory_injection_query(context), "")

    def test_caps_a_large_run_input(self) -> None:
        # A run's input carries folded plan text and attachments.
        context = self._context({"role": "user", "content": [{"text": "x" * 5000}]})
        self.assertEqual(len(memory._memory_injection_query(context)), 2000)


if __name__ == "__main__":
    unittest.main()

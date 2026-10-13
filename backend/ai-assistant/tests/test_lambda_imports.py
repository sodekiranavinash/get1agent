"""The Lambda's import graph must stay split: the guest route never loads LangChain.

There is one Lambda now, and it serves both routes. That makes the import graph the
thing worth pinning: `handler` is imported on **every** invocation, including a
guest's, so anything it pulls in at module scope is paid for by both audiences —
and the agent framework (LangChain, LangGraph, Deep Agents, and the numerical stack
LangChain-AWS drags in) is the expensive one.

`src/agent.py` imports the framework **inside** the functions that use it, and
`handler` imports `src.agent` only inside the signed-in turn, so a guest turn never
pays for it. That is easy to break with one convenient top-level import, and the
break would only show up as a slower, larger cold start — so it is pinned here.

These tests run the real handler in-process with the model calls stubbed. No AWS.
"""

from __future__ import annotations

import builtins
import json
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parent / "packages"
for extra in (str(SERVICE_ROOT), str(PACKAGES)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

#: The agent framework and the provider SDKs it drags in. `numpy` matters because
#: `langchain-aws` depends on it.
FORBIDDEN = (
    "langchain",
    "langchain_core",
    "langchain_aws",
    "langgraph",
    "deepagents",
    "langsmith",
    "anthropic",
    "numpy",
    "google",
)

#: The modules the guest route legitimately needs, imported *after* the guard is
#: installed — so a stray framework import inside them fails here too.
GUEST_MODULES = ("src.frames", "src.llm", "src.metrics", "src.classifier", "src.retrieval")


def _fresh_import(name: str, guard) -> object:
    """Import `name` with `guard` watching, after dropping cached copies."""
    for module in list(sys.modules):
        root = module.split(".")[0]
        if root in FORBIDDEN or module == name or module.startswith(name + "."):
            del sys.modules[module]
    real = builtins.__import__
    builtins.__import__ = guard
    try:
        return __import__(name)
    finally:
        builtins.__import__ = real


class GuestImportGraphTests(unittest.TestCase):
    def _guard(self):
        real_import = builtins.__import__

        def guard(name, *args, **kwargs):
            if name.split(".")[0] in FORBIDDEN:
                raise ImportError(f"{name} must not be reachable from the guest path")
            return real_import(name, *args, **kwargs)

        return guard

    def test_handler_imports_without_the_agent_framework(self):
        handler = _fresh_import("handler", self._guard())
        self.assertTrue(callable(handler.lambda_handler))

    def test_the_guest_modules_import_without_the_agent_framework(self):
        for name in GUEST_MODULES:
            with self.subTest(module=name):
                module = _fresh_import(name, self._guard())
                self.assertIsNotNone(module)

    def test_streaming_adapter_is_gone(self):
        """The Function URL adapter was the only reason `streaming.py` existed.

        Answers are buffered through API Gateway now, so a response-streaming
        adapter left behind would be dead code that implies a capability the
        deployment does not have.
        """
        self.assertFalse((SERVICE_ROOT / "src" / "streaming.py").exists())

    def test_agent_module_defers_the_framework_import(self):
        """`src/agent.py` must be importable where LangChain is absent.

        The framework is imported *inside* the functions that use it; a top-level
        import would defeat the split above.
        """
        source = (SERVICE_ROOT / "src" / "agent.py").read_text(encoding="utf-8")
        offenders: list[str] = []
        for line in source.splitlines():
            # Only column-zero imports are module-level; an indented import is
            # inside a function, which is exactly the pattern we want.
            if line[:1] in (" ", "\t", "#"):
                continue
            if not line.startswith(("import ", "from ")):
                continue
            if any(root in line for root in ("langchain", "langgraph", "deepagents")):
                offenders.append(line)
        self.assertEqual(
            offenders,
            [],
            f"the agent module must import the framework lazily, found: {offenders}",
        )

    def test_handler_defers_the_agent_import(self):
        """`handler` must not import `src.agent` at module scope.

        The guest route never runs the agent graph, so importing it up front would
        charge every guest question for the framework.
        """
        source = (SERVICE_ROOT / "handler.py").read_text(encoding="utf-8")
        for line in source.splitlines():
            if line[:1] in (" ", "\t", "#"):
                continue
            if line.startswith(("import ", "from ")) and "src.agent" in line:
                self.fail(f"src.agent must be imported lazily, found: {line}")


class BufferedResponseTests(unittest.TestCase):
    """The response contract: one SSE body, framed exactly as the widget parses it."""

    @classmethod
    def setUpClass(cls):
        import handler  # noqa: PLC0415

        cls.handler = handler

    def _frames(self) -> list[dict]:
        frames = [
            {"type": "run.started", "runId": "r1", "agentId": "ai-assistant", "sessionId": "r1"},
            {"type": "text", "data": "hello"},
            {"type": "run.completed", "text": "hello", "stopReason": "end_turn"},
        ]
        return frames

    def test_sse_body_is_parseable_frame_by_frame(self):
        response = self.handler._sse_response(self._frames())
        self.assertEqual(response["statusCode"], 200)
        self.assertIn("text/event-stream", response["headers"]["content-type"])
        self.assertFalse(response["isBase64Encoded"])
        parsed = [
            json.loads(part[len("data: ") :].strip())
            for part in response["body"].split("\n\n")
            if part.startswith("data: ")
        ]
        self.assertEqual(parsed, self._frames())

    def test_an_oversized_run_is_replaced_by_one_error_frame(self):
        huge = [{"type": "text", "data": "x" * 1_000_000} for _ in range(8)]
        response = self.handler._sse_response(huge)
        parsed = [
            json.loads(part[len("data: ") :].strip())
            for part in response["body"].split("\n\n")
            if part.startswith("data: ")
        ]
        self.assertEqual(parsed[-1]["type"], "run.error")
        self.assertLess(len(response["body"]), self.handler.MAX_RESPONSE_BYTES)

    def test_the_error_body_carries_the_fields_the_widget_reads(self):
        response = self.handler._error_response(
            429, "rate_limited", "too many", retry_after=30, sign_in_required=True
        )
        self.assertEqual(response["statusCode"], 429)
        self.assertEqual(response["headers"]["retry-after"], "30")
        body = json.loads(response["body"])
        self.assertEqual(body["error"], "too many")
        self.assertEqual(body["retryAfterSeconds"], 30)
        self.assertTrue(body["signInRequired"])


if __name__ == "__main__":
    unittest.main()

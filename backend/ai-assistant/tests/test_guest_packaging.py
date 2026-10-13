"""The guest Lambda must not depend on the agent framework.

The guest path is a single direct model call: it needs Bedrock, the shared
packages and AI Assistant's own classifier/retrieval — but **not** LangChain, LangGraph,
Deep Agents, or a numerical stack. That is what keeps the guest zip small and its
cold start short (the Makefile excludes those packages from the zip), and it is
easy to break accidentally by adding a convenient top-level import.

This test imports the packaged handler with those modules blocked, so the
regression fails here rather than as an ImportError in production.
"""

from __future__ import annotations

import builtins
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parent / "packages"
for extra in (str(SERVICE_ROOT), str(PACKAGES)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

#: Modules the guest path must never need. `numpy` matters because
#: `langchain-aws` depends on it; the rest are the agent framework and the other
#: provider SDKs it drags in.
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


class GuestPackagingTests(unittest.TestCase):
    def test_handler_imports_without_the_agent_framework(self):
        real_import = builtins.__import__

        def guard(name, *args, **kwargs):
            root = name.split(".")[0]
            if root in FORBIDDEN:
                raise ImportError(f"{name} must not be needed by the guest path")
            return real_import(name, *args, **kwargs)

        # Drop anything already imported so the guard actually sees the imports.
        for module in list(sys.modules):
            if module.split(".")[0] in FORBIDDEN:
                del sys.modules[module]
        for module in [m for m in sys.modules if m == "handler" or m.startswith("src")]:
            del sys.modules[module]

        builtins.__import__ = guard
        try:
            import handler  # noqa: PLC0415

            self.assertTrue(callable(handler.lambda_handler))
        finally:
            builtins.__import__ = real_import

    def test_the_guest_modules_are_importable_on_their_own(self):
        """The shared package must stay importable without the agent stack."""
        from src import frames, llm, metrics, streaming  # noqa: PLC0415

        self.assertTrue(callable(frames.sse))
        self.assertTrue(callable(llm.stream_direct))
        self.assertTrue(callable(metrics.turn))
        self.assertIn(streaming.mode(), ("buffered", "awslambda-streaming", "awslambda-plain", "lambda_runtime"))

    def test_agent_module_defers_the_framework_import(self):
        """`ai-assistant.agent` must be importable even where LangChain is absent.

        This is the invariant that lets one shared package serve both a slim
        Lambda zip and the full container: the framework is imported *inside* the
        functions that use it.
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


if __name__ == "__main__":
    unittest.main()

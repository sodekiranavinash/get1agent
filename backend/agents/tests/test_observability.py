"""Unit tests for the Langfuse tracing gate (no network, no langfuse install)."""

from __future__ import annotations

import contextlib
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import observability  # noqa: E402

_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")


@contextlib.contextmanager
def no_langfuse_env():
    """Run the block with the Langfuse env vars removed."""
    with mock.patch.dict(os.environ, {}, clear=False):
        for key in _KEYS:
            os.environ.pop(key, None)
        yield


class EnabledTests(unittest.TestCase):
    def test_disabled_without_keys(self) -> None:
        with no_langfuse_env():
            self.assertFalse(observability.enabled())

    def test_disabled_with_only_public_key(self) -> None:
        with mock.patch.dict(os.environ, {"LANGFUSE_PUBLIC_KEY": "pk-lf-1"}, clear=False):
            os.environ.pop("LANGFUSE_SECRET_KEY", None)
            self.assertFalse(observability.enabled())

    def test_enabled_with_both_keys(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"LANGFUSE_PUBLIC_KEY": "pk-lf-1", "LANGFUSE_SECRET_KEY": "sk-lf-1"},
            clear=False,
        ):
            self.assertTrue(observability.enabled())


class NoopTests(unittest.TestCase):
    def test_init_tracing_noop_without_keys(self) -> None:
        with no_langfuse_env():
            with mock.patch.object(observability, "_initialized", False):
                observability.init_tracing()  # must not raise
            observability.flush()  # must not raise

    def test_run_trace_yields_noop_without_keys(self) -> None:
        with no_langfuse_env():
            with observability.run_trace("agent:test", input="hi") as span:
                span.update(output="ok")  # no-op update must not raise

    def test_trace_attributes_noop_without_keys(self) -> None:
        with no_langfuse_env():
            with observability.trace_attributes(user_id="u_1", session_id="1"):
                pass


if __name__ == "__main__":
    unittest.main()

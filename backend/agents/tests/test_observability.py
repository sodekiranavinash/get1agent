"""Unit tests for the AWS-native (OTel) tracing helpers."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import observability  # noqa: E402


class EnabledTests(unittest.TestCase):
    def test_enabled_by_default(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_TRACING_ENABLED", None)
            self.assertTrue(observability.enabled())

    def test_disabled_by_env(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_TRACING_ENABLED": "false"}, clear=False):
            self.assertFalse(observability.enabled())


class TraceTests(unittest.TestCase):
    def test_init_tracing_and_flush_do_not_raise(self) -> None:
        with mock.patch.object(observability, "_initialized", False):
            observability.init_tracing()
        observability.flush()

    def test_run_trace_yields_updatable_observation(self) -> None:
        with observability.run_trace("agent:test", input="hi", user_id="u_1") as span:
            span.update(output="ok")  # must not raise

    def test_trace_attributes_and_identity(self) -> None:
        with observability.trace_attributes(user_id="u_1", session_id="1"):
            trace_id, trace_url = observability.trace_identity()
        # Without a configured TracerProvider the trace id is absent, not an error.
        self.assertIsNone(trace_url)
        self.assertTrue(trace_id is None or isinstance(trace_id, str))

    def test_run_trace_disabled_is_noop(self) -> None:
        with mock.patch.dict(os.environ, {"AGENT_TRACING_ENABLED": "false"}, clear=False):
            with observability.run_trace("agent:test") as span:
                span.update(output="ok")
            self.assertIsNone(observability.trace_identity(span)[0])


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the tool harness: program building, output parsing and a
local end-to-end execution (no AWS, no AgentCore)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))
sys.path.insert(0, str(SRC.parents[1] / "packages"))

from src import execute, harness  # noqa: E402

TOOL_CODE = """
def run(args):
    name = args.get("name", "world")
    return {"greeting": f"hello {name}", "length": len(name)}
"""


class HarnessTests(unittest.TestCase):
    def test_build_program_invokes_entrypoint(self) -> None:
        program = harness.build_program(TOOL_CODE, {"name": "ada"})
        self.assertIn("def run(args):", program)
        self.assertIn("run(_g1_args)", program)

    def test_parse_result_marker(self) -> None:
        output = 'some log\n__G1_TOOL_RESULT__{"result": {"ok": true}}\n'
        parsed = harness.parse_output(output)
        self.assertEqual(parsed, {"result": {"ok": True}})

    def test_parse_error_marker(self) -> None:
        output = '__G1_TOOL_ERROR__{"error": "boom", "traceback": "..."}\n'
        parsed = harness.parse_output(output)
        self.assertEqual(parsed["error"], "boom")

    def test_parse_missing_marker(self) -> None:
        self.assertIsNone(harness.parse_output("no markers here"))


class ExecuteLocalTests(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["CUSTOM_TOOLS_MODE"] = "local"
        os.environ["CUSTOM_TOOLS_EXEC_TIMEOUT_SECONDS"] = "30"

    def test_runs_tool_and_validates_output(self) -> None:
        result = execute.run_tool(
            "u_test",
            code=TOOL_CODE,
            args={"name": "ada"},
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            output_schema={
                "type": "object",
                "properties": {
                    "greeting": {"type": "string"},
                    "length": {"type": "integer"},
                },
            },
        )
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["result"]["greeting"], "hello ada")
        self.assertEqual(result["outputSchemaErrors"], [])

    def test_reports_invalid_input(self) -> None:
        result = execute.run_tool(
            "u_test",
            code=TOOL_CODE,
            args={},
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            output_schema=None,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "invalid_input")

    def test_reports_tool_error(self) -> None:
        result = execute.run_tool(
            "u_test",
            code="def run(args):\n    raise ValueError('nope')\n",
            args={},
            input_schema=None,
            output_schema=None,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "tool_error")
        self.assertIn("nope", result["error"]["message"])

    def test_reports_missing_entrypoint(self) -> None:
        result = execute.run_tool(
            "u_test",
            code="def other(args):\n    return 1\n",
            args={},
            input_schema=None,
            output_schema=None,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "tool_error")


if __name__ == "__main__":
    unittest.main()

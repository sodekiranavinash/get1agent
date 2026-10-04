"""Build and parse the sandbox program that invokes a user-defined tool.

A tool's source defines an entrypoint (``run`` by default) taking a single
``args`` dict and returning a JSON-serializable value. The harness appends a
small driver that calls it with the (validated) arguments and prints a
line-delimited marker so the result can be recovered from the sandbox output
regardless of any logging the tool itself does.
"""

from __future__ import annotations

import json
from typing import Any

DEFAULT_ENTRYPOINT = "run"
RESULT_MARKER = "__G1_TOOL_RESULT__"
ERROR_MARKER = "__G1_TOOL_ERROR__"

_DRIVER = """

# --- get1agent tool driver (appended) ---
import json as _g1_json
import sys as _g1_sys


def _g1_main():
    try:
        _g1_args = _g1_json.loads({args_literal})
    except Exception:  # noqa: BLE001
        _g1_args = {{}}
    try:
        _g1_result = {entrypoint}(_g1_args)
    except Exception as _g1_exc:  # noqa: BLE001
        _g1_sys.stdout.write(
            "\\n" + {error_marker!r}
            + _g1_json.dumps(
                {{"error": str(_g1_exc), "type": type(_g1_exc).__name__}},
                default=str,
            )
            + "\\n"
        )
        return
    _g1_sys.stdout.write(
        "\\n" + {result_marker!r}
        + _g1_json.dumps({{"result": _g1_result}}, default=str)
        + "\\n"
    )


_g1_main()
"""


def build_program(
    user_code: str, args: dict[str, Any], entrypoint: str = DEFAULT_ENTRYPOINT
) -> str:
    """Return the full Python program to run in the sandbox."""
    args_literal = repr(json.dumps(args, default=str))
    driver = _DRIVER.format(
        args_literal=args_literal,
        entrypoint=entrypoint,
        result_marker=RESULT_MARKER,
        error_marker=ERROR_MARKER,
    )
    return f"{user_code.rstrip()}\n{driver}"


def _extract(output: str, marker: str) -> dict[str, Any] | None:
    index = output.rfind(marker)
    if index < 0:
        return None
    payload = output[index + len(marker):]
    # The marker line is the last line the driver writes; parse just that line.
    payload = payload.splitlines()[0] if payload else ""
    try:
        parsed = json.loads(payload)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_output(output: str) -> dict[str, Any] | None:
    """Return ``{"result": ...}`` or ``{"error": ..., "traceback": ...}``."""
    return _extract(output, RESULT_MARKER) or _extract(output, ERROR_MARKER)

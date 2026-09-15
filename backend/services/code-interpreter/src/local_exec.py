"""Local (Floci) execution backend for the code-interpreter tool.

AgentCore Code Interpreter is a managed AWS service and is not emulated by
Floci, so when ``CODE_INTERPRETER_MODE=local`` the code runs in an isolated
subprocess of the Lambda container instead. The same static guard and the same
audit-hook prelude run first, and ``resource`` limits plus a hard timeout bound
the damage.

This path is for local development only. It is **not** a security boundary —
the AgentCore microVM is what isolates production executions.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from typing import Any

_MEM_BYTES = 1024 * 1024 * 1024
_FILE_BYTES = 16 * 1024 * 1024
_MAX_PROCS = 64


def _limits(timeout: int):
    def _apply() -> None:
        try:
            import resource

            resource.setrlimit(resource.RLIMIT_CPU, (timeout, timeout + 5))
            resource.setrlimit(resource.RLIMIT_AS, (_MEM_BYTES, _MEM_BYTES))
            resource.setrlimit(resource.RLIMIT_FSIZE, (_FILE_BYTES, _FILE_BYTES))
            resource.setrlimit(resource.RLIMIT_NPROC, (_MAX_PROCS, _MAX_PROCS))
        except (ImportError, ValueError, OSError):
            # Best effort: the timeout below is the hard backstop.
            pass

    return _apply


def run(code: str, *, timeout: int, prelude: str, max_output: int) -> dict[str, Any]:
    """Execute ``code`` in a subprocess; return ``{output, is_error, timed_out}``."""
    script = f"{prelude}\n{code}\n"
    with tempfile.TemporaryDirectory(prefix="g1ci-") as workdir:
        try:
            proc = subprocess.run(
                [sys.executable, "-I", "-c", script],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
                env={"PATH": os.environ.get("PATH", ""), "PYTHONIOENCODING": "utf-8"},
                preexec_fn=_limits(timeout),
            )
        except subprocess.TimeoutExpired:
            return {"output": "", "is_error": True, "timed_out": True}

    output = (proc.stdout or "") + (proc.stderr or "")
    if len(output) > max_output:
        output = output[:max_output] + "\n…[truncated]"
    return {
        "output": output,
        "is_error": proc.returncode != 0,
        "timed_out": False,
    }

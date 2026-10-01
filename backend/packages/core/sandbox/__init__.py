"""Shared Python sandbox: static guard + AgentCore/local execution runner.

Used by the ``code-interpreter`` MCP tool and the ``custom-tools`` MCP server.
The AgentCore microVM is the real isolation boundary; the guard is
defence-in-depth and abuse/cost control.
"""

from .runner import SandboxConfig, error, run_code
from .sessions import sanitize_thread

__all__ = ["SandboxConfig", "error", "run_code", "sanitize_thread"]

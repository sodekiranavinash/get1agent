"""Runtime configuration for the agent worker (env-driven)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


@dataclass(frozen=True)
class RuntimeConfig:
    # OpenCode Go (OpenAI-compatible) model gateway.
    opencode_api_key: str
    opencode_base_url: str
    # Data plane.
    dynamodb_table: str
    s3_bucket: str
    s3_region: str
    # Vector store for user memory (shares the retrieval vector store).
    vector_store: str
    s3_vector_bucket: str
    # MCP server Lambda function names.
    knowledge_function: str
    web_search_function: str
    code_interpreter_function: str
    remote_function: str
    # Where Strands session snapshots live in S3.
    session_prefix: str
    # Model turn ceiling.
    max_turns: int
    # Fixed model used for the pre-run planning step (sub-queries + todos).
    planner_model: str
    # Disable the planning step (set AGENT_PLANNER_ENABLED=false).
    planner_enabled: bool


def load_config() -> RuntimeConfig:
    return RuntimeConfig(
        opencode_api_key=_env("OPENCODE_API_KEY"),
        opencode_base_url=_env("OPENCODE_BASE_URL", "https://opencode.ai/zen/go/v1"),
        dynamodb_table=_env("DYNAMODB_TABLE", "get1agent"),
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION") or _env("AWS_REGION") or "ap-south-1",
        vector_store=_env("VECTOR_STORE", "s3vectors"),
        s3_vector_bucket=_env("S3_VECTOR_BUCKET"),
        knowledge_function=_env("KNOWLEDGE_MCP_FUNCTION"),
        web_search_function=_env("WEB_SEARCH_MCP_FUNCTION"),
        code_interpreter_function=_env("CODE_INTERPRETER_MCP_FUNCTION"),
        remote_function=_env("REMOTE_MCP_FUNCTION"),
        session_prefix=_env("AGENT_SESSION_PREFIX", "agent-sessions/"),
        max_turns=int(_env("AGENT_MAX_TURNS", "40") or "40"),
        planner_model=_env("AGENT_PLANNER_MODEL", "deepseek-v4-flash-vision-exp"),
        planner_enabled=_env("AGENT_PLANNER_ENABLED", "true").lower() not in ("0", "false", "no"),
    )

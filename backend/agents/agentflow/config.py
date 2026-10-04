"""Runtime configuration for the agent worker (env-driven)."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


@dataclass(frozen=True)
class RuntimeConfig:
    # Amazon Bedrock is the platform model gateway (region for bedrock-runtime).
    bedrock_region: str
    # Data plane.
    dynamodb_table: str
    s3_bucket: str
    s3_region: str
    # Vector store for user memory (shares the retrieval vector store).
    vector_store: str
    s3_vector_bucket: str
    # MCP server Lambda function names.
    knowledge_function: str
    code_interpreter_function: str
    http_fetch_function: str
    browser_function: str
    remote_function: str
    # User-defined Python tools (Playground), served by the custom-tools Lambda.
    custom_tools_function: str
    # Where Strands session snapshots live in S3.
    session_prefix: str
    # Model turn ceiling.
    max_turns: int
    # Fixed model used for the pre-run planning step (sub-queries + todos).
    planner_model: str
    # Disable the planning step (set AGENT_PLANNER_ENABLED=false).
    planner_enabled: bool
    # Memory backend: "agentcore" (managed, the only deployed path) or "dynamo"
    # (local development and tests).
    memory_backend: str
    # AgentCore Memory resource id (required when memory_backend=agentcore).
    memory_id: str
    # AgentCore Policy engine applied to tool calls (empty disables enforcement).
    policy_engine: str
    # Gateway (managed MCP) — the deployed path; the in-app servers are the
    # fallback for local development. "gateway" requires GATEWAY_URL.
    mcp_transport: str
    gateway_url: str
    # Web Search is the AgentCore Gateway built-in connector (no MCP Lambda and
    # no model access). The gateway exposes it as "<target>___WebSearch"; there
    # is no direct-invoke fallback.
    web_search_gateway_tool: str
    # Dedicated gateway that hosts the Web Search connector (it may live in a
    # different Region than the main gateway). Empty disables web search.
    web_search_gateway_url: str
    web_search_gateway_region: str


def load_config() -> RuntimeConfig:
    return RuntimeConfig(
        bedrock_region=(
            _env("BEDROCK_REGION") or _env("AWS_REGION") or "ap-south-1"
        ),
        dynamodb_table=_env("DYNAMODB_TABLE", "get1agent"),
        s3_bucket=_env("S3_BUCKET"),
        s3_region=_env("S3_REGION") or _env("AWS_REGION") or "ap-south-1",
        vector_store=_env("VECTOR_STORE", "s3vectors"),
        s3_vector_bucket=_env("S3_VECTOR_BUCKET"),
        knowledge_function=_env("KNOWLEDGE_MCP_FUNCTION"),
        code_interpreter_function=_env("CODE_INTERPRETER_MCP_FUNCTION"),
        http_fetch_function=_env("HTTP_FETCH_MCP_FUNCTION"),
        browser_function=_env("BROWSER_MCP_FUNCTION"),
        remote_function=_env("REMOTE_MCP_FUNCTION"),
        custom_tools_function=_env("CUSTOM_TOOLS_MCP_FUNCTION"),
        session_prefix=_env("AGENT_SESSION_PREFIX", "agent-sessions/"),
        max_turns=int(_env("AGENT_MAX_TURNS", "40") or "40"),
        planner_model=_env("AGENT_PLANNER_MODEL", "zai.glm-4.7-flash"),
        planner_enabled=_env("AGENT_PLANNER_ENABLED", "true").lower()
        not in ("0", "false", "no"),
        memory_backend=(_env("AGENT_MEMORY_BACKEND", "agentcore") or "agentcore").lower(),
        memory_id=_env("AGENTCORE_MEMORY_ID"),
        policy_engine=_env("AGENT_POLICY_ENGINE", ""),
        mcp_transport=(_env("MCP_TRANSPORT", "aggregator") or "aggregator").lower(),
        gateway_url=_env("MCP_GATEWAY_URL"),
        web_search_gateway_tool=_env("WEB_SEARCH_GATEWAY_TOOL", "web-search___WebSearch"),
        web_search_gateway_url=_env("WEB_SEARCH_GATEWAY_URL"),
        web_search_gateway_region=_env("WEB_SEARCH_GATEWAY_REGION"),
    )

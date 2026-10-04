"""AgentCore Registry helper (governed catalog).

Publishes a workspace's agents, MCP servers, tools and skills into the managed
**AgentCore Registry** so they are discoverable with semantic + keyword search
and governed by an approval workflow, instead of only living in per-user
DynamoDB items.

Best-effort: without ``AGENTCORE_REGISTRY_ARN`` every helper reports
"not configured".

Config: ``AGENTCORE_REGISTRY_ARN``, ``AGENTCORE_REGISTRY_ID``, ``BEDROCK_REGION``.
"""

from __future__ import annotations

import os
from typing import Any

DEFAULT_RECORD_TYPE = "AGENT"


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def registry_arn() -> str:
    return _env("AGENTCORE_REGISTRY_ARN")


def registry_id() -> str:
    return _env("AGENTCORE_REGISTRY_ID")


def region() -> str:
    return _env("BEDROCK_REGION") or _env("AWS_REGION") or "ap-south-1"


def enabled() -> bool:
    return bool(registry_id() or registry_arn())


def _client() -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "bedrock-agentcore",
        region_name=region(),
        config=Config(retries={"max_attempts": 4, "mode": "adaptive"}),
    )


def publish(
    *,
    name: str,
    description: str,
    record_type: str = DEFAULT_RECORD_TYPE,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Publish one record into the registry (``CreateRegistryRecord``)."""
    if not enabled():
        raise RuntimeError("AgentCore Registry is not configured")
    if not name.strip():
        raise ValueError("name is required")
    response = _client().create_registry_record(
        registryId=registry_id(),
        name=name.strip(),
        description=(description or "").strip()[:1000],
        recordType=record_type,
        metadata=metadata or {},
    )
    return response


def search(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Semantic + keyword search over registry records."""
    if not enabled():
        return []
    response = _client().search_registry_records(
        registryId=registry_id(),
        query=(query or "").strip(),
        maxResults=max(1, min(limit, 50)),
    )
    return response.get("records") or response.get("results") or []


def describe() -> dict[str, Any]:
    return {
        "configured": enabled(),
        "registryId": registry_id() or None,
        "registryArn": registry_arn() or None,
        "region": region(),
    }

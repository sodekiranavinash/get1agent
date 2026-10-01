"""Validation and limits for user-defined MCP tools.

Server names follow the lowercase-hyphen convention (like skills/agents); tool
names are lowercase too so the namespaced MCP name ``<slug>/<tool>`` is stable
and easy to match in the agent's tool selection.
"""

from __future__ import annotations

import json
import re
from typing import Any

MAX_CUSTOM_SERVERS_PER_USER = 20
MAX_CUSTOM_TOOLS_PER_SERVER = 20
MAX_CUSTOM_TOOL_CODE_BYTES = 64 * 1024  # 64 KB of Python source
MAX_CUSTOM_TOOL_NAME = 64
MAX_CUSTOM_SERVER_NAME = 64
MAX_SCHEMA_BYTES = 8 * 1024
MAX_CUSTOM_DESCRIPTION = 1000
CUSTOM_TOOL_ENTRYPOINT = "run"

_NAME_CHARS = re.compile(r"^[a-z0-9-]+$")
_NAME_EDGES = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
_TOOL_NAME_CHARS = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (value or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", slug)[:48].strip("-")


def validate_server_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Server name is required")
    name = value.strip()
    if len(name) > MAX_CUSTOM_SERVER_NAME:
        raise ValueError(f"Name must be at most {MAX_CUSTOM_SERVER_NAME} characters")
    if not _NAME_CHARS.match(name):
        raise ValueError(
            "Name can only contain lowercase letters, numbers and hyphens"
        )
    if not _NAME_EDGES.match(name):
        raise ValueError("Name must start and end with a letter or number")
    return name


def validate_tool_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Tool name is required")
    name = value.strip()
    if len(name) > MAX_CUSTOM_TOOL_NAME:
        raise ValueError(f"Tool name must be at most {MAX_CUSTOM_TOOL_NAME} characters")
    if not _TOOL_NAME_CHARS.match(name):
        raise ValueError(
            "Tool name must be lowercase and contain only letters, numbers, "
            "hyphens or underscores"
        )
    return name


def validate_description(value: Any) -> str:
    if value in (None, ""):
        return ""
    if not isinstance(value, str):
        raise ValueError("description must be a string")
    text = value.strip()
    if len(text) > MAX_CUSTOM_DESCRIPTION:
        raise ValueError(
            f"description must be at most {MAX_CUSTOM_DESCRIPTION} characters"
        )
    return text


def validate_code(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Tool source code is required")
    if len(value.encode("utf-8")) > MAX_CUSTOM_TOOL_CODE_BYTES:
        raise ValueError(
            f"Tool source exceeds the {MAX_CUSTOM_TOOL_CODE_BYTES // 1024} KB limit"
        )
    return value


def normalize_schema(value: Any) -> dict[str, Any]:
    """Coerce a schema into an object schema within the size cap."""
    if value in (None, {}):
        return {"type": "object", "properties": {}}
    if not isinstance(value, dict):
        raise ValueError("schema must be an object")
    if len(json.dumps(value).encode("utf-8")) > MAX_SCHEMA_BYTES:
        raise ValueError("schema is too large")
    schema = dict(value)
    schema.setdefault("type", "object")
    if schema.get("type") == "object":
        schema.setdefault("properties", {})
        if not isinstance(schema["properties"], dict):
            raise ValueError("schema properties must be an object")
    return schema

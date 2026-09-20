"""Skill spec constants and validation (strands format).

Kept dependency-free (no PyYAML) so it can live in the shared data layer and be
reused by the agent at runtime. The frontmatter grammar is deliberately narrow:
scalar keys plus a string list for ``allowed-tools``.
"""

from __future__ import annotations

import re
from typing import Any

# Skill names follow the strands convention: lowercase letters, digits and
# hyphens, starting and ending alphanumeric (e.g. ``pdf-processing``).
SKILL_NAME_MIN = 1
SKILL_NAME_MAX = 64
_NAME_CHARS = re.compile(r"^[a-z0-9-]+$")
_NAME_EDGES = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")

MAX_DESCRIPTION_LENGTH = 1000
MAX_SKILL_CONTENT_BYTES = 100 * 1024  # 100 KB of markdown body
MAX_SKILLS_PER_USER = 50
MAX_ALLOWED_TOOLS = 20

# Built-in MCP servers every user can grant to a skill. ``code-interpreter``
# and ``web-search`` are the two default servers. Knowledge-base tools are
# internal and are intentionally never surfaced here.
DEFAULT_TOOLS: list[dict[str, str]] = [
    {
        "name": "code-interpreter",
        "label": "Code Interpreter",
        "description": "Run Python in a sandbox for data analysis and file processing.",
        "source": "builtin",
    },
    {
        "name": "web-search",
        "label": "Web Search",
        "description": "Search the web for current information and citations.",
        "source": "builtin",
    },
]

# Tool identifiers are lowercase and may be namespaced for MCP servers, e.g.
# ``github/create-issue``.
_TOOL_CHARS = re.compile(r"^[a-z0-9][a-z0-9._/-]*$")


def validate_skill_name(value: Any) -> str:
    """Return the normalized skill name or raise ``ValueError``."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Skill name is required")
    name = value.strip()
    if len(name) < SKILL_NAME_MIN:
        raise ValueError(f"Name must be at least {SKILL_NAME_MIN} character")
    if len(name) > SKILL_NAME_MAX:
        raise ValueError(f"Name must be at most {SKILL_NAME_MAX} characters")
    if not _NAME_CHARS.match(name):
        raise ValueError(
            "Name can only contain lowercase letters, numbers and hyphens "
            "(no spaces or special characters)"
        )
    if not _NAME_EDGES.match(name):
        raise ValueError("Name must start and end with a letter or number")
    return name


def normalize_allowed_tools(raw: Any) -> list[str]:
    """Normalize a tool selection into a de-duplicated list of valid names.

    Accepts a list (from the UI/JSON) or a whitespace/comma separated string
    (from frontmatter). Order is preserved and duplicates are dropped.
    """
    if raw in (None, ""):
        return []
    if isinstance(raw, str):
        parts = re.split(r"[,\s]+", raw.strip())
    elif isinstance(raw, (list, tuple, set)):
        parts = [str(item) for item in raw]
    else:
        raise ValueError("allowedTools must be a list of tool names")

    tools: list[str] = []
    seen: set[str] = set()
    for part in parts:
        tool = str(part).strip()
        if not tool:
            continue
        if not _TOOL_CHARS.match(tool):
            raise ValueError(f"Invalid tool name: {tool}")
        if tool in seen:
            continue
        seen.add(tool)
        tools.append(tool)
    if len(tools) > MAX_ALLOWED_TOOLS:
        raise ValueError(f"At most {MAX_ALLOWED_TOOLS} tools per skill")
    return tools

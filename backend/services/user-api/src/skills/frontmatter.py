"""Parse and render the strands skill markdown format.

The parser is intentionally forgiving (it is also used to pre-fill the editor
from an uploaded ``.md``) while the renderer produces the canonical form the
agent consumes.
"""

from __future__ import annotations

import re
from typing import Any

from src.skills.spec import normalize_allowed_tools

_DELIMITER = re.compile(r"^---\s*$")
_KEY = re.compile(r"^([A-Za-z0-9_-]+)\s*:\s*(.*)$")
_SPECIAL = re.compile(r"[:#\[\]{}\n\"']")


def _unquote(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "\"'":
        inner = text[1:-1]
        if text[0] == '"':
            inner = inner.replace('\\"', '"').replace("\\\\", "\\")
        return inner
    return text


def parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    """Split raw markdown into (frontmatter mapping, body)."""
    text = markdown.lstrip("\ufeff")
    lines = text.splitlines()
    if not lines or not _DELIMITER.match(lines[0].strip()):
        return {}, text

    end: int | None = None
    for index in range(1, len(lines)):
        if _DELIMITER.match(lines[index].strip()):
            end = index
            break
    if end is None:
        return {}, text

    data: dict[str, Any] = {}
    list_key: str | None = None
    for raw_line in lines[1:end]:
        stripped = raw_line.strip()
        if not stripped:
            list_key = None
            continue

        if stripped == "-" or stripped.startswith("- "):
            if list_key is not None and isinstance(data.get(list_key), list):
                data[list_key].append(_unquote(stripped[1:].strip()))
            continue

        match = _KEY.match(stripped)
        if match:
            key = match.group(1).strip().lower().replace("-", "_")
            value = match.group(2).strip()
            if value == "":
                data[key] = []
                list_key = key
            else:
                data[key] = _unquote(value)
                list_key = None
            continue

        # Continuation of the previous scalar (e.g. a wrapped description).
        if list_key is None and data:
            last_key = next(reversed(data))
            if isinstance(data[last_key], str):
                data[last_key] = f"{data[last_key]} {stripped}".strip()

    return data, "\n".join(lines[end + 1 :])


def parse_skill_markdown(markdown: str) -> dict[str, Any]:
    """Extract the strands fields from a raw skill file.

    Missing fields come back as ``None``/``[]`` so the caller (the editor
    pre-fill) can fall back to the filename or leave a field blank.
    """
    data, body = parse_frontmatter(markdown)

    name = data.get("name")
    description = data.get("description")
    tools_raw = data.get("allowed_tools")
    if isinstance(tools_raw, str):
        tools_raw = tools_raw.strip().strip("[]")
    try:
        tools = normalize_allowed_tools(tools_raw)
    except ValueError:
        # Pre-fill is best-effort: keep the raw tokens so the user can fix them.
        tools = [
            token
            for token in re.split(r"[,\s]+", str(tools_raw or "").strip().strip("[]"))
            if token
        ]

    return {
        "name": name.strip() if isinstance(name, str) and name.strip() else None,
        "description": (
            description.strip()
            if isinstance(description, str) and description.strip()
            else None
        ),
        "allowedTools": tools,
        "content": body.strip("\n"),
    }


def _format_value(value: str) -> str:
    text = value.strip()
    if not text or _SPECIAL.search(text) or text != value:
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def render_skill_markdown(
    name: str,
    description: str,
    allowed_tools: list[str] | str | None,
    content: str,
) -> str:
    """Assemble the canonical strands skill markdown."""
    lines = [
        "---",
        f"name: {_format_value(name)}",
        f"description: {_format_value(description)}",
    ]
    tools = normalize_allowed_tools(allowed_tools)
    if tools:
        lines.append(f"allowed-tools: {' '.join(tools)}")
    lines.append("---")
    header = "\n".join(lines)

    body = (content or "").strip("\n")
    return f"{header}\n\n{body}\n" if body else f"{header}\n"

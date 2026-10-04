"""Preview and load a third-party skill from a raw ``SKILL.md`` URL."""

from __future__ import annotations

from typing import Any

from src.skills.classify import classify_skill, referenced_files
from src.skills.fetch import fetch_text
from src.skills.frontmatter import parse_skill_markdown


def load(raw_url: str) -> dict[str, Any]:
    """Fetch and parse a raw SKILL.md (no persistence)."""
    markdown = fetch_text(raw_url)
    parsed = parse_skill_markdown(markdown)
    classification = classify_skill(markdown)
    return {
        "rawUrl": raw_url,
        "name": parsed["name"],
        "description": parsed["description"],
        "content": parsed["content"],
        "allowedTools": parsed["allowedTools"],
        "kind": classification["kind"],
        "suggestedServers": classification["suggestedServers"],
        "referencedFiles": referenced_files(markdown),
        "sizeBytes": len(markdown.encode("utf-8")),
    }


def preview(raw_url: str) -> dict[str, Any]:
    return load(raw_url)

"""Assemble the agent's system prompt from its canonical config."""

from __future__ import annotations

from typing import Any

_OUTPUT_LABELS = {"markdown": "Markdown", "text": "plain text", "json": "JSON"}


def _skill_block(skill: dict[str, Any]) -> str:
    name = skill.get("name") or "skill"
    description = (skill.get("description") or "").strip()
    body = (skill.get("content") or "").strip()
    header = f"### Skill: {name}"
    if description:
        header += f"\n{description}"
    return f"{header}\n\n{body}" if body else header


def build_system_prompt(config: dict[str, Any], skills: list[dict[str, Any]]) -> str:
    parts: list[str] = []

    prompt = (config.get("prompt") or "").strip()
    parts.append(prompt or "You are a helpful AI agent.")

    output = config.get("output") or {}
    format_label = _OUTPUT_LABELS.get(
        output.get("format") or config.get("outputFormat"), "Markdown"
    )
    instructions = (output.get("instructions") or "").strip()
    output_line = f"Respond in {format_label}."
    if instructions:
        output_line += f" {instructions}"
    parts.append(output_line)

    parts.append(
        "Return only the final answer. Never include your internal reasoning, "
        "chain-of-thought, planning notes, or step-by-step commentary in your "
        "response — use tools silently and write the answer for the user."
    )

    parts.append(
        "When you are given a plan or multiple steps, execute them strictly in "
        "order, one at a time, finishing each step before starting the next."
    )

    parts.append(
        "CITATIONS (required): every source returned by a tool carries an "
        "`index`. After each sentence or bullet that uses information from a "
        "tool, append the matching index as a bracketed number, e.g. [1] or "
        "[1][3]. Never omit citations for facts taken from tools."
    )

    if skills:
        skills_text = "\n\n".join(_skill_block(skill) for skill in skills)
        parts.append(
            "You have the following skills. Follow them when they apply:\n\n"
            f"{skills_text}"
        )

    if config.get("knowledgeBaseIds"):
        parts.append(
            "For questions about the attached knowledge bases, call "
            "`get-user-knowledge-bases` once to see what is available, then call "
            "`search-user-knowledge-bases` before answering from memory."
        )

    return "\n\n".join(part for part in parts if part).strip()

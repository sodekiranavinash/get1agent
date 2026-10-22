"""Assemble the agent's system prompt from its canonical config.

The wording itself lives in the shared prompt library
(``backend/packages/prompts/agent/``) so it can be read and tuned
as prose; this module only decides which blocks apply to a run and in what
order. Everything here is still prompt *structure*, which is a per-agent setting:
answer mode, reasoning effort, human-in-the-loop, memory and attached sources.
"""

from __future__ import annotations

from typing import Any

from prompts import render as render_prompt
from prompts import text as prompt_text

_OUTPUT_LABELS = {"markdown": "Markdown", "text": "plain text", "json": "JSON"}

# How detailed the answer should be, chosen per agent. Defaults to `normal`.
_ANSWER_MODE_INSTRUCTIONS = {
    mode: prompt_text(f"agent/answer-mode.{mode}")
    for mode in ("summarize", "normal", "detailed")
}

# Values stored before the modes were renamed.
_ANSWER_MODE_ALIASES = {"medium": "normal", "deep": "detailed"}

_DEFAULT_ANSWER_MODE = "summarize"

# Reasoning effort is a prompt-level hint (the gateway exposes no reasoning token
# budget). `medium` adds nothing.
_REASONING_HINTS = {
    effort: prompt_text(f"agent/reasoning.{effort}") for effort in ("low", "high")
}


def answer_mode_instruction(mode: Any) -> str:
    """The prompt block for an agent's answer mode (summarize/normal/detailed)."""
    key = str(mode or _DEFAULT_ANSWER_MODE).strip().lower()
    key = _ANSWER_MODE_ALIASES.get(key, key)
    return _ANSWER_MODE_INSTRUCTIONS.get(
        key, _ANSWER_MODE_INSTRUCTIONS[_DEFAULT_ANSWER_MODE]
    )


def reasoning_instruction(effort: Any) -> str:
    return _REASONING_HINTS.get(str(effort or "").strip().lower(), "")


_HITL_ASK_INSTRUCTION = prompt_text("agent/hitl.ask")

_HITL_ASSUME_INSTRUCTION = prompt_text("agent/hitl.assume")

# Injected by the Strands MemoryManager as a <memory> block before each model
# call. This is the user's own long-term context, not training knowledge, so it
# is allowed to answer personal questions directly.
_USER_MEMORY_INSTRUCTION = prompt_text("agent/memory.use")

# Only added when the memory manager exposes an add tool, so the prompt never
# names a tool the run does not have.
_USER_MEMORY_SAVE_INSTRUCTION = prompt_text("agent/memory.save")


def build_system_prompt(
    config: dict[str, Any],
    skills: list[dict[str, Any]],
    human_in_loop: bool | None = None,
    memory_enabled: bool = False,
    memory_can_save: bool = False,
) -> str:
    parts: list[str] = []

    prompt = (config.get("prompt") or "").strip()
    parts.append(prompt or prompt_text("agent/default"))

    output = config.get("output") or {}
    format_label = _OUTPUT_LABELS.get(
        output.get("format") or config.get("outputFormat"), "Markdown"
    )
    instructions = (output.get("instructions") or "").strip()
    output_line = render_prompt("agent/output-format", format=format_label)
    if instructions:
        output_line += f" {instructions}"
    parts.append(output_line)

    # Answer depth is a per-agent setting; when absent (e.g. workflow host prompts,
    # which are not saved agents) fall back to the `normal` default.
    parts.append(answer_mode_instruction(config.get("answerMode")))

    reasoning = reasoning_instruction(config.get("reasoning"))
    if reasoning:
        parts.append(reasoning)

    parts.append(prompt_text("agent/final-answer-only"))

    parts.append(prompt_text("agent/plan-order"))

    parts.append(prompt_text("agent/grounding"))

    if memory_enabled:
        parts.append(_USER_MEMORY_INSTRUCTION)
        if memory_can_save:
            parts.append(_USER_MEMORY_SAVE_INSTRUCTION)

    if skills:
        # Skills themselves are loaded by the Strands AgentSkills plugin via
        # progressive disclosure: the plugin injects a lightweight
        # ``<available_skills>`` block (name + description) and exposes a
        # ``skills`` tool. We only tell the model how to use it — never paste the
        # skill bodies here, or the model loses the choice of applying a skill.
        parts.append(prompt_text("agent/skills"))

    if config.get("knowledgeBaseIds"):
        parts.append(prompt_text("agent/knowledge-bases"))

    # Chat-only. `None` means the caller did not opt in (builder, automation),
    # so the agent's normal behavior is unchanged.
    if human_in_loop is True:
        parts.append(_HITL_ASK_INSTRUCTION)
    elif human_in_loop is False:
        parts.append(_HITL_ASSUME_INSTRUCTION)

    return "\n\n".join(part for part in parts if part).strip()

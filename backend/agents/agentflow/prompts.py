"""Assemble the agent's system prompt from its canonical config."""

from __future__ import annotations

from typing import Any

_OUTPUT_LABELS = {"markdown": "Markdown", "text": "plain text", "json": "JSON"}

# How detailed the answer should be, chosen per agent. Defaults to `normal`.
_ANSWER_MODE_INSTRUCTIONS = {
    "summarize": (
        "Answer mode: SUMMARIZE. Be as concise as possible — give the shortest "
        "answer that fully addresses the request. Lead with the answer, use short "
        "bullets when helpful, and omit preamble, background, filler and tangential "
        "detail. Do not add a closing summary or sign-off."
    ),
    "normal": (
        "Answer mode: NORMAL. Give a focused answer: the key points plus enough "
        "context or explanation to be clear. Use short sections or bullets when "
        "helpful, but avoid long digressions, repetition and filler."
    ),
    "detailed": (
        "Answer mode: DETAILED. Give a thorough, well-structured answer with clear "
        "sections, full context and supporting detail, as you normally would for an "
        "in-depth response."
    ),
}

# Values stored before the modes were renamed.
_ANSWER_MODE_ALIASES = {"medium": "normal", "deep": "detailed"}

_DEFAULT_ANSWER_MODE = "summarize"

# Reasoning effort is a prompt-level hint (the gateway exposes no reasoning token
# budget). `medium` adds nothing.
_REASONING_HINTS = {
    "low": "Reasoning effort: LOW. Keep your internal reasoning brief.",
    "high": "Reasoning effort: HIGH. Think carefully and check edge cases before answering.",
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


_HITL_ASK_INSTRUCTION = (
    "HUMAN-IN-THE-LOOP: use the `ask_user` tool ONLY when a specific, "
    "mutually-exclusive choice genuinely blocks the task and you cannot pick a "
    "sensible default — for example choosing between named accounts, formats or "
    "scopes that lead to materially different work. When you do ask, give 2-4 "
    "concrete options.\n"
    "- NEVER ask open-ended questions such as \"what aspect are you interested "
    "in?\", never ask the user to clarify, narrow or restate their request, and "
    "never ask for routine confirmation.\n"
    "- For any general, factual or \"tell me about X\" request, do NOT ask — "
    "answer it, using your tools where they help. Pick the most useful default "
    "and proceed.\n"
    "- Ask at most ONE question per run."
)

_HITL_ASSUME_INSTRUCTION = (
    "HUMAN-IN-THE-LOOP: the user has enabled auto-approve, so do not ask "
    "questions. When a choice is missing, make the most sensible assumption "
    "yourself and state it briefly. Facts must still come from tool results or "
    "the injected <memory> block, never from your own training knowledge."
)

# Injected by the Strands MemoryManager as a <memory> block before each model
# call. This is the user's own long-term context, not training knowledge, so it
# is allowed to answer personal questions directly.
_USER_MEMORY_INSTRUCTION = (
    "USER MEMORY (long-term): a `<memory>` block may be injected with durable "
    "facts, preferences and past decisions about this user. Treat it as the "
    "user's own context. Answer personal questions (\"what is my favorite "
    "color?\", \"what did we decide?\") directly from it, without a tool call, "
    "and let it shape your answer. Only use what the block actually contains — "
    "never invent memories. Do not cite the memory block as a source."
)


def build_system_prompt(
    config: dict[str, Any],
    skills: list[dict[str, Any]],
    human_in_loop: bool | None = None,
    memory_enabled: bool = False,
) -> str:
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

    # Answer depth is a per-agent setting; when absent (e.g. workflow host prompts,
    # which are not saved agents) fall back to the `normal` default.
    parts.append(answer_mode_instruction(config.get("answerMode")))

    reasoning = reasoning_instruction(config.get("reasoning"))
    if reasoning:
        parts.append(reasoning)

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
        "GROUNDING (mandatory): answer ONLY from information returned by tool "
        "calls in this run. Do NOT use your own or training knowledge to state "
        "facts, and never present anything as fact that no tool returned. Every "
        "factual sentence or bullet MUST carry the bracketed `index` of the tool "
        "source it came from, e.g. [1] or [1][3]. If the tools did not return the "
        "answer, reply that you could not find it in the available sources rather "
        "than answering from your own training knowledge. (The injected `<memory>` "
        "block about the user, when present, is the user's own context and may be "
        "used.) Call only tools that actually exist; never invent "
        "a tool name. Never fabricate sources, source names or citation markers. "
        "The only exception is a bare greeting or sign-off, which needs no tool."
    )

    if memory_enabled:
        parts.append(_USER_MEMORY_INSTRUCTION)

    if skills:
        # Skills themselves are loaded by the Strands AgentSkills plugin via
        # progressive disclosure: the plugin injects a lightweight
        # ``<available_skills>`` block (name + description) and exposes a
        # ``skills`` tool. We only tell the model how to use it — never paste the
        # skill bodies here, or the model loses the choice of applying a skill.
        parts.append(
            "You have skills available under `available_skills`. When the user's "
            "request matches a skill's description, call the `skills` tool to load "
            "that skill's full instructions, then follow them."
        )

    if config.get("knowledgeBaseIds"):
        parts.append(
            "KNOWLEDGE BASES (primary source): the attached knowledge bases hold "
            "authoritative, user-specific context (a resume/profile, policies, "
            "uploaded documents). Before answering, call `get-user-knowledge-bases` "
            "once to see what is available, then ALWAYS call "
            "`search-user-knowledge-bases` to check them — including when the "
            "request is not phrased as being about them — and prefer their content "
            "over your own memory. Cite what you use."
        )

    # Chat-only. `None` means the caller did not opt in (builder, automation),
    # so the agent's normal behavior is unchanged.
    if human_in_loop is True:
        parts.append(_HITL_ASK_INSTRUCTION)
    elif human_in_loop is False:
        parts.append(_HITL_ASSUME_INSTRUCTION)

    return "\n\n".join(part for part in parts if part).strip()

"""AI Assistant's system prompts.

Three properties matter more than eloquence here:

1. **Grounded.** AI Assistant answers from retrieved platform documentation only. If the
   passages do not cover the question it says so and points at Support — it never
   guesses, because a confident wrong answer about limits or pricing is worse
   than "I don't have that documented".
2. **Real links.** The route catalogue is injected, and AI Assistant is told to copy a
   route from it verbatim. It is never asked to invent a path.
3. **Short.** AI Assistant lives in a dialog, not a document. The default is a few
   sentences; detail only when the question needs steps.

The tone rules exist because this is the first thing many people see: warm,
direct, never scolding, never "As an AI language model".
"""

from __future__ import annotations

from typing import Any

from prompts import render as render_prompt
from prompts import text as prompt_text

from src import deep_links

#: Appended to every prompt so a refusal is always actionable.
ESCALATION_LINE = prompt_text("ai-assistant/escalation")

BASE_RULES = prompt_text("ai-assistant/base-rules")

#: How much detail to give. Chosen per turn from the question, not the user.
ANSWER_MODES: dict[str, str] = {
    mode: prompt_text(f"ai-assistant/answer-mode.{mode}")
    for mode in ("summarize", "normal", "detailed")
}


def _doc_block(passages: list[dict[str, Any]] | None) -> str:
    """Render retrieved passages with their citation numbers and routes."""
    if not passages:
        return prompt_text("ai-assistant/no-passages")
    lines: list[str] = []
    for index, passage in enumerate(passages, 1):
        route = str(passage.get("route") or "")
        title = str(passage.get("title") or passage.get("documentTitle") or "")
        header = f"[{index}] {title}".strip()
        if route:
            header += f" (page: {route})"
        lines.append(header)
        content = str(passage.get("content") or passage.get("text") or "").strip()
        if content:
            lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()


def build_system_prompt(
    *,
    passages: list[dict[str, Any]] | None = None,
    answer_mode: str = "summarize",
    route: str = "",
    is_guest: bool = False,
    allow_admin: bool = False,
    plan: str = "",
) -> str:
    """The system prompt for one turn.

    ``passages`` are the retrieved documents (§ retrieval), ``route`` is where the
    user opened the dialog (so AI Assistant can be page-aware), and ``is_guest`` switches
    to the shorter guest preamble.
    """
    parts = [BASE_RULES.strip()]

    mode = ANSWER_MODES.get(answer_mode) or ANSWER_MODES["summarize"]
    parts.append(render_prompt("ai-assistant/length", mode=mode))

    if route:
        parts.append(render_prompt("ai-assistant/route-context", route=route))
    if is_guest:
        parts.append(prompt_text("ai-assistant/guest"))

    catalogue = deep_links.catalog_text(allow_admin=allow_admin)
    if catalogue:
        parts.append(render_prompt("ai-assistant/route-catalogue", catalogue=catalogue))

    if plan:
        parts.append(render_prompt("ai-assistant/plan", plan=plan))

    parts.append(render_prompt("ai-assistant/docs", passages=_doc_block(passages)))
    parts.append(ESCALATION_LINE)

    return "\n\n".join(parts)


def off_topic_prompt(question: str, route: str = "", examples: list[str] | None = None) -> str:
    """The system prompt used when the classifier decided the question is not ours.

    The model is still used to write the sentence, so it sounds human — but it is
    given the verdict, the example questions and a hard instruction not to answer
    the actual question.
    """
    options = "\n".join(f"- {item}" for item in (examples or []))
    route_line = f"They are on this page: {route}\n" if route else ""
    examples_block = f"\nExample questions to offer:\n{options}" if options else ""
    return render_prompt(
        "ai-assistant/off-topic",
        question=repr(question),
        route_line=route_line,
        examples_block=examples_block,
    )


def greeting_prompt(route: str = "") -> str:
    """A one-line opener for a greeting, so 'hi' does not trigger retrieval."""
    route_suffix = f" They are on this page: {route}." if route else ""
    return render_prompt("ai-assistant/greeting", route_suffix=route_suffix)

"""Human-in-the-loop: an ``ask_user`` tool that pauses a run for the chat user.

Chat runs may opt in to human-in-the-loop progress (the composer's
auto-approve toggle is OFF). When enabled the runtime adds the ``ask_user``
tool; when the agent calls it, the tool raises a Strands **interrupt**, which
pauses the run and surfaces a ``question`` frame to the client. The user's
answer is sent back as an ``interruptResponses`` payload, Strands replays the
paused tool call with the stored response, and the agent continues.

Only the chat screen enables this. The builder, the workflow builder and
scheduled/automation runs never set ``humanInLoop``, so their flows stay
continuous. ``humanInLoop`` is also meaningful when **false**: it tells the
model to assume the best option instead of asking.
"""

from typing import Any

ASK_USER_TOOL = "ask_user"
"""Public tool name the model calls to ask the user a clarifying question."""

_TOOL_CALL_MARKER = ":tool_call:"


def build_ask_user_tool() -> Any:
    """Build the Strands ``ask_user`` tool (raises an interrupt when called)."""
    from strands import tool
    from strands.types.tools import ToolContext

    # `context=True` injects the ToolContext as `tool_context`; the annotation is
    # evaluated at def time (no `from __future__ import annotations`) so Strands
    # can resolve it from this scope.
    @tool(name=ASK_USER_TOOL, context=True)
    def ask_user(
        tool_context: ToolContext,
        question: str,
        options: list[str] | None = None,
        allow_custom: bool = True,
    ) -> str:
        """Ask the user a clarifying question and wait for their answer.

        Use this only when you genuinely cannot proceed without the user's input
        (a missing fact, an ambiguous choice, or a preference). Keep the question
        short and specific. When the answer is a choice, pass a short list of
        options. Never use this for routine confirmation.

        Args:
            question: The clarifying question to ask the user.
            options: Short suggested answers, offered as buttons.
            allow_custom: Whether the user may type their own answer instead.
        """
        response = tool_context.interrupt(
            ASK_USER_TOOL,
            reason={
                "question": str(question or "").strip(),
                "options": [
                    str(option) for option in (options or []) if str(option or "").strip()
                ],
                "allowCustom": bool(allow_custom),
            },
        )
        if isinstance(response, dict):
            return str(response.get("answer") or response.get("value") or response)
        return str(response)

    return ask_user


def question_from_interrupt(interrupt: Any) -> dict[str, Any] | None:
    """Turn a Strands interrupt into the wire ``question`` fields (or ``None``)."""
    if interrupt is None:
        return None
    name = str(getattr(interrupt, "name", "") or "")
    if name and name != ASK_USER_TOOL:
        return None
    reason = getattr(interrupt, "reason", None)
    if not isinstance(reason, dict):
        reason = {"question": str(reason or "")}
    options = reason.get("options")
    return {
        "questionId": str(getattr(interrupt, "id", "") or ""),
        "question": str(reason.get("question") or ""),
        "options": [str(option) for option in options] if isinstance(options, list) else [],
        "allowCustom": bool(reason.get("allowCustom", True)),
    }


def tool_use_id_from_interrupt_id(interrupt_id: str) -> str:
    """Extract the originating ``toolUseId`` from a tool interrupt id, if any.

    Strands' ``ToolContext._interrupt_id`` is
    ``v1:tool_call:<toolUseId>:<uuid5>``; hook-scoped interrupts have no marker
    and return an empty string.
    """
    value = str(interrupt_id or "")
    if _TOOL_CALL_MARKER not in value:
        return ""
    rest = value.split(_TOOL_CALL_MARKER, 1)[1]
    return rest.split(":", 1)[0]


def pending_interrupt_responses(owner: Any, message: str) -> list[dict[str, Any]] | None:
    """Answers for a session left paused by an earlier question.

    A new message can arrive while the Strands session is still paused at an
    ``ask_user`` interrupt (e.g. a stale tab, or the question was never answered).
    ``stream_async`` refuses a plain string in that state, so recover by resuming
    the pending interrupt(s) with the new message folded in — the run continues
    instead of failing. Returns ``None`` when nothing is pending.
    """
    state = getattr(owner, "_interrupt_state", None)
    if state is None or not getattr(state, "activated", False):
        return None
    pending = [
        interrupt
        for interrupt in (getattr(state, "interrupts", {}) or {}).values()
        if getattr(interrupt, "response", None) is None
    ]
    if not pending:
        return None
    guidance = (
        "The user did not answer your earlier question and instead sent a new "
        f"message: {message!r}. If it answers your question, treat it as the "
        "answer; otherwise treat it as a new instruction and proceed."
    )
    return [
        {"interruptResponse": {"interruptId": interrupt.id, "response": guidance}}
        for interrupt in pending
    ]


def interrupt_responses(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Read the client's answers from the run payload, in Strands' wire shape."""
    raw = payload.get("interruptResponses")
    if not isinstance(raw, list) or not raw:
        return None
    responses: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        interrupt_id = str(entry.get("interruptId") or "").strip()
        if not interrupt_id:
            continue
        responses.append(
            {
                "interruptResponse": {
                    "interruptId": interrupt_id,
                    "response": entry.get("response"),
                }
            }
        )
    return responses or None

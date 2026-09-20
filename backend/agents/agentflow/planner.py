"""Plan a run before executing it.

The planner is a short, tool-free model call that turns the user's request into
a small JSON plan: a one-line understanding, the sub-queries worth running, and,
under each sub-query, an ordered todo list. The runtime forwards the plan to the
client (so the UI can show a live checklist) and folds it into the agent's
instructions so the run follows the plan.
"""

from __future__ import annotations

import json
import re
from typing import Any

from agentflow.config import RuntimeConfig
from agentflow.models import build_model, resolve_model_id

# Planning wants the strongest reasoning model, independent of the agent's own
# (often cheaper) model. Overridable with AGENT_PLANNER_MODEL.
DEFAULT_PLANNER_MODEL = "deepseek-v4-flash-vision-exp"
MAX_SUB_QUERIES = 4
MAX_TODOS_PER_SUB_QUERY = 5

_SYSTEM_PROMPT = """You are a planning assistant for an AI agent.
Break the user's request into sub-queries, and a short todo list for each.

Return ONLY a JSON object with exactly this shape:
{
  "understanding": "one sentence describing what the user wants",
  "subQueries": [
    {
      "query": "an independent search or sub-question",
      "todos": [
        {
          "id": "1",
          "title": "short human-readable action",
          "detail": "one line explaining the step",
          "tool": "comma-separated tool names this step uses (required)",
          "query": "the query to pass to that tool, or empty"
        }
      ]
    }
  ]
}

Rules:
- Use as FEW sub-queries as possible: 1 for a simple request, 2-4 for a
  multi-dimensional one. Never create more than 4, and never one sub-query per
  fact.
- Only create a sub-query when it involves at least one tool call. Never create
  a sub-query for pure reasoning, summarizing or writing — those are not steps.
- Prefer FEW todos: 1 to 3 per sub-query. Keep the checklist short.
- A single todo may use SEVERAL tool calls. Group related lookups into one todo
  instead of splitting them into one todo per tool call.
- Every todo MUST name at least one tool. `tool` is a comma-separated list of the
  exact tool names that todo uses. Never create a todo that uses no tool — if a
  step needs no tool, it is not a todo and must be omitted.
- Do NOT repeat the same tool with near-duplicate queries.
- The todos are executed strictly in order, one at a time: order them so each
  step is a prerequisite of the next.
- Titles must be short and plain: no JSON, no markdown, no quotes.
- Never answer the user's question here; only plan the work.
"""


def _extract_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    candidate = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.DOTALL)
    if fenced:
        candidate = fenced.group(1)
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        pass
    start = candidate.find("{")
    end = candidate.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(candidate[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError):
            return None
    return None


def _clean_todos(entries: Any) -> list[dict[str, str]]:
    if not isinstance(entries, list):
        return []
    todos: list[dict[str, str]] = []
    for index, entry in enumerate(entries[:MAX_TODOS_PER_SUB_QUERY]):
        if isinstance(entry, str):
            entry = {"title": entry}
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        tool = str(entry.get("tool") or "").strip()[:100]
        # A step that uses no tool is reasoning, not an action — omit it so the
        # UI never shows a todo without a tool call.
        if not tool:
            continue
        todos.append(
            {
                "id": str(entry.get("id") or index + 1)[:32],
                "title": title[:200],
                "detail": str(entry.get("detail") or "").strip()[:300],
                "tool": tool,
                "query": str(entry.get("query") or "").strip()[:500],
            }
        )
    return todos


def _clean_plan(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    understanding = str(raw.get("understanding") or "").strip()[:300]

    sub_queries: list[dict[str, Any]] = []
    entries = raw.get("subQueries")
    if isinstance(entries, list):
        for index, entry in enumerate(entries[:MAX_SUB_QUERIES]):
            if isinstance(entry, str):
                entry = {"query": entry}
            if not isinstance(entry, dict):
                continue
            query = str(entry.get("query") or entry.get("text") or "").strip()[:300]
            todos = _clean_todos(entry.get("todos"))
            # Drop sub-queries that contain no tool step.
            if not todos:
                continue
            sub_queries.append(
                {"id": str(entry.get("id") or index + 1)[:32], "query": query, "todos": todos}
            )

    # Backward compatibility: a flat todo list becomes one sub-query.
    if not sub_queries:
        todos = _clean_todos(raw.get("todos"))
        if todos:
            sub_queries.append(
                {"id": "1", "query": understanding or "Plan", "todos": todos}
            )

    if not sub_queries:
        return None
    return {"understanding": understanding, "subQueries": sub_queries}


def _planner_prompt(
    user_input: str,
    agent_prompt: str,
    tool_names: list[str],
    knowledge_names: list[str],
    skills: list[dict[str, Any]],
) -> str:
    lines: list[str] = []
    agent_prompt = (agent_prompt or "").strip()
    if agent_prompt:
        lines.append(f"Agent instructions (context):\n{agent_prompt[:2000]}")
        lines.append("")
    lines.append(f"User request:\n{user_input}")
    lines.append("")
    lines.append("Available tools: " + (", ".join(tool_names) if tool_names else "none"))
    if knowledge_names:
        lines.append("Knowledge bases: " + ", ".join(knowledge_names))
    if skills:
        lines.append(
            "Skills: " + ", ".join(str(s.get("name") or "") for s in skills if s.get("name"))
        )
    lines.append("")
    lines.append("Return the plan JSON now.")
    return "\n".join(lines)


def build_plan(
    config: RuntimeConfig,
    agent_config: dict[str, Any],
    user_input: str,
    tool_names: list[str],
    knowledge_names: list[str],
    skills: list[dict[str, Any]],
    session_id: str | None = None,
    history: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Return a cleaned plan, or None when planning is disabled/unavailable.

    ``history`` is the conversation so far (text-only user/assistant turns) so the
    plan can resolve references to earlier messages.
    """
    if not config.planner_enabled or not config.opencode_api_key:
        return None

    from strands import Agent

    model = build_model(
        config,
        resolve_model_id(config.planner_model or DEFAULT_PLANNER_MODEL),
        session_id,
    )
    planner = Agent(
        model=model,
        system_prompt=_SYSTEM_PROMPT,
        messages=list(history or []),
        callback_handler=None,
    )
    prompt = _planner_prompt(
        user_input,
        str(agent_config.get("prompt") or ""),
        tool_names,
        knowledge_names,
        skills,
    )
    result = planner(prompt)
    return _clean_plan(_extract_json(str(result)))


def execution_input(user_input: str, plan: dict[str, Any]) -> str:
    """Fold the plan into the user message so the agent executes step by step."""
    sub_queries = plan.get("subQueries") or []
    if not sub_queries:
        return user_input

    lines = [
        "User request:",
        user_input,
        "",
        "Execution plan — work through these in order:",
    ]
    step = 0
    for sub_query in sub_queries:
        query = sub_query.get("query")
        if query:
            lines.append(f"\nSub-query: {query}")
        for todo in sub_query.get("todos") or []:
            step += 1
            line = f"{step}. {todo.get('title')}"
            detail = todo.get("detail")
            if detail:
                line += f" — {detail}"
            if todo.get("tool"):
                line += f" (use the `{todo['tool']}` tool"
                if todo.get("query"):
                    line += f" with query: \"{todo['query']}\""
                line += ")"
            lines.append(line)
    lines.append("")
    lines.append(
        "Execute the steps strictly in sequential order, one at a time. Finish "
        "the current step (including any tool call) before starting the next, and "
        "never run tools for different steps in parallel. Then write the final "
        "answer for the user. Cite every fact taken from a tool with the source's "
        "bracketed `index`, e.g. [1]."
    )
    return "\n".join(lines)

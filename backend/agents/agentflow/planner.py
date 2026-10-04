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
DEFAULT_PLANNER_MODEL = "zai.glm-4.7-flash"
MAX_SUB_QUERIES = 4
MAX_TODOS_PER_SUB_QUERY = 5

_SYSTEM_PROMPT = """You are an expert planning assistant for an AI agent — a lead
researcher who turns a request into the SMALLEST correct set of tool steps.

Return ONLY a JSON object with exactly this shape:
{
  "understanding": "one sentence describing what the user actually wants",
  "subQueries": [
    {
      "query": "an independent search or sub-question",
      "todos": [
        {
          "id": "1",
          "title": "short human-readable action",
          "detail": "one line explaining the step",
          "tool": "comma-separated exact tool names this step uses (required)",
          "query": "the argument to pass to that tool, or empty"
        }
      ]
    }
  ]
}

Source priority — apply strictly, in this order:
1. KNOWLEDGE BASES (highest priority). If any "Knowledge bases" are listed they
   are the agent's authoritative, user-specific source. The FIRST step MUST
   search them with `search-user-knowledge-bases` (call
   `get-user-knowledge-bases` once first only if unsure what exists). This is
   required whenever knowledge bases are attached — they often hold context that
   changes the answer (a resume/profile, policies, past work, uploaded docs).
   Omit only for pure chit-chat that cannot depend on stored data.
2. SKILLS. If a listed skill clearly matches the request, add a step whose
   `tool` is `skills` and whose `query` is that skill's exact name, so the agent
   loads and follows it. Put it before the tools that skill needs. Never put a
   skill's own name in `tool` — the tool is always `skills`.
3. TOOLS. Use the listed tools (web search, MCP servers, code interpreter, …)
   for external or current information and for actions.
4. Pure reasoning, summarizing or writing needs NO step.

Rules:
- Use as FEW sub-queries as possible: 1 for a simple request, 2-4 for a
  multi-dimensional one. Never more than 4, and never one sub-query per fact.
- Prefer FEW todos: 1 to 3 per sub-query. A single todo may use SEVERAL tools —
  group related lookups instead of one todo per call.
- Every todo MUST name at least one tool. `tool` is a comma-separated list of
  exact names from "Available tools" (or `skills` for a skill step). Never
  invent a tool name.
- Do NOT repeat the same tool with near-duplicate queries.
- Todos run strictly in order, one at a time: order them so each step is a
  prerequisite of the next.
- Titles must be short and plain: no JSON, no markdown, no quotes.
- Never answer the user's question here; only plan the work.
- The final answer will be written ONLY from the tool results of this plan, so
  every todo must retrieve the facts the answer needs. If a fact cannot be
  retrieved by a tool, it must not appear in the answer.
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


def _norm_tool(name: str) -> str:
    """Canonical form for matching planner-named tools to real tool names.

    The planner may echo a name with backticks, quotes, spaces, ``_`` instead of
    ``-``, or the original ``slug/tool`` form while the Strands tool name is
    sanitized (``slug_tool``). Normalizing both sides keeps a valid tool from
    being dropped, without letting a truly invented name through.
    """
    return re.sub(r"[^a-z0-9]+", "-", (name or "").strip().lower()).strip("-")


def _clean_todos(
    entries: Any,
    skill_names: frozenset[str] = frozenset(),
    known_tools: frozenset[str] = frozenset(),
) -> list[dict[str, str]]:
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
        raw_tool = str(entry.get("tool") or "").strip()[:100]
        query = str(entry.get("query") or "").strip()[:500]
        resolved: list[str] = []
        wanted_skill = ""
        for name in raw_tool.split(","):
            cleaned = name.strip().strip("`\"'")
            if not cleaned:
                continue
            if cleaned.lower() in skill_names:
                # The planner named a skill directly: it is loaded through the
                # `skills` tool, never called as a tool itself.
                wanted_skill = wanted_skill or cleaned
                continue
            # Drop invented / unavailable tool names (e.g. `global_search`) so
            # they never reach the agent as "Unknown tool". Normalized so
            # backticks / ``_`` / ``slug/tool`` still resolve to a real tool.
            if known_tools and _norm_tool(cleaned) not in known_tools:
                continue
            resolved.append(cleaned)
        if wanted_skill:
            if "skills" not in resolved:
                resolved.insert(0, "skills")
            if not query:
                query = wanted_skill
        tool = ", ".join(resolved)[:100]
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
                "query": query,
            }
        )
    return todos


def _clean_plan(
    raw: dict[str, Any] | None,
    skill_names: frozenset[str] = frozenset(),
    known_tools: frozenset[str] = frozenset(),
) -> dict[str, Any] | None:
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
            todos = _clean_todos(entry.get("todos"), skill_names, known_tools)
            # Drop sub-queries that contain no tool step.
            if not todos:
                continue
            sub_queries.append(
                {"id": str(entry.get("id") or index + 1)[:32], "query": query, "todos": todos}
            )

    # Backward compatibility: a flat todo list becomes one sub-query.
    if not sub_queries:
        todos = _clean_todos(raw.get("todos"), skill_names, known_tools)
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
    if knowledge_names:
        lines.append(
            "Attached knowledge bases (authoritative, user-specific — the plan "
            "MUST search these first): " + ", ".join(knowledge_names)
        )
    else:
        lines.append("Attached knowledge bases: none")
    lines.append("Available tools: " + (", ".join(tool_names) if tool_names else "none"))
    described_skills: list[str] = []
    for skill in skills:
        name = str(skill.get("name") or "").strip()
        if not name:
            continue
        description = str(skill.get("description") or "").strip()
        allowed = [
            str(tool) for tool in (skill.get("allowedTools") or []) if str(tool).strip()
        ]
        entry = name
        if description:
            entry += f" — {description}"
        if allowed:
            entry += f" (tools: {', '.join(allowed)})"
        described_skills.append(entry)
    if described_skills:
        lines.append(
            "Available skills (load one with the `skills` tool when it matches): "
            + " | ".join(described_skills)
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
    if not config.planner_enabled:
        return None

    from strands import Agent

    model = build_model(
        config,
        resolve_model_id(config.planner_model or DEFAULT_PLANNER_MODEL),
        session_id,
    )
    planner = Agent(
        name="planner",
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
    skill_names = frozenset(
        str(skill.get("name") or "").strip().lower()
        for skill in skills
        if skill.get("name")
    )
    # Only tool names this run actually offers are valid plan steps — a
    # hallucinated name (e.g. `global_search`) is dropped before execution.
    # Normalized so backticks / `_` / `slug/tool` still resolve to a real tool.
    known = {_norm_tool(str(name)) for name in tool_names if str(name).strip()}
    if skills:
        # Skills are activated through the plugin's `skills` tool, which is not
        # part of the MCP tool list — allow it as a valid step.
        known.add("skills")
    known_tools = frozenset(known)
    result = planner(prompt)
    return _clean_plan(_extract_json(str(result)), skill_names, known_tools)


_KNOWLEDGE_TOOLS = ("get-user-knowledge-bases", "search-user-knowledge-bases")


def _plan_has_knowledge_step(plan: dict[str, Any]) -> bool:
    for sub_query in plan.get("subQueries") or []:
        for todo in sub_query.get("todos") or []:
            names = str(todo.get("tool") or "")
            if any(tool in names for tool in _KNOWLEDGE_TOOLS):
                return True
    return False


def ensure_knowledge_plan(
    plan: dict[str, Any] | None, knowledge_names: list[str]
) -> dict[str, Any] | None:
    """Guarantee the plan consults the attached knowledge bases first.

    The planner is *asked* to do this, but a model can omit it; when knowledge
    bases are attached (and their tools are available) we deterministically
    prepend a knowledge-base search step so the KB is always checked first.

    Returns the (possibly new) plan, or the plan unchanged when there are no
    knowledge bases or a KB step already exists.
    """
    if not knowledge_names:
        return plan
    base = plan if isinstance(plan, dict) else {"understanding": "", "subQueries": []}
    if _plan_has_knowledge_step(base):
        return base
    step = {
        "id": "kb-1",
        "title": "Check the attached knowledge bases",
        "detail": "Search the user's stored knowledge (profile/resume/documents) before other sources.",
        "tool": "search-user-knowledge-bases",
        "query": "profile, resume, and any stored context relevant to the request",
    }
    sub_queries = list(base.get("subQueries") or [])
    sub_queries.insert(
        0, {"id": "kb", "query": "Knowledge base context", "todos": [step]}
    )
    return {"understanding": base.get("understanding") or "", "subQueries": sub_queries}


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
            tool = str(todo.get("tool") or "").strip()
            if tool == "skills":
                # A skill step: load that skill's instructions before continuing.
                skill = str(todo.get("query") or "").strip()
                line += (
                    f' (load the "{skill}" skill with the `skills` tool)'
                    if skill
                    else " (use the `skills` tool)"
                )
            elif tool:
                line += f" (use the `{tool}` tool"
                if todo.get("query"):
                    line += f" with query: \"{todo['query']}\""
                line += ")"
            lines.append(line)
    lines.append("")
    lines.append(
        "Execute the steps strictly in sequential order, one at a time. Finish "
        "the current step (including any tool call) before starting the next, and "
        "never run tools for different steps in parallel. Then write the final "
        "answer using ONLY the results of these tool calls — do not add facts "
        "from your own knowledge. Cite every fact with the source's bracketed "
        "`index`, e.g. [1]. If the steps did not return the answer, say you could "
        "not find it in the available sources."
    )
    return "\n".join(lines)

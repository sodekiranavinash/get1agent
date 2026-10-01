"""Build the Strands AgentSkills plugin from a user's resolved skills.

Skills follow the Agent Skills specification and use **progressive disclosure**:
only lightweight metadata (name + description) is injected into the system
prompt, and the agent calls the ``skills`` tool to load a skill's full
instructions when it decides the skill applies. The plugin also persists the
activated-skill state on the agent (and therefore the conversation session).

The alternative — pasting every skill body into the system prompt on every run —
makes the model unable to choose, wastes context and creates no activation event.
Always prefer this plugin.
"""

from __future__ import annotations

from typing import Any


def build_skills_plugin(skills: list[dict[str, Any]]) -> Any:
    """Return an ``AgentSkills`` plugin for the resolved skills, or ``None``.

    ``skills`` is the shape returned by ``agentflow.store.resolve_skills``
    (``{id, name, description, allowedTools, content}``).
    """
    usable = [skill for skill in skills if str(skill.get("name") or "").strip()]
    if not usable:
        return None

    from strands.vended_plugins.skills import AgentSkills, Skill

    prepared: list[Any] = []
    for skill in usable:
        name = str(skill.get("name") or "").strip()
        description = str(skill.get("description") or "").strip()
        prepared.append(
            Skill(
                name=name,
                # The plugin renders the description into the prompt, so keep it
                # non-empty even for skills saved without one.
                description=description or f"Custom skill '{name}'.",
                instructions=str(skill.get("content") or ""),
                allowed_tools=list(skill.get("allowedTools") or []) or None,
            )
        )

    return AgentSkills(skills=prepared)

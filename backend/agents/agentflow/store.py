"""Load an agent's config and resolve its owner-scoped references."""

from __future__ import annotations

from typing import Any

from data.repositories import agents as agents_repo
from data.repositories import knowledge_bases as kb_repo
from data.repositories import skills as skills_repo


class AgentNotFound(Exception):
    pass


def load_agent(user_id: str, agent_id: str) -> dict[str, Any]:
    agent = agents_repo.get_agent(user_id, agent_id)
    if agent is None:
        raise AgentNotFound(f"Agent {agent_id} not found for this user")
    return agent


def resolve_knowledge_bases(user_id: str, kb_ids: list[str]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for kb_id in kb_ids:
        kb = kb_repo.get_kb(user_id, kb_id)
        if kb and kb.get("status") == "ready":
            resolved.append({"id": kb.get("kbId"), "name": kb.get("name")})
    return resolved


def resolve_skills(user_id: str, skill_ids: list[str]) -> list[dict[str, Any]]:
    resolved: list[dict[str, Any]] = []
    for skill_id in skill_ids:
        skill = skills_repo.get_skill(user_id, skill_id)
        if skill is None:
            continue
        resolved.append(
            {
                "id": skill.get("skillId"),
                "name": skill.get("name"),
                "description": skill.get("description"),
                "allowedTools": skill.get("allowedTools") or [],
                "content": skill.get("content") or "",
            }
        )
    return resolved

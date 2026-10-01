"""Load a workflow and resolve its agent-node references.

Agent nodes reference saved agents by id; a node may override a few fields
(model, prompt, reasoning, MCP servers, skills) for this workflow only. Nothing
is embedded — the referenced agent is loaded fresh and its config merged with the
node's overrides.
"""

from __future__ import annotations

import re
from typing import Any

from data.repositories import agents as agents_repo
from data.repositories import workflows as workflows_repo


class WorkflowNotFound(Exception):
    pass


def load_workflow(user_id: str, workflow_id: str) -> dict[str, Any]:
    workflow = workflows_repo.get_workflow(user_id, workflow_id)
    if workflow is None:
        raise WorkflowNotFound(f"Workflow {workflow_id} not found for this user")
    return workflow


def merge_config(agent_config: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Return the agent's config with this node's overrides applied.

    Only the fields the user changed are present in ``overrides``; everything
    else is inherited from the saved agent, so edits to the agent propagate to
    every workflow that has not overridden that field.
    """
    merged = dict(agent_config or {})
    if not overrides:
        return merged
    for key in ("model", "prompt", "reasoning", "servers", "skillIds"):
        if key in overrides and overrides[key] is not None:
            merged[key] = overrides[key]
    return merged


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", (value or "").lower()).strip("-")
    return slug or "agent"


def _unique_node_id(agent: dict[str, Any], used: set[str]) -> str:
    base = _slug(str(agent.get("name") or agent.get("agentId") or "agent"))
    node_id = base
    index = 2
    while node_id in used:
        node_id = f"{base}-{index}"
        index += 1
    return node_id


def resolve_agent_nodes(
    user_id: str,
    workflow_config: dict[str, Any],
    agent_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Resolve every agent node to its effective agent + config.

    Returns a list of node specs (``nodeId``, ``agentId``, ``agentName``,
    ``description``, ``agent``, ``config``). Agent nodes whose referenced agent no
    longer exists are skipped with a warning (the run continues with the rest).

    When ``agent_ids`` is given (the chat run settings), it is the **per-run**
    selection: the saved nodes for those agents keep their ids/overrides/edges,
    and any selected agent that is not already a node is appended as a new,
    edge-less node (an entry + sink, so it runs in parallel). The workflow config
    itself is never modified.
    """
    saved_nodes: list[dict[str, Any]] = []
    by_agent: dict[str, dict[str, Any]] = {}
    for node in workflow_config.get("nodes") or []:
        if not isinstance(node, dict) or node.get("type") != "agent":
            continue
        data = node.get("data") or {}
        agent_id = str(data.get("agentId") or "")
        if not agent_id:
            continue
        entry = {"nodeId": str(node.get("id")), "agentId": agent_id, "data": data}
        saved_nodes.append(entry)
        by_agent.setdefault(agent_id, entry)

    if agent_ids is None:
        ordered = [entry["agentId"] for entry in saved_nodes]
    else:
        ordered = []
        for value in agent_ids:
            text = str(value or "").strip()
            if text and text not in ordered:
                ordered.append(text)

    used: set[str] = set()
    specs: list[dict[str, Any]] = []
    for agent_id in ordered:
        entry = by_agent.get(agent_id)
        data = (entry or {}).get("data") or {}
        agent = agents_repo.get_agent(user_id, agent_id)
        if agent is None:
            continue
        config = merge_config(agent.get("config") or {}, data.get("overrides") or {})
        node_id = str((entry or {}).get("nodeId") or "") or _unique_node_id(agent, used)
        used.add(node_id)
        specs.append(
            {
                "nodeId": node_id,
                "agentId": agent_id,
                "agentName": str(agent.get("name") or data.get("agentName") or agent_id),
                "description": str(agent.get("description") or ""),
                "agent": agent,
                "config": config,
            }
        )
    return specs

"""Build the Strands agents and the Graph/Swarm that orchestrates them.

The workflow's **input card is its host agent**: it owns the workflow system
prompt, the starting query and its own model, and it is never one of the saved
agents. Both modes use it:

* **Swarm** — the host is the swarm entry point and hands off to the saved agents
  with the injected ``handoff_to_agent`` tool.
* **Graph** — the host dispatches (its brief becomes the entry agents' input),
  the saved agents run along the wired edges, then a second host pass synthesizes
  their outputs into the final answer.

Every saved agent node becomes a Strands ``Agent`` whose model, tools and prompt
come from the referenced agent (with the node's overrides applied). The
orchestration itself is delegated to Strands; this module only assembles it.
"""

from __future__ import annotations

from typing import Any

from agentflow.config import RuntimeConfig
from agentflow.context import TruncatingModel
from agentflow.models import build_model, resolve_model_id
from agentflow.prompts import build_system_prompt
from agentflow.provider import resolve_model_provider
from agentflow.skills import build_skills_plugin
from agentflow.store import resolve_knowledge_bases, resolve_skills
from agentflow.tools import build_tools

from workflow.store import resolve_agent_nodes

# Reserved graph node ids for the host. They never collide with saved-agent node
# ids because the frontend slugs those from agent names.
HOST_NODE_ID = "host"
HOST_SYNTH_NODE_ID = "host-synth"

DEFAULT_HOST_PROMPT = (
    "You are the host agent of a multi-agent workflow. You receive the user's "
    "request and coordinate a team of specialist agents to fulfil it."
)
DEFAULT_MEMBER_PROMPT = "You are a helpful AI agent."

_SWARM_HOST_INSTRUCTION = (
    "You lead this team. Decide which teammate is best for each part of the "
    "request and hand off to them with `handoff_to_agent`. You own the final "
    "answer: once the team has what it needs, write the complete response "
    "yourself instead of handing off again."
)

_GRAPH_DISPATCH_INSTRUCTION = (
    "You are the dispatch step of this workflow. Read the user's request and "
    "produce a clear, self-contained brief that your team of agents will "
    "execute. State the goal, the key questions and any constraints. Do not "
    "answer the request yourself and do not call any tools."
)

_GRAPH_SYNTH_INSTRUCTION = (
    "You are the synthesis step of this workflow. You receive the outputs of "
    "the team's agents. Combine them into one coherent final answer for the "
    "user, resolving overlaps and filling any gaps. Cite sources inline with "
    "their bracketed index where relevant."
)


def _node_specs(
    config: RuntimeConfig,
    user_id: str,
    workflow_config: dict[str, Any],
    agent_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    return resolve_agent_nodes(user_id, workflow_config, agent_ids)


def _team_block(specs: list[dict[str, Any]]) -> str:
    lines = [
        "Your team (hand off with the teammate's id as `agent_name`):",
    ]
    for spec in specs:
        description = f" — {spec['description']}" if spec["description"] else ""
        lines.append(f"- `{spec['nodeId']}` — {spec['agentName']}{description}")
    return "\n".join(lines)


def _graph_block() -> str:
    return (
        "You are one agent in a multi-agent workflow. You receive the host's "
        "brief or the previous agent's output as your input, and your result is "
        "passed to the next step."
    )


# Members are intermediate steps, not the final responder. This frames their
# role; the length/depth of each result follows that agent's own answer mode.
_MEMBER_RESULT_INSTRUCTION = (
    "You are an intermediate step in a multi-agent workflow, not the final "
    "responder: your result is passed on and the host assembles the final answer "
    "for the user. Return your step's result directly — do not address the end "
    "user, do not add a greeting or sign-off."
)


def _build_prompt(
    base_config: dict[str, Any],
    skills: list[dict[str, Any]],
    *,
    extra: str = "",
    output_instructions: str = "",
    output_format: str = "markdown",
    human_in_loop: bool | None = None,
) -> str:
    prompt = dict(base_config)
    if output_instructions:
        output = dict(prompt.get("output") or {})
        output["format"] = output_format
        output["instructions"] = (
            (output.get("instructions") or "").strip()
            + ("\n" if output.get("instructions") else "")
            + output_instructions
        ).strip()
        prompt["output"] = output
    base = build_system_prompt(prompt, skills, human_in_loop=human_in_loop)
    return f"{base}\n\n{extra}".strip() if extra else base


def _host_config(
    workflow_config: dict[str, Any],
    output_format: str,
    overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], str]:
    input_config = workflow_config.get("input") or {}
    prompt = str(input_config.get("prompt") or "").strip() or DEFAULT_HOST_PROMPT
    model_id = resolve_model_id(input_config.get("model"))
    base: dict[str, Any] = {
        "prompt": prompt,
        "output": {"format": output_format, "instructions": ""},
    }
    # The chat composer's answer-mode / reasoning pickers apply to the workflow
    # HOST (the coordinator and final answerer), never to the member agents.
    if overrides:
        if overrides.get("answerMode"):
            base["answerMode"] = overrides["answerMode"]
        if overrides.get("reasoning"):
            base["reasoning"] = overrides["reasoning"]
    return base, model_id


def _make_host(
    config: RuntimeConfig,
    conversation_id: str,
    model_id: str,
    base_config: dict[str, Any],
    *,
    name: str,
    extra: str,
    output_instructions: str,
    output_format: str,
    human_in_loop: bool | None = None,
) -> Any:
    from strands import Agent

    from agentflow.hitl import build_ask_user_tool

    tools = [build_ask_user_tool()] if human_in_loop else []
    return Agent(
        name=name,
        model=TruncatingModel(build_model(config, model_id, conversation_id)),
        tools=tools,
        system_prompt=_build_prompt(
            base_config,
            [],
            extra=extra,
            output_instructions=output_instructions,
            output_format=output_format,
            human_in_loop=human_in_loop,
        ),
        callback_handler=None,
    )


def build_node_agents(
    config: RuntimeConfig,
    user_id: str,
    conversation_id: str,
    workflow_config: dict[str, Any],
    counter: dict[str, int],
    agent_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Build one Strands Agent per saved-agent node."""
    from strands import Agent

    specs = _node_specs(config, user_id, workflow_config, agent_ids)
    mode = workflow_config.get("mode") or "graph"
    extra = _team_block(specs) if mode == "swarm" else _graph_block()
    extra = f"{extra}\n\n{_MEMBER_RESULT_INSTRUCTION}"

    built: list[dict[str, Any]] = []
    for spec in specs:
        effective = spec["config"]
        # A member agent inherits its provider from the saved agent's config.
        provider = resolve_model_provider(user_id, effective.get("providerSecretId"))
        if provider:
            model_id = str(effective.get("model") or "").strip() or str(
                provider.get("defaultModel") or ""
            )
            if not model_id:
                raise ValueError("Select a model for the chosen provider")
        else:
            model_id = resolve_model_id(effective.get("model"))
        knowledge = resolve_knowledge_bases(
            user_id, list(effective.get("knowledgeBaseIds") or [])
        )
        skills = resolve_skills(user_id, list(effective.get("skillIds") or []))
        prompt = _build_prompt(effective, skills, extra=extra)
        skills_plugin = build_skills_plugin(skills)
        tools = build_tools(
            config,
            user_id,
            effective,
            [kb["name"] for kb in knowledge],
            counter,
        )
        agent = Agent(
            name=spec["nodeId"],
            model=TruncatingModel(
                build_model(config, model_id, conversation_id, provider=provider)
            ),
            tools=tools,
            plugins=[skills_plugin] if skills_plugin else None,
            system_prompt=prompt or DEFAULT_MEMBER_PROMPT,
            callback_handler=None,
        )
        spec = dict(spec)
        spec["agent"] = agent
        spec["model"] = model_id
        built.append(spec)
    return built


def _build_graph(
    dispatch: Any,
    synth: Any,
    members: list[dict[str, Any]],
    workflow_config: dict[str, Any],
) -> Any:
    from strands.multiagent import GraphBuilder

    builder = GraphBuilder()
    builder.add_node(dispatch, node_id=HOST_NODE_ID)
    for member in members:
        builder.add_node(member["agent"], node_id=member["nodeId"])
    builder.add_node(synth, node_id=HOST_SYNTH_NODE_ID)

    agent_ids = {member["nodeId"] for member in members}
    has_in: set[str] = set()
    has_out: set[str] = set()
    for edge in workflow_config.get("edges") or []:
        source = str(edge.get("source"))
        target = str(edge.get("target"))
        if source in agent_ids and target in agent_ids:
            builder.add_edge(source, target)
            has_out.add(source)
            has_in.add(target)

    entries = [node_id for node_id in agent_ids if node_id not in has_in] or list(agent_ids)
    sinks = [node_id for node_id in agent_ids if node_id not in has_out] or list(agent_ids)
    for entry in entries:
        builder.add_edge(HOST_NODE_ID, entry)
    for sink in sinks:
        builder.add_edge(sink, HOST_SYNTH_NODE_ID)

    builder.set_entry_point(HOST_NODE_ID)
    builder.set_max_node_executions(max(8, len(members) * 4 + 2))
    builder.set_execution_timeout(900.0)
    builder.set_node_timeout(300.0)
    return builder.build()


def build_workflow(
    config: RuntimeConfig,
    user_id: str,
    conversation_id: str,
    workflow_config: dict[str, Any],
    counter: dict[str, int],
    host_overrides: dict[str, Any] | None = None,
    agent_ids: list[str] | None = None,
    human_in_loop: bool | None = None,
) -> tuple[Any, str, list[dict[str, Any]]]:
    """Build the orchestrator.

    Returns ``(orchestrator, mode, nodes)`` where ``nodes`` is the ordered node
    metadata (hosts first/last around the members) the client renders.
    """
    mode = workflow_config.get("mode") or "graph"
    members = build_node_agents(
        config, user_id, conversation_id, workflow_config, counter, agent_ids
    )
    if not members:
        raise ValueError("This workflow has no runnable agents")
    output = workflow_config.get("output") or {}
    output_format = str(output.get("format") or "markdown")
    output_instructions = str(output.get("instructions") or "").strip()
    base, host_model = _host_config(workflow_config, output_format, host_overrides)

    meta: list[dict[str, Any]] = [
        {
            "nodeId": member["nodeId"],
            "agentName": member["agentName"],
            "model": member["model"],
            "role": "agent",
        }
        for member in members
    ]

    if mode == "swarm":
        from strands.multiagent import Swarm

        host = _make_host(
            config,
            conversation_id,
            host_model,
            base,
            name=HOST_NODE_ID,
            extra=_SWARM_HOST_INSTRUCTION + "\n\n" + _team_block(members),
            output_instructions=output_instructions,
            output_format=output_format,
            human_in_loop=human_in_loop,
        )
        nodes = [host] + [member["agent"] for member in members]
        swarm = Swarm(
            nodes=nodes,
            entry_point=host,
            max_handoffs=max(8, len(nodes) * 3),
            max_iterations=max(8, len(nodes) * 3),
            execution_timeout=900.0,
            node_timeout=300.0,
        )
        meta.insert(
            0,
            {
                "nodeId": HOST_NODE_ID,
                "agentName": "Host",
                "model": host_model,
                "role": "host",
                "stage": "host",
            },
        )
        return swarm, mode, meta

    dispatch = _make_host(
        config,
        conversation_id,
        host_model,
        base,
        name=HOST_NODE_ID,
        extra=_GRAPH_DISPATCH_INSTRUCTION,
        output_instructions="",
        output_format=output_format,
    )
    synth = _make_host(
        config,
        conversation_id,
        host_model,
        base,
        name=HOST_SYNTH_NODE_ID,
        extra=_GRAPH_SYNTH_INSTRUCTION,
        output_instructions=output_instructions,
        output_format=output_format,
        human_in_loop=human_in_loop,
    )
    graph = _build_graph(dispatch, synth, members, workflow_config)
    meta.insert(
        0,
        {
            "nodeId": HOST_NODE_ID,
            "agentName": "Host",
            "model": host_model,
            "role": "host",
            "stage": "dispatch",
        },
    )
    meta.append(
        {
            "nodeId": HOST_SYNTH_NODE_ID,
            "agentName": "Host",
            "model": host_model,
            "role": "host",
            "stage": "synthesis",
        }
    )
    return graph, mode, meta

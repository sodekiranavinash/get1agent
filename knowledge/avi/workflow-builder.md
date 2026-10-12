---
id: workflow-builder
title: Workflow builder
route: "/workflow-builder"
group: Build
audience: user
source: docs
tags: [docs, build]
---

## Workflow builder

Coordinate several saved agents as a deterministic graph or a dynamic swarm.

A workflow wires saved agents together. The Query card is the host agent: it owns the workflow system prompt and its own model, and it coordinates in both modes. Agents are added from the left palette by dragging onto the canvas (or clicking), and connected by dragging between their handles.

- Graph mode is deterministic: the host dispatches its brief to the entry agents, agents run along the wired agent-to-agent edges (independent ones in parallel), then a second host pass synthesises the outputs into the final answer.
- Swarm mode is dynamic: the host is the swarm entry point and hands off to teammates using an injected handoff tool.
- A schedule node can be attached to the Query card’s left side, like an agent schedule.

## Workflow builder

1. Open Workflows in the sidebar (or New workflow on the Dashboard) to start a workflow with just the Query and Output cards.
2. Click the Query card to set the host system prompt and model. Switch between graph and swarm with the mode control in the header.
3. Drag agents from the left palette onto the canvas, or click one to add it. Every added agent is connected to the host automatically.
4. Connect agents to each other by dragging between handles to define the execution order (graph mode).
5. Use the Inspect tab on the right to select any node. The host exposes its prompt and model; an agent exposes per-node overrides for model, prompt, reasoning, servers and skills.
6. Click Add schedule in the inspector to attach a cron schedule to the Query card.

## Workflow builder

7. Press Save, then open the Run tab and type a question in the run composer. The Run/Stop action lives there — the question is typed per run and never saved.
8. Watch the WorkflowRunTimeline for per-node status, tool calls and timing. When the answer is ready, use View final answer to open the persisted conversation in Chat — that is where the answer renders.

## Workflow builder

**How transitions read** — In swarm mode an inbound transition reads “Handoff from X”; in graph mode it reads “From X” because it is a batch transition, not a handoff. The graph synthesiser host is never shown as a step.

**Limits** — Up to 50 workflows per user, 10 agents, 100 nodes and 300 edges per workflow, and 256 KB of configuration.

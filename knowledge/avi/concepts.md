---
id: concepts
title: Core concepts
route: "/docs#concepts"
group: Getting started
audience: public
source: docs
tags: [docs, start]
---

## Core concepts

The shared vocabulary used across every page in the app.

## Core concepts

- Agent: one saved configuration — a system prompt, a model, an answer mode, optional knowledge bases, MCP servers, skills and attached files. Runs stream live in Chat.
- Workflow: several saved agents coordinated by a host agent, either as a deterministic graph or a dynamic swarm. Workflows reference agents by id; they never embed them.
- Knowledge base: a searchable collection of documents. Hybrid search (semantic + keyword) with small-to-big retrieval returns precise passages plus their surrounding page.
- MCP server: a Model Context Protocol tool server. Built-ins are web-search, code-interpreter, http-fetch, storage and browser; remote servers are connected over OAuth or an API key; custom servers are Python tools you build in the MCP Builder. Every tool call is routed through AgentCore Gateway and checked by AgentCore Policy.

## Core concepts

- Skill: a Strands-format markdown document (YAML frontmatter plus a body) that grants an agent reusable instructions and declares which MCP servers it may use.
- Memory: durable facts and preferences an agent keeps across sessions in AgentCore Memory, shared by that useru2019s agents.
- Conversation: one persisted transcript. Chat and builder runs each create a conversation that can be reopened later from the sidebar or History tab.
- Trace: the full AWS (CloudWatch/X-Ray) record of one run — the agent loop, model generations, tool calls, tokens and cost. Traces feed Datasets, Review queues and Metrics (AWS-native).
- Vault secret: an encrypted key, token or connection string. Secrets are only ever referenced, never displayed back to the browser.

## Core concepts

**How the pieces fit** — Knowledge, skills and tools are inputs to an agent. Agents are inputs to workflows. Both produce conversations and traces that you can evaluate, curate and monitor. The Vault feeds credentials into all of them.

---
id: agent-builder
title: Agent builder
route: "/agent-builder"
group: Build
audience: user
source: docs
tags: [docs, build]
---

## Agent builder

Compose one agent from a prompt, model, knowledge, MCP tools, skills and an optional schedule.

The Agent builder is a fixed React Flow canvas. The agent sits in the middle with Input on top, Output on the bottom, Schedule on the left, and Knowledge, MCP servers & tools and Skills stacked down the right. Every card is permanent — equal size, not draggable — and clicking anywhere on it opens a dialog with all of its options.

## Agent builder

1. Open the builder from Dashboard, the Agents library (New agent) or the /agent-builder route.
2. Click the name at the top left to set the agent name and description. Names are lowercase-hyphen, 1–64 characters and unique per user.
3. Click the Agent card to set the system prompt, model, reasoning effort and Answer mode (Summarize, Normal or Detailed).
4. Click the Knowledge card to attach any ready knowledge bases.
5. Click the MCP servers & tools card to select built-in, remote or custom servers, and choose which tools are enabled per server.
6. Click the Skills card to attach skills. Selecting a skill automatically adds the MCP servers it declares.
7. Click the Schedule card to add a cron schedule (frequency, time, day and timezone). It is mirrored into the scheduler registry on save.

## Agent builder

8. Click the Input card to add up to eight starter questions and attach storage files. The Output card configures the output format and instructions.
9. Press Save. Edits also autosave to a local draft; the small dot on Save means unsaved changes.
10. Open the right-hand Agent panel, use its Live tab run composer to ask a question, and watch the run timeline. Publish (bottom right) sends the agent to the library.

## Agent builder

- The right panel has Response (Live), History and Errors tabs. History lists the persisted runs and links into Chat to reopen one.
- Publishing flips visibility to public so anyone in the workspace can find and install a copy; Unpublish reverses it.
- Delete permanently removes the agent. Copies others already installed are not affected.
- A run performed in the builder always creates a fresh conversation.

**Start minimal** — A prompt plus one knowledge base is a complete agent. Add tools and skills only when the model needs them — too many tools can distract planning.

**Limits** — Up to 50 agents per user and 256 KB of configuration per agent.

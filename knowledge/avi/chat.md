---
id: chat
title: Chat
route: "/chat"
group: Getting started
audience: public
source: docs
tags: [docs, start]
---

## Chat

Run agents and workflows conversationally, with live plans, tool calls, sources and answer modes.

Chat is the end-user surface. Pick a target (any saved agent or workflow), configure the run, and ask a question. The run streams a plan, its steps and tool calls, then the final answer. Agents resume per conversation, so follow-up questions keep context.

The composer is at the bottom of the chat column. It holds the target picker, the model picker, Answer mode and Reasoning effort, a Run settings dialog, and the Auto-approve toggle. An agent chat also shows a ring context meter once a conversation grows large.

## Chat

1. Open the target picker and choose an agent (or a workflow, grouped under Workflows). A workflow target shows only the picker and applies Answer mode and Reasoning effort to the host agent.
2. Optionally open Run settings. For an agent this selects knowledge bases, skills, MCP servers and storage files for this run (seeded from the saved config). For a workflow it selects which of your agents run this time.
3. Choose a model. Platform models are listed, plus any provider keys you stored in the Vault; selecting a Vault key encodes it as vault:<id>:<model>.
4. Pick Answer mode (Summarize, Normal or Detailed) and Reasoning effort for this run. These override the agent defaults without changing the saved agent.
5. Toggle Auto-approve off if you want the agent to ask you a question mid-run, or on to let it assume the best option and state it.

## Chat

6. Type a question — or tap a starter question on the welcome screen — and send. Watch the run card move through Planning, sub-query groups and numbered todo steps; each tool call shows its name, arguments, response and citation sources.
7. Read the final answer, rendered in the agent output format (markdown, pretty JSON or plain text). Below it, the Source carousel lists every source by number; inline [n] badges scroll the matching card into view.
8. Rate the run with the thumbs under the answer, or open View trace for the full run trace — every stage with its input, output and metadata.

## Chat

**Human in the loop** — With Auto-approve off, the agent can pause and ask a question in a card with option buttons and a custom answer. Submitting resumes the exact same run — the paused turn is replaced, so there is no duplicate.

**Context limits** — Once a conversation fills the model window (the meter turns full), the composer stops accepting messages. Start a new chat to continue with a clean context.

- The left sidebar lists your conversations (closable with the panel button). New chat resets to a draft until you send the first message.
- A conversation has a readable global id in the URL: /chat/conversation/<number>?agent=<name>.
- Only the final answer is shown; streamed narration before a tool call is dropped. All sources live in the carousel below the answer.

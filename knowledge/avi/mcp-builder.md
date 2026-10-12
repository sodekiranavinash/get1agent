---
id: mcp-builder
title: MCP Builder
route: "/mcp-builder"
group: Build
audience: user
source: docs
tags: [docs, build]
---

## MCP Builder

Build, generate, diff and test your own Python MCP tools in a chat-to-code workspace.

The MCP Builder is where you create custom tools. It is a chat-to-code workspace, not a form: a build chat on the left and a CodeMirror code panel on the right. The server name, tool name and description are editable fields across the top. Save tool is the page’s single primary action and Test sits beside it.

A tool’s source defines a run(args) function that takes one dictionary and returns a JSON-serializable value. The input and output schemas are JSON Schema. Your code runs in a sandbox, never in the browser.

```python
def run(args):
    # args matches the tool input schema
    return {"result": args}
```

## MCP Builder

1. Open MCP Builder and give the server and tool a name and a one-sentence description the agent will read to decide when to call it.
2. Describe what the tool should do in the build chat. The generator replies with a proposal.
3. Review the change card (+N/-M) — it opens a VS Code-style unified diff between the accepted code and the proposal. Use the single global Accept or Reject pair, or Restore checkpoint to revert to the code before that change.
4. Use Undo and Redo in the editor header over the accepted code, and switch between the Code and Schema tabs to edit the JSON schemas directly.
5. Click Test, fill in the argument form built from the input schema, and run the tool to see its result. Test is always available.
6. Press Save tool. The source is stored as a custom server and appears in the MCP Tools list and in the Agent builder’s tools card.

## MCP Builder

- Limits: 20 servers per user, 20 tools per server, 64 KB of source per tool.
- Build-chat history persists in Playground sessions (100 sessions per user, 200 messages per session).
- A custom server attaches to an agent as a servers[] entry with source “custom” and the server slug as its id.
- Changing a tool’s code does not redeploy anything — it can be tested from the inspector, and the sandbox runs the current source.

**Sandboxed and offline** — Custom tools run isolated, so they cannot fetch the web or reach cloud SDKs. If a tool needs remote content, have the agent call HTTP Fetch first, then read the saved file and pass its content to your tool as an argument.

---
id: mcp-tools
title: MCP Tools
route: "/tools"
group: Resources
audience: user
source: docs
tags: [docs, resources]
---

## MCP Tools

Built-in tools plus remote MCP server connections over OAuth or an API key.

The MCP Tools page lists the built-in tools that need no setup, then your connected remote servers. Built-ins are Web Search (real-time web results with citations), Code Interpreter (Python in a sandbox, no internet), HTTP Fetch (call a public URL and return the response inline), and Storage (list, read, write and delete the user’s files).

Remote (Streamable HTTP) MCP servers are connected from the catalog, which has three tabs: All, One Agent Marketplace and MCP Registry. Auth filters let you show only OAuth or no-sign-in servers.

## MCP Tools

1. To connect a server, find it in the catalog and start the connection. For an OAuth server a popup walks you through authorization; the callback completes the connection.
2. For an API-key server, paste the key when prompted. You may reference a Vault secret instead of a literal token.
3. Once connected, use the connection card to enable or disable it, manage and toggle its individual tools, refresh its cached schemas, reconnect if needed, or disconnect.
4. If a connection shows Reconnect, its token was revoked — start the authorization again.
5. Use the connected servers in an agent by selecting them on the MCP servers & tools card in the Agent builder.

## MCP Tools

- Statuses: Setup, Connected, Reconnect and Error. Disabled connections are dimmed and skipped at run time.
- Tool schemas are cached; Refresh re-reads them from the server.
- Only remote HTTP servers are listed — stateful stdio servers are not supported.

**Prefer Vault references** — Store an API key in the Vault and reference it as a placeholder so rotating the value is picked up live without editing the connection.

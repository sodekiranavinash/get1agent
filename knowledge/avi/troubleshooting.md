---
id: troubleshooting
title: Troubleshooting
route: "/docs#troubleshooting"
group: Help
audience: user
source: docs
tags: [docs, help]
---

## Troubleshooting

What to check when something does not work as expected.

Most issues fall into a few categories. Work through the matching entry below before contacting support, and include the affected resource id and the time it happened.

## Troubleshooting

- “Agent runs are not configured” warning in Chat: the run endpoint is not set for this environment. In a managed workspace this is an operator setting; report it rather than retrying.
- A document stays Processing: ingestion retries automatically and a watchdog fails anything stuck past the threshold. Re-upload the document and note its id.
- Search returns nothing: confirm the knowledge base is Ready and attached to the agent, and that your query is not restricted by tags that no document carries.
- A remote MCP connection shows Reconnect: the token was revoked or expired. Run Reconnect from the connection card.

## Troubleshooting

- A custom tool times out or errors: check the Test dialog first. Tools run sandboxed with public HTTP(S) access (up to 25 network calls and ~90s per run, 180s while testing); heavy ML libraries and private hosts are blocked. Use Storage for files and Code Interpreter for heavy calculations.
- The Chat composer stops accepting messages and the context meter is full: start a new chat to continue with a fresh context.
- Credits are exhausted: add a provider key in the Vault to run on your own account, or ask an admin for more credits.
- A workflow run produces no visible answer: open View final answer to read the persisted conversation in Chat. Intermediate agent text is intentionally not streamed.

## Troubleshooting

**Check status first** — Before filing a report, open the status page from Support to confirm there is no active incident.

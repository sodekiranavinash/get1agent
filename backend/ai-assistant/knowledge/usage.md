---
id: usage
title: Usage
route: "/usage"
group: Manage
audience: user
source: docs
tags: [docs, manage]
---

## Usage

Live workspace usage: AI credits, 30-day token and cost analytics, provider keys and resource limits.

Usage has two tabs. Overview covers the workspace budget and analytics; Resources covers every per-user limit and the model rate table. Every number is server-derived — nothing is estimated in the browser.

## Usage

- AI credits card: how many credits of your grant you have spent, how many remain and the equivalent dollar amount. Runs on your own Vault provider keys are not counted.
- KPI row (30 days): Runs, Tokens, Cost and p95 latency, with trend sparklines.
- Provider keys: your Vault secrets with previews, default models, test status and usage; Manage opens the Vault.
- Usage by model: cost and token share per model for the last 30 days.
- Resources: knowledge bases, storage, stored files, agents, workflows, skills, MCP connections and Vault secrets against their limits.
- Model rates: the input and output USD-per-1M-token rates used to price platform usage.

## Usage

1. Open the Overview tab to check your remaining credits before a large batch of runs.
2. If credits are low, add a provider key in the Vault to keep running on your own account, or ask an admin to grant more.
3. Switch to Resources to see which limit is closest to being reached; near-limit bars turn amber.

**Credits vs provider keys** — Platform models draw down your AI credits. A run that uses your own Vault provider key is billed to that provider and is always allowed, even when credits are exhausted.

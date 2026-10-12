---
id: agents-library
title: Agents library
route: "/agent-store"
group: Marketplace
audience: user
source: docs
tags: [docs, marketplace]
---

## Agents library

Browse your agents and published agents, then install a copy into your workspace.

The Agents page shows both your own agents and agents other people have published. An agent appears as a card with its status, model, knowledge/skill/server counts and install count. Public agents you do not own offer Add to workspace; your own offers Edit.

1. Use the All, My agents and Public tabs to filter the grid.
2. Click New agent to create one, or Edit on your own agent to open it in the builder.
3. On a public agent, click Add to workspace. A copy is created in your workspace and opens in the builder.
4. To share your own, open it in the builder and publish it. Publishing is ungated and flips visibility to public.

## Agents library

- Installing a published agent clones it with source “library” and a forkedFrom reference.
- Owner-scoped references (knowledge bases, skills and remote servers) are stripped on install because they are not shareable.
- Published copies already installed by others are not affected if you later unpublish or delete yours.

**Where publishing lives** — You publish and unpublish from the Agent builder header — there is no publish action in the library itself.

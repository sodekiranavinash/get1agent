---
id: platform-limits
title: Platform limits
route: "/usage"
group: Manage
audience: user
source: code
tags: [limits, quota, maximum, how many, usage, billing]
questions:
  - "How many knowledge bases can I create?"
  - "What is the maximum file size?"
  - "How many agents am I allowed?"
---

## Platform limits

These are the limits the product enforces. They are generated from the
constants in the code, so they are exact — and a per-account override can
raise some of them, which is why the **Usage** page shows the numbers that
actually apply to your account.

## Platform limits > Knowledge bases

- **Knowledge bases per user**: 10
- **Files per knowledge base**: 25
- **Files per user**: 250
- **Size per uploaded file**: 10 MB
- **Knowledge storage per user**: 100 MB

## Platform limits > Agents

- **Agents per user**: 50
- **Agent configuration size**: 256 KB
- **Starter questions per agent input**: 8

## Platform limits > Workflows

- **Workflows per user**: 50
- **Agents per workflow**: 10
- **Nodes per workflow**: 100
- **Edges per workflow**: 300

## Platform limits > Vault

- **Secrets per user**: 100

## Platform limits > Guardrails

- **Guardrails per user**: 20

## Platform limits > Tags

- **Tags per document**: 10

## Platform limits > Avi

- **Guest questions per IP per hour**: 6
- **Guest questions per IP per day**: 20
- **Signed-in questions per hour**: 120
- **Signed-in questions per day**: 1000
- **Agent steps per Avi answer**: 6
- **Characters per Avi question**: 2000

To see your own effective limits, open the Usage page at `/usage`.

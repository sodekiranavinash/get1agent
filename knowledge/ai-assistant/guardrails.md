---
id: guardrails
title: Guardrails
route: "/guardrails"
group: Manage
audience: user
source: docs
tags: [docs, manage]
---

## Guardrails

Apply Amazon Bedrock Guardrails to your runs — content filters, denied topics and PII handling.

Create and manage your own Amazon Bedrock Guardrails from the Guardrails page, then attach one to any agent or workflow. A guardrail bundles content filters, denied topics, word filters, sensitive-information (PII) handling and contextual-grounding checks. A guardrail is set on the workspace as the default, and each agent or workflow can pick its own or opt out entirely. When a guardrail applies, every model call is screened: harmful content, denied topics and sensitive information are filtered before the model sees the prompt or the answer reaches the user.

## Guardrails

- Create: name the guardrail and choose its policy — content filters per category and strength, denied topics, profanity and custom words, PII entities and custom regex patterns, and grounding/relevance thresholds.
- Workspace guardrail: your default. Every agent and workflow run is screened with it unless that agent or workflow picks its own. Choose “None” to disable workspace screening.
- Per agent / workflow: in the builder, toggle the guardrail and pick one of your guardrails from the dropdown. Turning it off opts that agent or workflow out.
- Test: run a piece of text through a guardrail and see whether it intervenes, with the filtered output.

**Guardrails vs Policy** — Guardrails screen content. AgentCore Policy is separate and deterministic: it decides which tools an agent may call, and it runs on every tool call.

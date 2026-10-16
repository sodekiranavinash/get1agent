---
id: playground
title: Playground
route: "/playground"
group: Labs
audience: user
source: docs
tags: [docs, labs]
---

## Playground

Replay a real LLM call, edit the prompt, A/B two models and judge the result.

The Playground replays a generation from a trace. It is opened from a trace row’s Replay action, which loads that trace’s model calls. The original messages and model are lifted into an editable prompt so you can iterate without changing the agent.

## Playground

1. On Traces, click Replay on a row to open the Playground with that trace.
2. Pick which LLM call to work with from the list on the left.
3. Edit the prompt: change each message’s role, edit its content, add or remove messages. Content may contain {{variable}} placeholders — a variables panel appears and substitutes values before running.
4. Choose a model, optionally a second model for an A/B comparison, and set temperature and max tokens.
5. Click Run. The Outputs panel shows the original trace output beside each replay (and side by side when comparing two models), with latency and token counts.
6. Click Judge to score the replay. Supply an optional reference answer to get a correctness score; relevance and faithfulness scores are always returned.
7. Optionally name a dataset and click Save case to turn the last user message and the replay output into a dataset case.

## Playground

- The variables panel is frontend-only — substitution happens before the call is made.
- Models are limited to the curated Amazon Bedrock set.
- Saved cases are created on demand in the named dataset and can be used in Evaluations.

**Tight iteration loop** — Replay, adjust one thing, judge, and save the good version as a dataset case — that is the fastest way to improve a prompt that is feeding an evaluation.

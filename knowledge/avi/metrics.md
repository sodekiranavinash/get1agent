---
id: metrics
title: Metrics
route: "/metrics"
group: Labs
audience: user
source: docs
tags: [docs, labs]
---

## Metrics

Seven-day run volume, latency, cost, tokens and score averages for your workspace.

Metrics is a compact analytics view built from your traces. It answers “how much am I running, how fast and how expensive” without opening the full trace list.

- KPI row: Runs (traces), p95 latency, Cost over 7 days and total Tokens, each with a small trend sparkline where one is meaningful.
- Daily volume: a bar chart of runs per day for the last seven days.
- Daily p95 latency: a bar chart of the 95th-percentile latency per day.
- Scores: the average and count of every numeric score, such as run feedback or evaluation metrics.

**Needs traces** — If analytics are not configured for the environment, the page explains what is missing rather than showing fabricated numbers. Run an agent to generate the first trace.

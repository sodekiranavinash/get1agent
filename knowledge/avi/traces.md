---
id: traces
title: Traces
route: "/traces"
group: Labs
audience: user
source: docs
tags: [docs, labs]
---

## Traces

Every agent and workflow run, and the only place to add a run to a dataset or a review queue.

Traces is the audit view of your runs. Each row shows the trace name, when it ran, its latency, tags, the input question and three actions. It has two tabs: Traces and Review queues.

1. Open Traces after running an agent. Use the pagination controls to move through older runs.
2. Use Dataset on a row to add the run to a dataset (creating one on demand), producing a dataset item that keeps its source trace link.
3. Use Replay to open the trace in the Playground, where you can edit and re-run one of its model calls.
4. Use Queue to add the run to a review queue; choose or create the score configs the queue uses.
5. Switch to the Review queues tab and click Review on a queue to label pending items. Scores are written straight to the trace.

## Traces

- Curation is namespaced per user, so you only ever see your own datasets, queues and score configs.
- If trace storage is not configured the page shows a clear empty state instead of failing.
- Adding the same trace to the same dataset upserts rather than duplicating.

**The only curation entry point** — Datasets and review queues can only be fed from the Traces page — there are no such actions on the chat, builder or evaluations screens.

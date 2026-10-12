---
id: evaluations
title: Evaluations
route: "/evaluations"
group: Labs
audience: user
source: docs
tags: [docs, labs]
---

## Evaluations

Run RAG offline evaluations against a golden dataset and compare runs metric by metric.

Evaluations measure quality against a golden dataset. A dataset is a list of cases; each case has a question, an optional expected answer and optional expected sources. A run evaluates cases and scores retrieval and generation separately.

A run can use one of two tasks. The RAG task calls the real knowledge search and a controlled generator, then scores the retrieved contexts and the answer. The agent task re-runs a saved agent end to end and scores the answer and its tool trajectory.

## Evaluations

1. Open the Datasets tab and click New dataset. Add cases by hand or from a trace; a case can carry expected sources and an expected answer.
2. Open a dataset to see its cases and the runs that used it. Use Add cases to append more.
3. Click New evaluation (or Run on a dataset) and choose the dataset, the task (RAG or agent) and the knowledge bases or agents to use.
4. Start the run. It runs in the background; the page polls until it completes. A run stops before its time budget and marks any remaining cases skipped.
5. Open the finished run to see aggregate metrics and per-case detail, including the retrieved contexts, the generated answer and the judge’s reasoning.
6. Use the Compare tab to line up two runs and compare their metrics.

## Evaluations

- Retrieval metrics (when expected sources exist): context recall, context precision, hit rate and MRR.
- Generation metrics: faithfulness, context relevance, answer relevance and answer correctness (when an expected answer exists).
- Agent-task runs additionally report tool precision, tool recall, tool F1 and the number of tool calls when expected tools are declared.
- Ground truth is optional per case — a metric lights up only when its inputs are present.
- Limits: 50 datasets, 200 cases per dataset and 20 cases per run.

**Explainable scores** — The per-case artifact keeps the unsupported claims and passage labels behind each score, so you can see why faithfulness or context relevance scored the way it did.

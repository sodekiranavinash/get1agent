"""Evaluation runner: retrieve -> generate -> judge -> persist.

Datasets live in the AWS-native Lab store; each case is a store item. This worker
runs the *real* retrieval path (knowledge-mcp) and a controlled generator, then
scores retrieval and generation separately. Every case is ingested as a real
per-case result with its metric scores,
while the run/result bookkeeping the UI reads stays in DynamoDB + S3 so the UI
never depends on external read latency.
"""

from __future__ import annotations

import sys
import time
import traceback
from decimal import Decimal
from typing import Any

from core.mcp_client import McpClientError, call_tool
from core.storage import Storage
from data.client import now_iso
from data.repositories import evals as evals_repo
from retrieval import layout

from . import agent_client, config, judge, store
from . import metrics as metrics_lib

SEARCH_TOOL = "search-user-knowledge-bases"

CASE_OK = evals_repo.CASE_OK
CASE_ERROR = evals_repo.CASE_ERROR
CASE_SKIPPED = evals_repo.CASE_SKIPPED


class EvalError(Exception):
    """A case could not be evaluated."""


def _jsonable(value: Any) -> Any:
    """Convert DynamoDB ``Decimal`` values to plain int/float for JSON/S3."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _as_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value in (None, ""):
        return ""
    if isinstance(value, (dict, list)):
        try:
            import json

            return json.dumps(value)
        except (TypeError, ValueError):
            return str(value)
    return str(value)


def _tool_payload(response: dict[str, Any]) -> dict[str, Any]:
    """Unwrap the MCP JSON-RPC response to the tool's JSON object."""
    if not isinstance(response, dict):
        raise EvalError("Retrieval returned an invalid response")
    if response.get("error"):
        message = (
            response["error"].get("message")
            if isinstance(response["error"], dict)
            else ""
        )
        raise EvalError(f"Retrieval failed: {message or 'unknown error'}")
    result = response.get("result") or {}
    for part in result.get("content") or []:
        if isinstance(part, dict) and part.get("type") == "text":
            import json

            try:
                parsed = json.loads(part.get("text") or "{}")
            except ValueError as exc:
                raise EvalError("Retrieval returned invalid JSON") from exc
            if isinstance(parsed, dict):
                if parsed.get("error"):
                    detail = parsed["error"]
                    message = (
                        detail.get("message") if isinstance(detail, dict) else str(detail)
                    )
                    raise EvalError(f"Retrieval failed: {message}")
                return parsed
    raise EvalError("Retrieval returned no content")


def retrieve(
    user_id: str, query: str, knowledge_base_names: list[str], *, rerank: bool
) -> dict[str, Any]:
    function = config.knowledge_function()
    if not function:
        raise EvalError("Knowledge retrieval is not configured")
    try:
        _, response = call_tool(
            function,
            user_id,
            SEARCH_TOOL,
            {
                "query": query,
                "knowledgeBaseNames": knowledge_base_names,
                "rerank": bool(rerank),
            },
        )
    except McpClientError as exc:
        raise EvalError(f"Retrieval failed: {exc}") from exc
    return _tool_payload(response)


def _contexts_from_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    contexts: list[dict[str, Any]] = []
    total = 0
    for chunk in chunks:
        text = str(chunk.get("content") or chunk.get("matchedContent") or "").strip()
        if not text:
            continue
        text = text[: config.MAX_CONTEXT_PASSAGE_CHARS]
        if total + len(text) > config.MAX_CONTEXT_CHARS:
            break
        total += len(text)
        contexts.append(
            {
                "documentId": chunk.get("documentId"),
                "page": chunk.get("page"),
                "fileName": chunk.get("fileName"),
                "text": text,
            }
        )
    return contexts


def case_from_item(item: dict[str, Any]) -> dict[str, Any]:
    """Map a Lab-store dataset item to the runner's case shape."""
    source_input = item.get("input")
    query = ""
    if isinstance(source_input, dict):
        query = str(
            source_input.get("question")
            or source_input.get("query")
            or source_input.get("input")
            or ""
        )
    elif isinstance(source_input, str):
        query = source_input
    metadata = item.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    expected_sources = metadata.get("expectedSources")
    if not isinstance(expected_sources, list):
        expected_sources = []
    return {
        "caseId": str(item.get("id") or ""),
        "query": query,
        "expectedOutput": _as_text(item.get("expectedOutput")),
        "expectedSources": [
            source for source in expected_sources if isinstance(source, dict)
        ],
        "metadata": metadata,
    }


def evaluate_case(
    *,
    user_id: str,
    case: dict[str, Any],
    run_config: dict[str, Any],
    knowledge_base_names: list[str],
    storage: Storage,
    artifact_key: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run one case and return ``(artifact, result)``."""
    case_id = str(case.get("caseId") or "")
    query = str(case.get("query") or "")
    expected_output = str(case.get("expectedOutput") or "").strip()
    expected_sources = case.get("expectedSources") or []
    mode = str(run_config.get("mode") or config.DEFAULT_MODE)
    task = str(run_config.get("task") or config.DEFAULT_TASK)
    rerank = bool(run_config.get("rerank"))

    metrics: dict[str, Any] = {}
    retrieval: dict[str, Any] = {}
    contexts: list[dict[str, Any]] = []
    answer = ""
    tools: list[str] = []
    quality_reasoning = ""
    relevance_reasoning = ""
    context_reasoning = ""
    correctness_reasoning = ""
    faithfulness_claims: list[dict[str, Any]] = []
    passages: list[dict[str, Any]] = []
    status = CASE_OK
    error = ""

    started = time.perf_counter()
    try:
        if task == config.TASK_AGENT:
            if not config.enabled():
                raise EvalError("The evaluation model gateway is not configured")
            agent_result = agent_client.run_agent(
                user_id=user_id,
                agent_name=str(run_config.get("agentId") or ""),
                question=query,
            )
            answer = str(agent_result.get("answer") or "")
            tools = [str(name) for name in agent_result.get("tools") or []]
            retrieval = {"tools": tools, "sources": agent_result.get("sources") or []}
            expected_tools = (case.get("metadata") or {}).get("expectedTools")
            metrics.update(metrics_lib.trajectory_metrics(tools, expected_tools))
            relevance = judge.judge_relevance(query, answer)
            metrics["answer_relevance"] = relevance["answer_relevance"]
            quality_reasoning = relevance.get("reasoning") or ""
            if expected_output:
                correctness = judge.judge_correctness(query, answer, expected_output)
                metrics[config.CORRECTNESS_METRIC] = correctness["answer_correctness"]
                correctness_reasoning = correctness.get("reasoning") or ""
        else:
            payload = retrieve(user_id, query, knowledge_base_names, rerank=rerank)
            chunks = payload.get("chunks") or []
            retrieval = {
                "chunks": chunks,
                "sources": payload.get("sources") or [],
                "meta": payload.get("meta") or {},
            }
            contexts = _contexts_from_chunks(chunks)
            metrics.update(metrics_lib.retrieval_metrics(chunks, expected_sources))

            if mode == config.MODE_RAG:
                if not config.enabled():
                    raise EvalError("The evaluation model gateway is not configured")
                answer = judge.generate_answer(query, contexts)
                faithfulness = judge.judge_faithfulness(query, answer, contexts)
                metrics["faithfulness"] = faithfulness["faithfulness"]
                faithfulness_claims = faithfulness.get("claims") or []
                quality_reasoning = faithfulness.get("reasoning") or ""

                relevance = judge.judge_relevance(query, answer)
                metrics["answer_relevance"] = relevance["answer_relevance"]
                relevance_reasoning = relevance.get("reasoning") or ""

                context_relevance = judge.judge_context_relevance(query, contexts)
                metrics["context_relevance"] = context_relevance["context_relevance"]
                passages = context_relevance.get("passages") or []
                context_reasoning = context_relevance.get("reasoning") or ""

                if expected_output:
                    correctness = judge.judge_correctness(query, answer, expected_output)
                    metrics[config.CORRECTNESS_METRIC] = correctness["answer_correctness"]
                    correctness_reasoning = correctness.get("reasoning") or ""
    except Exception as exc:  # noqa: BLE001 - a bad case must not stop the run
        status = CASE_ERROR
        error = str(exc)[:1000]

    latency_ms = int((time.perf_counter() - started) * 1000)
    timestamp = now_iso()
    artifact = {
        "caseId": case_id,
        "query": query,
        "expectedOutput": expected_output,
        "expectedSources": expected_sources,
        "metadata": case.get("metadata") or {},
        "status": status,
        "error": error,
        "mode": mode,
        "rerank": rerank,
        "knowledgeBaseNames": knowledge_base_names,
        "contexts": contexts,
        "retrieval": retrieval,
        "answer": answer,
        "task": task,
        "tools": tools,
        "metrics": metrics,
        "judge": {
            "reasoning": quality_reasoning,
            "relevanceReasoning": relevance_reasoning,
            "contextReasoning": context_reasoning,
            "correctnessReasoning": correctness_reasoning,
            "claims": faithfulness_claims,
            "passages": passages,
        },
        "latencyMs": latency_ms,
        "createdAt": timestamp,
    }
    try:
        storage.put_json(artifact_key, _jsonable(artifact))
    except Exception as exc:  # noqa: BLE001 - the metrics still matter
        print(f"eval artifact write failed: {exc!r}", file=sys.stderr)

    result = {
        "caseId": case_id,
        "query": query,
        "status": status,
        "metrics": metrics,
        "artifactKey": artifact_key,
        "error": error,
        "latencyMs": latency_ms,
        "retrievedCount": (
            len(tools)
            if task == config.TASK_AGENT
            else len(retrieval.get("chunks") or [])
        ),
    }
    return artifact, result


def run_evaluation(*, user_id: str, run_id: str) -> dict[str, Any]:
    """Evaluate a Lab-store dataset and persist each case result."""
    run = evals_repo.get_run(user_id, run_id)
    if run is None:
        return {"ok": False, "error": "Evaluation run not found"}

    dataset_name = str(run.get("datasetId") or "")
    full_name = store.full_name(user_id, dataset_name)
    knowledge_base_names = list(run.get("knowledgeBaseNames") or [])
    run_config = run.get("config") or {}

    evals_repo.update_run(
        user_id, run_id, status=evals_repo.RUN_RUNNING, startedAt=now_iso()
    )

    try:
        dataset = store.get_dataset(full_name)
    except store.StoreError as exc:
        evals_repo.update_run(
            user_id,
            run_id,
            status=evals_repo.RUN_FAILED,
            error=f"Dataset unavailable: {exc}",
            completedAt=now_iso(),
        )
        return {"ok": False, "error": str(exc)}

    try:
        items = store.list_dataset_items(full_name)
    except store.StoreError as exc:
        evals_repo.update_run(
            user_id,
            run_id,
            status=evals_repo.RUN_FAILED,
            error=f"Could not load dataset items: {exc}",
            completedAt=now_iso(),
        )
        return {"ok": False, "error": str(exc)}

    cases = [case_from_item(item) for item in items]
    dataset_id = str((dataset or {}).get("id") or full_name)
    experiment_name = f"{dataset_name} · {run_id[:8]}"
    evals_repo.update_run(user_id, run_id, caseCount=len(cases))

    storage = Storage()
    limit = config.max_cases_per_run()
    deadline = time.monotonic() + config.run_budget_seconds()

    metric_rows: list[dict[str, Any]] = []
    completed = 0
    failed = 0
    skipped = 0

    for index, case in enumerate(cases):
        case_id = str(case.get("caseId") or "")
        if index >= limit or time.monotonic() >= deadline:
            evals_repo.put_case_result(
                user_id,
                run_id,
                case_id,
                query=str(case.get("query") or ""),
                status=CASE_SKIPPED,
                metrics={},
                error="Not evaluated (run limit reached)",
            )
            skipped += 1
            continue

        artifact_key = layout.eval_case_key(user_id, run_id, case_id)
        artifact, result = evaluate_case(
            user_id=user_id,
            case=case,
            run_config=run_config,
            knowledge_base_names=knowledge_base_names,
            storage=storage,
            artifact_key=artifact_key,
        )
        evals_repo.put_case_result(
            user_id,
            run_id,
            case_id,
            query=result["query"],
            status=result["status"],
            metrics=result["metrics"],
            artifact_key=result["artifactKey"],
            error=result["error"],
            latency_ms=result["latencyMs"],
            retrieved_count=result["retrievedCount"],
        )
        if result["status"] == CASE_OK:
            completed += 1
            metric_rows.append(result["metrics"])
            store.emit_experiment_item(
                user_id=user_id,
                experiment_id=run_id,
                experiment_name=experiment_name,
                experiment_description=str(run_config.get("mode") or "rag"),
                dataset_id=dataset_id,
                item_id=case_id,
                item_input=case.get("query"),
                item_output=artifact.get("answer") or "",
                expected_output=case.get("expectedOutput") or None,
                metrics=result["metrics"],
                reasoning=(artifact.get("judge") or {}).get("reasoning") or "",
                metadata={"agent": "knowledge-rag", "mode": run_config.get("mode")},
            )
        else:
            failed += 1

    aggregate = metrics_lib.aggregate_metrics(metric_rows)
    evals_repo.update_run(
        user_id,
        run_id,
        status=evals_repo.RUN_COMPLETED,
        completedCount=completed,
        failedCount=failed,
        skippedCount=skipped,
        metrics=aggregate,
        completedAt=now_iso(),
    )
    return {"ok": True, "metrics": aggregate, "completed": completed, "failed": failed}

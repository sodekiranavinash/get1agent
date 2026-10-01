"""Evaluation lab: Langfuse-backed datasets + a background run scored offline."""

from __future__ import annotations

import json
import uuid

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/user-api/handler.py", "user_api_handler_evals")

SUB = "auth0|evaltest"


def _event(method: str, path: str, body=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "eval@example.com",
                        "https://get1agent.com/name": "Eval",
                    }
                }
            },
        },
        "headers": {"x-active-view": "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _call(method, path, body=None, expect=200):
    response = handler.lambda_handler(_event(method, path, body), None)
    assert response["statusCode"] == expect, (method, path, response["statusCode"], response["body"])
    return json.loads(response["body"])


class FakeLangfuse:
    """In-memory stand-in for the src.evals.langfuse module."""

    def __init__(self) -> None:
        self.datasets: dict[str, dict] = {}
        self.items: dict[str, dict] = {}
        self.runs: dict[str, list] = {}
        self.emitted: list[dict] = []
        self._seq = 0

    def _next(self) -> int:
        self._seq += 1
        return self._seq

    def configured(self) -> bool:
        return True

    def list_datasets(self) -> list[dict]:
        return list(self.datasets.values())

    def get_dataset(self, name: str) -> dict:
        from src.evals.langfuse import LangfuseError

        if name not in self.datasets:
            raise LangfuseError("not found")
        return self.datasets[name]

    def create_dataset(self, name: str, description: str = "") -> dict:
        item = {"id": str(uuid.uuid4()), "name": name, "description": description, "createdAt": "x", "itemCount": 0}
        self.datasets[name] = item
        return item

    def delete_dataset(self, name: str) -> None:
        from src.evals.langfuse import LangfuseError

        if name not in self.datasets:
            raise LangfuseError("not found")
        self.datasets.pop(name)

    def list_dataset_items(self, name: str) -> list[dict]:
        return [item for item in self.items.values() if item["_dataset"] == name]

    def create_dataset_item(
        self,
        *,
        dataset_name: str,
        input_value,
        expected_output=None,
        metadata=None,
        source_trace_id=None,
        item_id=None,
    ) -> dict:
        item = {
            "id": item_id or str(uuid.uuid4()),
            "_dataset": dataset_name,
            "input": input_value,
            "expectedOutput": expected_output,
            "metadata": metadata or {},
            "createdAt": "x",
        }
        self.items[item["id"]] = item
        return item

    def delete_dataset_item(self, item_id: str) -> None:
        self.items.pop(item_id, None)

    def list_dataset_runs(self, name: str) -> list:
        return self.runs.get(name, [])

    def emit_experiment_item(self, **kwargs) -> str:
        self.emitted.append(kwargs)
        return "trace"


def _patch_langfuse(monkeypatch, fake: FakeLangfuse) -> None:
    for name in (
        "configured",
        "list_datasets",
        "get_dataset",
        "create_dataset",
        "delete_dataset",
        "list_dataset_items",
        "create_dataset_item",
        "delete_dataset_item",
        "list_dataset_runs",
        "emit_experiment_item",
    ):
        monkeypatch.setattr(handler.evals_langfuse, name, getattr(fake, name))


def test_dataset_and_case_crud(monkeypatch):
    fake = FakeLangfuse()
    _patch_langfuse(monkeypatch, fake)

    created = _call("POST", "/v1/evals/datasets", {"name": "smoke", "description": "d"}, expect=201)
    assert created["dataset"]["name"] == "smoke"
    # Namespaced on the way into Langfuse.
    assert list(fake.datasets) == [f"u_{_uid()}/smoke"]

    _call("POST", "/v1/evals/datasets", {"name": "smoke"}, expect=409)

    added = _call(
        "POST",
        "/v1/evals/datasets/smoke/cases",
        {"cases": [{"query": "q1"}, {"query": "q2", "expectedSources": [{"documentId": "doc1", "page": 2}]}]},
        expect=201,
    )
    assert added["caseCount"] == 2

    detail = _call("GET", "/v1/evals/datasets/smoke")
    assert detail["dataset"]["caseCount"] == 2
    assert [case["query"] for case in detail["dataset"]["cases"]] == ["q1", "q2"]

    listed = _call("GET", "/v1/evals/datasets")
    assert [item["name"] for item in listed["datasets"]] == ["smoke"]

    case_id = detail["dataset"]["cases"][0]["caseId"]
    _call("DELETE", f"/v1/evals/datasets/smoke/cases/{case_id}")
    after = _call("GET", "/v1/evals/datasets/smoke")
    assert after["dataset"]["caseCount"] == 1

    _call("DELETE", "/v1/evals/datasets/smoke")
    assert _call("GET", "/v1/evals/datasets")["datasets"] == []


def test_eval_run_scores_and_ingests_experiment(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    fake = FakeLangfuse()
    _patch_langfuse(monkeypatch, fake)
    monkeypatch.setattr(handler.evals_config, "enabled", lambda: True)

    _call("POST", "/v1/evals/datasets", {"name": "rag"}, expect=201)
    _call(
        "POST",
        "/v1/evals/datasets/rag/cases",
        {
            "cases": [
                {
                    "query": "What is X?",
                    "expectedOutput": "Y",
                    "expectedSources": [{"documentId": "doc1", "page": 2}],
                }
            ]
        },
        expect=201,
    )

    jobs: list[dict] = []
    monkeypatch.setattr(handler, "_invoke_self_async", lambda payload: jobs.append(payload))
    run = _call(
        "POST",
        "/v1/evals/runs",
        {"datasetId": "rag", "knowledgeBaseNames": ["kb1"], "config": {"mode": "rag", "rerank": False}},
        expect=202,
    )["run"]
    assert jobs and jobs[0]["runId"] == run["runId"]

    from src.evals import runner

    monkeypatch.setattr(runner, "Storage", lambda: fake_storage)
    monkeypatch.setattr(runner.config, "enabled", lambda: True)
    monkeypatch.setattr(runner.config, "knowledge_function", lambda: "knowledge-mcp")
    monkeypatch.setattr(
        runner,
        "call_tool",
        lambda *args, **kwargs: (
            {},
            {
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(
                                {
                                    "chunks": [
                                        {
                                            "documentId": "doc1",
                                            "page": 2,
                                            "fileName": "f.pdf",
                                            "content": "X is Y.",
                                            "matchedContent": "Y",
                                        }
                                    ],
                                    "sources": [],
                                    "meta": {},
                                    "error": None,
                                }
                            ),
                        }
                    ]
                }
            },
        ),
    )
    monkeypatch.setattr(runner.judge, "generate_answer", lambda query, contexts: "Y")
    monkeypatch.setattr(
        runner.judge,
        "judge_faithfulness",
        lambda query, answer, contexts: {
            "faithfulness": 1.0,
            "claims": [{"text": "X is Y", "supported": True}],
            "reasoning": "grounded",
        },
    )
    monkeypatch.setattr(
        runner.judge,
        "judge_relevance",
        lambda query, answer: {"answer_relevance": 1.0, "reasoning": "on topic"},
    )
    monkeypatch.setattr(
        runner.judge,
        "judge_context_relevance",
        lambda query, contexts: {
            "context_relevance": 1.0,
            "passages": [{"index": 1, "relevant": True}],
            "reasoning": "relevant",
        },
    )
    monkeypatch.setattr(
        runner.judge,
        "judge_correctness",
        lambda query, answer, expected: {"answer_correctness": 1.0, "reasoning": "match"},
    )

    outcome = runner.run_evaluation(user_id=_uid(), run_id=run["runId"])
    assert outcome["ok"] is True

    detail = _call("GET", f"/v1/evals/runs/{run['runId']}")["run"]
    cases = _call("GET", f"/v1/evals/runs/{run['runId']}/cases")["cases"]
    assert detail["status"] == "completed", detail
    assert detail["completedCount"] == 1, cases
    metrics = detail["metrics"]
    assert metrics["faithfulness"] == 1.0
    assert metrics["answer_correctness"] == 1.0
    assert metrics["context_recall"] == 1.0

    assert len(fake.emitted) == 1
    emitted = fake.emitted[0]
    assert emitted["item_id"] == cases[0]["caseId"]
    assert emitted["metrics"]["faithfulness"] == 1.0

    case_id = cases[0]["caseId"]
    artifact = _call("GET", f"/v1/evals/runs/{run['runId']}/cases/{case_id}")["artifact"]
    assert artifact["answer"] == "Y"


def test_dataset_detail_shows_source_trace_and_runs(monkeypatch):
    fake = FakeLangfuse()
    _patch_langfuse(monkeypatch, fake)
    _call("POST", "/v1/evals/datasets", {"name": "traced"}, expect=201)

    uid = _uid()
    full = f"u_{uid}/traced"
    fake.items["item-1"] = {
        "id": "item-1",
        "_dataset": full,
        "input": {"question": "q"},
        "expectedOutput": "a",
        "metadata": {},
        "createdAt": "x",
        "sourceTraceId": "t1",
    }
    fake.runs[full] = [
        {
            "id": "run-1",
            "name": "exp-1",
            "description": "",
            "createdAt": "2026-09-27T00:00:00Z",
            "metadata": {},
        }
    ]

    detail = _call("GET", "/v1/evals/datasets/traced")["dataset"]
    assert detail["cases"][0]["sourceTraceId"] == "t1"

    runs = _call("GET", "/v1/evals/datasets/traced/runs")["runs"]
    assert runs[0]["name"] == "exp-1"


def test_eval_agent_task(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    fake = FakeLangfuse()
    _patch_langfuse(monkeypatch, fake)
    monkeypatch.setattr(handler.evals_config, "enabled", lambda: True)
    monkeypatch.setattr(handler.evals_config, "agent_run_function", lambda: "agent-run")
    monkeypatch.setattr(handler.evals_config, "service_client_id", lambda: "svc")
    monkeypatch.setattr(handler.evals_config, "service_client_secret", lambda: "secret")
    monkeypatch.setattr(handler.evals_config, "service_audience", lambda: "aud")

    _call("POST", "/v1/evals/datasets", {"name": "agent-set"}, expect=201)
    _call(
        "POST",
        "/v1/evals/datasets/agent-set/cases",
        {
            "cases": [
                {
                    "query": "Book a flight",
                    "expectedOutput": "Booked",
                    "metadata": {"expectedTools": ["search", "book"]},
                }
            ]
        },
        expect=201,
    )

    monkeypatch.setattr(handler, "_invoke_self_async", lambda payload: None)
    run = _call(
        "POST",
        "/v1/evals/runs",
        {
            "datasetId": "agent-set",
            "knowledgeBaseNames": [],
            "config": {"task": "agent", "agentId": "a-1", "mode": "rag"},
        },
        expect=202,
    )["run"]

    from src.evals import runner

    monkeypatch.setattr(runner, "Storage", lambda: fake_storage)
    monkeypatch.setattr(runner.config, "enabled", lambda: True)
    monkeypatch.setattr(
        runner.agent_client,
        "run_agent",
        lambda **kwargs: {"answer": "Booked", "tools": ["search", "book", "book"], "sources": []},
    )
    monkeypatch.setattr(
        runner.judge,
        "judge_relevance",
        lambda query, answer: {"answer_relevance": 1.0, "reasoning": "ok"},
    )
    monkeypatch.setattr(
        runner.judge,
        "judge_correctness",
        lambda query, answer, expected: {"answer_correctness": 1.0, "reasoning": "ok"},
    )

    outcome = runner.run_evaluation(user_id=_uid(), run_id=run["runId"])
    assert outcome["ok"] is True

    detail = _call("GET", f"/v1/evals/runs/{run['runId']}")["run"]
    metrics = detail["metrics"]
    assert metrics["answer_relevance"] == 1.0
    assert metrics["answer_correctness"] == 1.0
    assert metrics["tool_calls"] == 3.0
    assert metrics["tool_recall"] == 1.0
    assert round(metrics["tool_precision"], 4) == round(2 / 3, 4)
    assert fake.emitted and fake.emitted[0]["metrics"]["tool_calls"] == 3.0


def _uid() -> str:
    from data.repositories.users import get_user_by_sub

    return get_user_by_sub(SUB)["userId"]

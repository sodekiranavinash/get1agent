"""Evaluation lab (Langfuse-native) routes: traces, datasets, queues."""

from __future__ import annotations

import json

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/user-api/handler.py", "user_api_handler_lab")

SUB = "auth0|labtest"


def _event(method: str, path: str, body=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "lab@example.com",
                        "https://get1agent.com/name": "Lab",
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


def test_lab_not_configured(monkeypatch):
    monkeypatch.setattr(handler, "_langfuse_auth", lambda: None)
    traces = _call("GET", "/v1/lab/traces")
    assert traces == {"configured": False, "traces": []}
    assert _call("GET", "/v1/lab/datasets")["configured"] is False
    assert _call("GET", "/v1/lab/queues")["configured"] is False


def test_lab_traces_datasets_and_queues(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    monkeypatch.setattr(handler, "_langfuse_auth", lambda: ("https://lf.example", "tok"))

    calls: list[tuple] = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        from data.repositories.users import get_user_by_sub

        profile = get_user_by_sub(SUB)
        uid = profile["userId"] if profile else "unknown"
        if path.startswith("/v2/traces"):
            return {
                "data": [
                    {
                        "id": "t1",
                        "name": "support-agent",
                        "userId": uid,
                        "input": {"question": "How do refunds work?"},
                        "output": {"answer": "30 days"},
                        "tags": ["chat"],
                        "latency": 1.5,
                    },
                    {"id": "t2", "name": "eval:dataset:abc", "userId": uid},
                ],
                "meta": {"page": 1, "totalPages": 2, "totalItems": 3},
            }
        if method == "GET" and path.startswith("/datasets"):
            return {
                "data": [
                    {"id": "d1", "name": f"u_{uid}/refunds", "description": "d", "createdAt": "x"},
                    {"id": "d2", "name": "u_someoneelse/private"},
                ]
            }
        if method == "GET" and path.startswith("/annotation-queues"):
            return {"data": [{"id": "q1", "name": f"u_{uid}/review", "scoreConfigIds": []}]}
        if method == "GET" and path.startswith("/score-configs"):
            return {"data": [{"id": "s1", "name": f"u_{uid}/correct", "dataType": "BOOLEAN"}]}
        if method == "POST" and path == "/datasets":
            return {"id": "dnew", "name": payload["name"]}
        if method == "POST" and path == "/annotation-queues":
            return {"id": "qnew", "name": payload["name"]}
        if method == "POST" and path.startswith("/dataset-items"):
            return {"id": payload["id"]}
        if "/annotation-queues/" in path and path.endswith("/items"):
            return {"ok": True}
        return {}

    monkeypatch.setattr(handler, "_lab_request", fake_request)

    # Traces: the internal eval trace is hidden. This also creates the user.
    traces = _call("GET", "/v1/lab/traces")
    assert traces["configured"] is True
    assert [trace["id"] for trace in traces["traces"]] == ["t1"]
    assert traces["totalPages"] == 2

    from data.repositories.users import get_user_by_sub

    uid = get_user_by_sub(SUB)["userId"]

    # Datasets: only the caller's own, display name stripped.
    datasets = _call("GET", "/v1/lab/datasets")
    assert [d["name"] for d in datasets["datasets"]] == ["refunds"]

    created = _call("POST", "/v1/lab/datasets", {"name": "new-set"}, expect=201)
    assert created["dataset"]["name"] == "new-set"
    assert calls[-1][2]["name"] == f"u_{uid}/new-set"

    # Add trace to dataset: namespaced + sourceTraceId.
    _call(
        "POST",
        "/v1/lab/traces/t1/dataset",
        {"datasetName": "refunds", "expectedOutput": "30 days", "input": {"question": "q"}},
        expect=201,
    )
    method, path, payload = calls[-1]
    assert path == "/dataset-items"
    assert payload["datasetName"] == f"u_{uid}/refunds"
    assert payload["sourceTraceId"] == "t1"
    assert payload["expectedOutput"] == "30 days"
    assert payload["id"]

    # Queues: namespaced.
    queues = _call("GET", "/v1/lab/queues")
    assert [q["name"] for q in queues["queues"]] == ["review"]

    _call("POST", "/v1/lab/queues", {"name": "audit"}, expect=201)
    assert calls[-1][2]["name"] == f"u_{uid}/audit"

    # Add trace to an owned queue.
    _call("POST", "/v1/lab/traces/t1/queue", {"queueId": "q1"})
    method, path, payload = calls[-1]
    assert path == "/annotation-queues/q1/items"
    assert payload == {"objectId": "t1", "objectType": "TRACE"}

    # Adding to a queue the caller does not own is rejected.
    _call("POST", "/v1/lab/traces/t1/queue", {"queueId": "not-mine"}, expect=404)

    # Score configs are namespaced too.
    configs = _call("GET", "/v1/lab/score-configs")
    assert [c["name"] for c in configs["scoreConfigs"]] == ["correct"]


def test_lab_queue_review(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    monkeypatch.setattr(handler, "_langfuse_auth", lambda: ("https://lf.example", "tok"))

    calls: list[tuple] = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        from data.repositories.users import get_user_by_sub

        uid = (get_user_by_sub(SUB) or {}).get("userId", "u")
        if method == "GET" and path.startswith("/annotation-queues?"):
            return {"data": [{"id": "q1", "name": f"u_{uid}/review", "scoreConfigIds": ["sc1"]}]}
        if method == "GET" and path.startswith("/annotation-queues/q1/items?"):
            return {
                "data": [
                    {"id": "qi1", "objectId": "t1", "objectType": "TRACE", "status": "PENDING"}
                ]
            }
        if method == "GET" and path == "/annotation-queues/q1/items/qi1":
            return {"id": "qi1", "objectId": "t1", "status": "PENDING"}
        if method == "GET" and path == "/traces/t1":
            return {
                "id": "t1",
                "name": "agent",
                "input": {"question": "q"},
                "output": {"answer": "a"},
            }
        if method == "POST" and path == "/scores":
            return {"id": "s"}
        if method == "PATCH" and path == "/annotation-queues/q1/items/qi1":
            return {"ok": True}
        return {}

    monkeypatch.setattr(handler, "_lab_request", fake_request)

    items = _call("GET", "/v1/lab/queues/q1/items")
    assert items["items"][0]["objectId"] == "t1"

    trace = _call("GET", "/v1/lab/traces/t1")
    assert trace["trace"]["id"] == "t1"

    _call(
        "POST",
        "/v1/lab/queues/q1/items/qi1",
        {
            "scores": [
                {
                    "name": "answer_correct",
                    "configId": "sc1",
                    "stringValue": "correct",
                    "comment": "ok",
                }
            ],
            "complete": True,
        },
    )
    posted = [call for call in calls if call[0] == "POST" and call[1] == "/scores"]
    assert posted and posted[0][2]["traceId"] == "t1"
    assert posted[0][2]["stringValue"] == "correct"
    assert any(call[0] == "PATCH" for call in calls)

    # A queue the caller does not own is rejected.
    _call("GET", "/v1/lab/queues/nope/items", expect=404)


def test_lab_metrics(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    monkeypatch.setattr(handler, "_langfuse_auth", lambda: ("https://lf.example", "tok"))

    import json as _json
    import urllib.parse

    seen: list[dict] = []

    def fake_request(method, path, payload=None):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        spec = _json.loads(query.get("query", ["{}"])[0])
        seen.append(spec)
        if spec["view"] == "scores-numeric":
            return {"data": [{"name": "eval_faithfulness", "avg_value": 0.9, "count_count": 4}]}
        if spec.get("dimensions"):
            return {
                "data": [
                    {
                        "providedModelName": "gpt-4o-mini",
                        "count_count": 5,
                        "sum_totalCost": 0.04,
                        "sum_totalTokens": 1200,
                    }
                ]
            }
        if "timeDimension" in spec:
            return {
                "data": [
                    {"time_dimension": "2026-09-27T00:00:00Z", "count_count": 3, "p95_latency": 1200, "sum_totalCost": 0.02},
                    {"time_dimension": "2026-09-28T00:00:00Z", "count_count": 5, "p95_latency": 900, "sum_totalCost": 0.03},
                ]
            }
        measures = {item["measure"] for item in spec["metrics"]}
        if measures == {"totalTokens"}:
            return {"data": [{"sum_totalTokens": 1500}]}
        return {"data": [{"count_count": 8, "avg_latency": 700, "p95_latency": 1200, "sum_totalCost": 0.05}]}

    monkeypatch.setattr(handler, "_lab_request", fake_request)

    payload = _call("GET", "/v1/lab/metrics?days=7")
    assert payload["configured"] is True
    assert payload["totals"]["traces"] == 8
    assert payload["totals"]["p95Latency"] == 1200
    assert payload["totals"]["cost"] == 0.05
    assert payload["totals"]["tokens"] == 1500
    assert len(payload["series"]) == 2
    assert payload["series"][1]["count"] == 5
    assert payload["scores"] == [
        {"name": "eval_faithfulness", "avg": 0.9, "count": 4}
    ]
    assert payload["models"] == [
        {"model": "gpt-4o-mini", "count": 5, "cost": 0.04, "tokens": 1200}
    ]
    # Every query is scoped to the caller and the trace root.
    from data.repositories.users import get_user_by_sub

    uid = get_user_by_sub(SUB)["userId"]
    for spec in seen:
        assert {"column": "userId", "operator": "=", "value": uid, "type": "string"} in spec["filters"]


def test_lab_add_trace_creates_missing_dataset(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    monkeypatch.setattr(handler, "_langfuse_auth", lambda: ("https://lf.example", "tok"))

    calls: list[tuple] = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET" and path.startswith("/datasets/"):
            raise handler.ApiError(502, "Langfuse error (404): not found")
        if method == "POST" and path == "/datasets":
            return {"id": "d1", "name": payload["name"]}
        if method == "POST" and path == "/dataset-items":
            return {"id": payload["id"]}
        return {}

    monkeypatch.setattr(handler, "_lab_request", fake_request)
    _call(
        "POST",
        "/v1/lab/traces/tX/dataset",
        {"datasetName": "New Set", "input": {"question": "q"}},
        expect=201,
    )

    from data.repositories.users import get_user_by_sub

    uid = get_user_by_sub(SUB)["userId"]
    full = f"u_{uid}/new-set"
    assert ("POST", "/datasets", {"name": full, "description": ""}) in calls
    assert any(method == "POST" and path == "/dataset-items" for method, path, _ in calls)


def test_lab_playground_run(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"model": kwargs["model"], "output": "hi", "usage": {"total": 3}, "latencyMs": 5}

    monkeypatch.setattr(handler.evals_playground, "run_completion", fake_run)

    result = _call(
        "POST",
        "/v1/lab/playground/run",
        {"model": "glm-5.3-flash", "messages": [{"role": "user", "content": "q"}]},
    )
    assert result["results"][0]["output"] == "hi"
    assert captured["messages"][0]["content"] == "q"

    # A/B: two models in one request.
    ab = _call(
        "POST",
        "/v1/lab/playground/run",
        {
            "runs": [
                {"model": "glm-5.3-flash", "messages": [{"role": "user", "content": "q"}]},
                {"model": "kimi-k2.6", "messages": [{"role": "user", "content": "q"}]},
            ]
        },
    )
    assert [entry["model"] for entry in ab["results"]] == ["glm-5.3-flash", "kimi-k2.6"]

    # A model the playground does not offer is rejected before any call.
    _call("POST", "/v1/lab/playground/run", {"model": "nope", "messages": []}, expect=400)


def test_lab_playground_judge(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    monkeypatch.setattr(handler.evals_config, "enabled", lambda: True)
    monkeypatch.setattr(
        handler.evals_judge,
        "judge_relevance",
        lambda q, a: {"answer_relevance": 0.9, "reasoning": "on topic"},
    )
    monkeypatch.setattr(
        handler.evals_judge,
        "judge_correctness",
        lambda q, a, e: {"answer_correctness": 1.0, "reasoning": "match"},
    )
    payload = _call(
        "POST",
        "/v1/lab/playground/judge",
        {"query": "q", "answer": "a", "expectedOutput": "a"},
    )
    assert payload["metrics"]["answer_relevance"]["value"] == 0.9
    assert payload["metrics"]["answer_correctness"]["value"] == 1.0
    # query + answer are required.
    _call("POST", "/v1/lab/playground/judge", {"query": "", "answer": ""}, expect=400)

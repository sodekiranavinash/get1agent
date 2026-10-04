"""Agent-run trace store (Langfuse-style, AWS-native): index, tree and routes.

Covers the DynamoDB trace index + GSI listing, the runtime's trace builder, the
S3 observation tree read path, and the authenticated + public trace routes.
"""

from __future__ import annotations

import json
import sys

from support import REPO_ROOT, load_module, patch_lambda_storage

# The runtime package is not on the integration-test path by default.
sys.path.insert(0, str(REPO_ROOT / "backend" / "agents"))

handler = load_module("backend/services/apis/user-api/handler.py", "user_api_handler_traces")

SUB = "auth0|tracetest"


def _event(method: str, path: str, body=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "trace@example.com",
                        "https://get1agent.com/name": "Trace",
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


def _events() -> list[dict]:
    return [
        {"type": "run.started", "runId": "r1", "_at": 1000},
        {"type": "plan", "understanding": "Find X", "subQueries": [], "_at": 1010},
        {"type": "tool.start", "name": "search-user-knowledge-bases", "toolUseId": "t1", "input": {"query": "x"}, "_at": 1020},
        {"type": "tool.result", "toolUseId": "t1", "status": "success", "data": "ok", "_at": 1200},
        {"type": "text", "data": "The answer.", "_at": 1210},
        {"type": "run.completed", "usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120}, "_at": 1250},
    ]


def _build(trace_id: str = "t1", *, agent_id: str = "agent1"):
    from agentflow.traces import build_trace

    return build_trace(
        trace_id=trace_id,
        run_id="r1",
        user_id="u_owner",
        agent_id=agent_id,
        agent_name="scout",
        model="amazon.nova-2-lite-v1:0",
        provider=None,
        conversation_id="7",
        question="What is the answer?",
        answer="The answer.",
        status="completed",
        started_at="2026-10-03T10:00:00+00:00",
        ended_at="2026-10-03T10:00:01.250000+00:00",
        events=_events(),
        usage={"inputTokens": 100, "outputTokens": 20, "totalTokens": 120},
        tags=["agent", "scout"],
    )


def test_trace_builder_tree():
    trace = _build()
    assert trace["status"] == "ok"
    assert trace["latencyMs"] == 1250
    # root run span + planner + tool + answer generation
    assert trace["observationCount"] == 4
    by_name = {observation["name"]: observation for observation in trace["observations"]}
    root = by_name["scout"]
    planner = by_name["planner"]
    answer = by_name["answer"]
    tool = by_name["search-user-knowledge-bases"]
    assert root["type"] == "SPAN"
    assert planner["type"] == "GENERATION"
    assert answer["type"] == "GENERATION"
    assert tool["type"] == "TOOL"
    assert tool["durationMs"] == 180
    # Tools are the plan's steps: they nest under the planner, not the answer.
    assert tool["parentObservationId"] == planner["id"]
    assert planner["parentObservationId"] == root["id"]
    assert answer["parentObservationId"] == root["id"]


def test_trace_repo_roundtrip():
    from data.repositories import traces as repo

    repo.save_trace_index("u_abc", _build())
    items, cursor = repo.list_traces("u_abc", limit=10)
    assert [item["traceId"] for item in items] == ["t1"]
    assert cursor is None
    assert repo.get_trace_index("u_abc", "t1")["agentName"] == "scout"
    # Agent filter uses the overloaded GSI1 partition.
    only_agent, _ = repo.list_traces("u_abc", limit=10, agent_id="agent1")
    assert len(only_agent) == 1
    none, _ = repo.list_traces("u_abc", limit=10, agent_id="other")
    assert none == []
    assert repo.delete_traces("u_abc") == 1


def test_trace_store_and_routes(monkeypatch, fake_storage):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    # The Lab store reads the S3 tree through its own import of core.storage.
    monkeypatch.setattr("core.storage.Storage", lambda: fake_storage)

    # First call mints the user; then seed a real trace tree + index for them.
    _call("GET", "/v1/lab/traces")
    from data.repositories.users import get_user_by_sub

    uid = get_user_by_sub(SUB)["userId"]

    from agentflow.traces import build_trace, persist_trace
    from data.repositories import traces as repo
    from retrieval.layout import trace_key

    class _Config:
        s3_bucket = "get1agent-test-bucket"

    trace = build_trace(
        trace_id="t1",
        run_id="r1",
        user_id=uid,
        agent_id="agent1",
        agent_name="scout",
        model="amazon.nova-2-lite-v1:0",
        provider=None,
        conversation_id="7",
        question="What is the answer?",
        answer="The answer.",
        status="completed",
        started_at="2026-10-03T10:00:00+00:00",
        ended_at="2026-10-03T10:00:01.250000+00:00",
        events=_events(),
        usage={"inputTokens": 100, "outputTokens": 20, "totalTokens": 120},
        tags=["agent", "scout"],
    )
    # persist_trace writes through the runtime's own Storage binding.
    monkeypatch.setattr("agentflow.traces.Storage", lambda: fake_storage)
    persist_trace(_Config(), uid, trace)
    assert fake_storage.get_json(trace_key(uid, "t1"))["traceId"] == "t1"
    assert repo.get_trace_index(uid, "t1")["observationCount"] == 4

    # The list returns the rich summary (latency + tokens + cost).
    listing = _call("GET", "/v1/lab/traces")
    assert len(listing["traces"]) == 1
    summary = listing["traces"][0]
    assert summary["traceId"] == "t1"
    assert summary["latency"] == 1.25
    assert summary["usage"]["totalTokens"] == 120
    assert summary["costMicroUsd"] > 0
    assert listing["nextCursor"] is None

    # The detail returns the full observation tree.
    detail = _call("GET", "/v1/lab/traces/t1")
    assert detail["trace"]["observations"][0]["type"] == "SPAN"
    assert len(detail["trace"]["observations"]) == 4

    # The public signed link serves the same tree without auth.
    monkeypatch.setenv("TRACE_LINK_SECRET", "test-secret")
    token = handler._trace_token("t1", uid, "7")
    response = handler.lambda_handler(_event("GET", f"/v1/traces/{token}"), None)
    assert response["statusCode"] == 200, response["body"]
    public = json.loads(response["body"])
    assert public["trace"]["traceId"] == "t1"
    assert len(public["trace"]["observations"]) == 4

    # An expired/tampered token is rejected.
    assert handler.lambda_handler(_event("GET", "/v1/traces/bogus"), None)["statusCode"] == 410


def test_xray_spans_become_clean_observations():
    from core import xray

    span_tree = {
        "traceId": "x1",
        "durationMs": 900,
        "spans": [
            {
                "id": "root",
                "name": "agent:hello",
                "startTime": 1000.0,
                "endTime": 1000.9,
                "durationMs": 900,
                "status": "ok",
                "attributes": {
                    "get1agent.trace_name": "agent:hello",
                    "get1agent.input": "Hi",
                    "get1agent.output": "Hello!",
                    "get1agent.metadata": '{"agentId": "a1", "agentName": "hello"}',
                    "get1agent.session_id": "63",
                    "get1agent.user_id": "u_1",
                },
                "children": [
                    {
                        "id": "tool1",
                        "name": "execute_tool search-user-knowledge-bases",
                        "startTime": 1000.1,
                        "endTime": 1000.4,
                        "durationMs": 300,
                        "status": "ok",
                        "attributes": {"get1agent.trace_name": "search-user-knowledge-bases"},
                        "children": [],
                    }
                ],
            }
        ],
    }

    observations = xray.to_observations(span_tree)
    assert len(observations) == 2
    root = observations[0]
    assert root["type"] == "GENERATION"
    assert root["name"] == "agent:hello"
    assert root["input"] == "Hi"
    assert root["output"] == "Hello!"
    assert root["startTime"] == 1_000_000
    # The raw `get1agent.*` keys never survive: metadata is clean + human keys.
    assert "get1agent.trace_name" not in root["metadata"]
    assert root["metadata"]["agentName"] == "hello"
    assert root["metadata"]["session_id"] == "63"
    tool = observations[1]
    assert tool["type"] == "TOOL"
    assert tool["parentObservationId"] == "root"

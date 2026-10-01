"""Workflow route coverage: CRUD, verification, conversations, runs."""

from __future__ import annotations

import json

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/user-api/handler.py", "user_api_handler")

SUB = "auth0|workflowtest"


def _event(method: str, path: str, body=None, query=None) -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "wf@example.com",
                        "https://get1agent.com/name": "Wf",
                    }
                }
            },
        },
        "headers": {"x-active-view": "user"},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query:
        event["rawQueryString"] = "&".join(f"{k}={v}" for k, v in query.items())
    return event


def _call(method, path, body=None, query=None, expect=200):
    response = handler.lambda_handler(_event(method, path, body, query), None)
    assert response["statusCode"] == expect, (method, path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def _agent_payload(name: str = "researcher") -> dict:
    return {
        "name": name,
        "description": "Researches topics thoroughly.",
        "config": {
            "version": 2,
            "prompt": "You research topics and report concise findings.",
            "model": "mimo-v2.5",
            "reasoning": "medium",
            "outputFormat": "markdown",
            "input": {"query": "", "fileIds": []},
            "output": {"format": "markdown", "instructions": ""},
            "knowledgeBaseIds": [],
            "skillIds": [],
            "servers": [],
            "graph": {
                "nodes": [
                    {"id": "agent-1", "type": "agent", "position": {"x": 0, "y": 0}, "data": {}},
                    {"id": "input-1", "type": "input", "position": {"x": 0, "y": -1}, "data": {}},
                ],
                "edges": [{"id": "e1", "source": "input-1", "target": "agent-1"}],
            },
        },
    }


def _workflow_payload(agent_id: str, *, mode: str = "graph") -> dict:
    return {
        "name": "research-pipeline",
        "description": "Research then write.",
        "config": {
            "version": 1,
            "mode": mode,
            "input": {"query": "Summarize the topic"},
            "output": {"format": "markdown", "instructions": "Be concise."},
            "nodes": [
                {
                    "id": "input",
                    "type": "input",
                    "position": {"x": 360, "y": 210},
                    "data": {
                        "query": "Summarize the topic",
                        "prompt": "You coordinate a research team.",
                        "model": "mimo-v2.5",
                    },
                },
                {
                    "id": "researcher",
                    "type": "agent",
                    "position": {"x": 780, "y": 60},
                    "data": {"agentId": agent_id, "agentName": "researcher", "overrides": {"model": "kimi-k2.6"}},
                },
                {"id": "output", "type": "output", "position": {"x": 360, "y": 500}, "data": {"format": "markdown", "instructions": "Be concise."}},
                {
                    "id": "schedule",
                    "type": "schedule",
                    "position": {"x": 0, "y": 210},
                    "data": {"enabled": True, "cron": "0 9 * * 1-5", "timezone": "UTC"},
                },
            ],
            "edges": [
                {"id": "e-schedule", "source": "schedule", "target": "input"},
                {"id": "e1", "source": "input", "target": "researcher"},
                {"id": "e2", "source": "input", "target": "output"},
            ],
        },
    }


def test_workflow_crud_and_verify(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    agent = _call("POST", "/v1/agents", _agent_payload(), expect=201)

    created = _call(
        "POST", "/v1/workflows", _workflow_payload(agent["id"]), expect=201
    )
    assert created["mode"] == "graph"
    assert created["agentCount"] == 1
    assert created["status"] == "draft"

    # Names are unique per user.
    _call("POST", "/v1/workflows", _workflow_payload(agent["id"]), expect=409)

    listed = _call("GET", "/v1/workflows")
    assert [item["name"] for item in listed["workflows"]] == ["research-pipeline"]
    assert listed["usage"]["limits"]["workflows"] == 50

    detail = _call("GET", f"/v1/workflows/{created['id']}")
    assert detail["config"]["nodes"][1]["data"]["overrides"]["model"] == "kimi-k2.6"
    assert detail["config"]["schedule"] == {"enabled": True, "cron": "0 9 * * 1-5", "timezone": "UTC"}

    verified = _call("POST", f"/v1/workflows/{created['id']}/verify")
    assert verified["valid"] is True
    assert verified["workflow"]["status"] == "verified"

    # Swarm mode uses the same input/host card; the host is never a saved agent.
    swarm = _workflow_payload(agent["id"], mode="swarm")
    swarm["name"] = "swarm-pipeline"
    swarm_created = _call("POST", "/v1/workflows", swarm, expect=201)
    assert swarm_created["config"]["mode"] == "swarm"
    assert swarm_created["config"]["input"]["prompt"] == "You coordinate a research team."
    assert swarm_created["config"]["input"]["model"] == "mimo-v2.5"
    assert "hostNodeId" not in swarm_created["config"]

    updated = _call(
        "PUT",
        f"/v1/workflows/{created['id']}",
        {**_workflow_payload(agent["id"]), "description": "Updated description."},
    )
    assert updated["description"] == "Updated description."
    assert updated["status"] == "draft"

    _call("DELETE", f"/v1/workflows/{created['id']}")
    _call("GET", f"/v1/workflows/{created['id']}", expect=404)


def test_workflow_verify_flags_missing_agent(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    agent = _call("POST", "/v1/agents", _agent_payload(), expect=201)
    created = _call("POST", "/v1/workflows", _workflow_payload(agent["id"]), expect=201)

    # Delete the referenced agent, then verify: the workflow must report it.
    _call("DELETE", f"/v1/agents/{agent['id']}")
    result = _call("POST", f"/v1/workflows/{created['id']}/verify")
    assert result["valid"] is False
    assert any("no longer exists" in error for error in result["errors"])


def test_workflow_config_validation(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    agent = _call("POST", "/v1/agents", _agent_payload(), expect=201)

    no_agent = _workflow_payload(agent["id"])
    no_agent["config"]["nodes"] = [
        node for node in no_agent["config"]["nodes"] if node["type"] != "agent"
    ]
    no_agent["config"]["edges"] = []
    _call("POST", "/v1/workflows", no_agent, expect=400)

    bad_mode = _workflow_payload(agent["id"])
    bad_mode["config"]["mode"] = "turbo"
    _call("POST", "/v1/workflows", bad_mode, expect=400)

    bad_edge = _workflow_payload(agent["id"])
    bad_edge["config"]["edges"].append({"id": "e3", "source": "ghost", "target": "output"})
    _call("POST", "/v1/workflows", bad_edge, expect=400)

    # At most 10 agents per workflow.
    too_many = _workflow_payload(agent["id"])
    template = too_many["config"]["nodes"][1]
    agents = [
        {**template, "id": f"agent-{index}", "data": dict(template["data"])}
        for index in range(11)
    ]
    too_many["config"]["nodes"] = [
        too_many["config"]["nodes"][0],
        *agents,
        too_many["config"]["nodes"][2],
    ]
    too_many["config"]["edges"] = []
    _call("POST", "/v1/workflows", too_many, expect=400)


def test_workflow_conversation_and_runs(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    agent = _call("POST", "/v1/agents", _agent_payload(), expect=201)
    workflow = _call("POST", "/v1/workflows", _workflow_payload(agent["id"]), expect=201)

    conversation = _call(
        "POST",
        "/v1/conversations",
        {
            "agentId": workflow["id"],
            "targetType": "workflow",
            "kind": "chat",
            "title": "Run the pipeline",
        },
        expect=201,
    )
    assert conversation["targetType"] == "workflow"
    assert conversation["agentName"] == "research-pipeline"

    runs = _call("GET", f"/v1/workflows/{workflow['id']}/runs")
    assert [run["conversationId"] for run in runs["runs"]] == [conversation["conversationId"]]

    detail = _call("GET", f"/v1/conversations/{conversation['conversationId']}")
    assert detail["conversation"]["targetType"] == "workflow"

    # A workflow id is not a valid agent target.
    _call(
        "POST",
        "/v1/conversations",
        {"agentId": workflow["id"], "targetType": "agent", "kind": "chat"},
        expect=404,
    )

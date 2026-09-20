"""user-api route coverage: KBs/documents/tags/events/skills/settings."""

from __future__ import annotations

import json
import re

from support import load_module, patch_lambda_storage

handler = load_module("backend/services/user-api/handler.py", "user_api_handler")

SUB = "auth0|apitest"


def _event(method: str, path: str, body=None, query=None, view: str = "user") -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "api@example.com",
                        "https://get1agent.com/name": "Api",
                    }
                }
            },
        },
        "headers": {"x-active-view": view},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query:
        event["rawQueryString"] = "&".join(f"{k}={v}" for k, v in query.items())
    return event


def _call(method, path, body=None, query=None, expect=200, view="user"):
    response = handler.lambda_handler(_event(method, path, body, query, view), None)
    assert response["statusCode"] == expect, (method, path, response["statusCode"], response["body"])
    return json.loads(response["body"])


def test_settings(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    initial = _call("GET", "/v1/user/settings")
    # The public id is the short internal id, never the Auth0 sub.
    assert initial["id"] != SUB
    assert re.fullmatch(r"u_[0-9a-hjkmnp-tv-z]{16}", initial["id"])
    updated = _call(
        "POST",
        "/v1/user/settings",
        {"preferredTheme": "light", "timezone": "Europe/London", "fullName": "New Name"},
    )
    assert updated["preferredTheme"] == "light"
    assert updated["timezone"] == "Europe/London"
    assert updated["fullName"] == "New Name"


def test_knowledge_base_document_flow(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)

    user_id = _call("GET", "/v1/user/settings")["id"]

    created = _call("POST", "/v1/knowledge-bases", {"name": "api-kb", "description": "hi"}, expect=201)
    kb_id = created["id"]
    assert created["status"] == "ready" and created["fileCount"] == 0
    _call("POST", "/v1/knowledge-bases", {"name": "api-kb"}, expect=409)

    listed = _call("GET", "/v1/knowledge-bases")
    assert listed["knowledgeBases"][0]["name"] == "api-kb"
    assert listed["usage"]["limits"]["knowledgeBases"] == 10

    presign = _call(
        "POST",
        f"/v1/knowledge-bases/{kb_id}/documents/presign",
        {
            "fileName": "resume.pdf",
            "contentType": "application/pdf",
            "sizeBytes": 11,
            "tags": [{"name": "Resume", "description": "cv"}],
        },
        expect=201,
    )
    doc_id = presign["documentId"]
    key = presign["key"]
    assert key.startswith(f"raw/{user_id}/{kb_id}/{doc_id}/resume.pdf")
    fake_storage.put_bytes(key, b"hello world")
    completed = _call("POST", f"/v1/knowledge-bases/{kb_id}/documents/{doc_id}/complete")
    assert completed["status"] == "uploaded"
    assert completed["sizeBytes"] == 11
    assert completed["tags"][0]["name"] == "Resume"

    # The KB list reports the real file count.
    assert _call("GET", "/v1/knowledge-bases")["knowledgeBases"][0]["fileCount"] == 1

    # Same file name is rejected while a document exists.
    _call(
        "POST",
        f"/v1/knowledge-bases/{kb_id}/documents/presign",
        {"fileName": "resume.pdf", "contentType": "application/pdf", "sizeBytes": 11},
        expect=409,
    )

    inline = _call(
        "POST",
        f"/v1/knowledge-bases/{kb_id}/documents/inline",
        {"name": "notes", "content": "# Notes\n\nhello", "tags": [{"name": "Notes"}]},
        expect=201,
    )
    assert inline["fileName"] == "notes.md" and inline["status"] == "uploaded"
    assert _call("GET", "/v1/knowledge-bases")["knowledgeBases"][0]["fileCount"] == 2

    detail = _call("GET", f"/v1/knowledge-bases/{kb_id}")
    assert len(detail["documents"]) == 2
    assert detail["documents"][0]["downloadUrl"].startswith("https://s3.test/")

    events = _call("GET", "/v1/knowledge-bases/events", query={"limit": "10"})
    assert len(events["events"]) >= 2
    assert all("documentStatus" in item for item in events["events"])

    tag_list = _call("GET", "/v1/knowledge-bases/tags")
    assert {t["name"] for t in tag_list["tags"]} == {"Resume", "Notes"}

    _call("DELETE", f"/v1/knowledge-bases/{kb_id}/documents/{doc_id}")
    assert len(_call("GET", f"/v1/knowledge-bases/{kb_id}")["documents"]) == 1
    assert _call("GET", "/v1/knowledge-bases")["knowledgeBases"][0]["fileCount"] == 1
    # Removing a document must also clear its ingestion timeline.
    remaining = _call("GET", "/v1/knowledge-bases/events", query={"limit": "20"})["events"]
    assert all(event["fileName"] != "resume.pdf" for event in remaining), remaining

    _call("DELETE", f"/v1/knowledge-bases/{kb_id}")
    assert all(
        item["name"] != "api-kb" for item in _call("GET", "/v1/knowledge-bases")["knowledgeBases"]
    )


def test_agent_skills(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)

    skill = _call(
        "POST",
        "/v1/agent-skills",
        {"name": "pdf-processing", "description": "d", "content": "body", "allowedTools": ["web-search"]},
        expect=201,
    )
    assert skill["markdown"].startswith("---")
    skill_id = skill["id"]

    assert _call("GET", "/v1/agent-skills")["skills"][0]["name"] == "pdf-processing"
    servers = _call("GET", "/v1/agent-skills/mcp-servers")["servers"]
    assert servers[0]["id"] == "code-interpreter" and servers[0]["source"] == "builtin"

    parsed = _call(
        "POST",
        "/v1/agent-skills/parse",
        {"markdown": "---\nname: x\ndescription: y\n---\n\nbody"},
    )
    assert parsed["name"] == "x" and parsed["content"] == "body"

    _call(
        "PUT",
        f"/v1/agent-skills/{skill_id}",
        {"name": "pdf-parsing", "description": "d2", "content": "b2", "allowedTools": []},
    )
    assert _call("GET", f"/v1/agent-skills/{skill_id}")["name"] == "pdf-parsing"

    _call("DELETE", f"/v1/agent-skills/{skill_id}")
    assert _call("GET", "/v1/agent-skills")["skills"] == []


def test_agents(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)

    payload = {
        "name": "researcher",
        "description": "d",
        "config": {
            "version": 2,
            "prompt": "You are a careful research assistant.",
            "model": "deepseek-v4-flash-vision-exp",
            "reasoning": "medium",
            "outputFormat": "markdown",
            "input": {"query": "Summarise my resume.", "fileIds": []},
            "output": {"format": "markdown", "instructions": "Cite sources."},
            "defaultQuestions": ["Summarise my resume", "What are my strengths?"],
            "knowledgeBaseIds": [],
            "knowledgeRerank": True,
            "skillIds": [],
            "servers": [
                {"id": "web-search", "name": "Web Search", "source": "builtin", "tools": None}
            ],
            "memory": {"enabled": True},
            "schedule": {"enabled": False, "cron": "", "timezone": "UTC"},
            "graph": {"nodes": [{"id": "agent-1", "type": "agent"}], "edges": []},
        },
    }
    created = _call("POST", "/v1/agents", payload, expect=201)
    agent_id = created["id"]
    assert created["status"] == "draft" and created["model"] == "deepseek-v4-flash-vision-exp"
    assert created["config"]["knowledgeRerank"] is True
    assert created["config"]["version"] == 2
    assert created["config"]["memory"] == {"enabled": True}
    assert created["config"]["input"]["query"] == "Summarise my resume."
    assert created["config"]["output"]["instructions"] == "Cite sources."
    assert created["config"]["defaultQuestions"] == [
        "Summarise my resume",
        "What are my strengths?",
    ]
    assert created["defaultQuestions"] == created["config"]["defaultQuestions"]

    # A non-boolean rerank flag is rejected.
    _call(
        "POST",
        "/v1/agents",
        {
            **payload,
            "name": "bad-rerank",
            "config": {**payload["config"], "knowledgeRerank": "yes"},
        },
        expect=400,
    )

    # Publishing before a successful test is rejected.
    _call("POST", f"/v1/agents/{agent_id}/publish", {}, expect=409)

    verified = _call("POST", f"/v1/agents/{agent_id}/verify", {})
    assert verified["valid"] is True
    assert verified["agent"]["status"] == "verified"

    published = _call("POST", f"/v1/agents/{agent_id}/publish", {})
    assert published["visibility"] == "public"

    library = _call("GET", "/v1/agents/library")["agents"]
    assert library[0]["id"] == agent_id and library[0]["isMine"] is True

    # Re-saving without renaming is an update, not a name clash.
    same = _call("PUT", f"/v1/agents/{agent_id}", payload)
    assert same["id"] == agent_id and same["name"] == "researcher"

    # Editing invalidates the verification and unpublishes the agent.
    updated = _call("PUT", f"/v1/agents/{agent_id}", {**payload, "name": "researcher-2"})
    assert updated["status"] == "draft" and updated["visibility"] == "private"
    assert _call("GET", "/v1/agents/library")["agents"] == []

    # A missing prompt fails the dry-run.
    bad = {**payload, "name": "bad-agent", "config": {**payload["config"], "prompt": ""}}
    bad_created = _call("POST", "/v1/agents", bad, expect=201)
    result = _call("POST", f"/v1/agents/{bad_created['id']}/verify", {})
    assert result["valid"] is False and result["errors"]

    _call("DELETE", f"/v1/agents/{bad_created['id']}")
    _call("DELETE", f"/v1/agents/{agent_id}")
    assert _call("GET", "/v1/agents")["agents"] == []


def test_admin_view_is_rejected(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    response = handler.lambda_handler(_event("GET", "/v1/user/settings", view="admin"), None)
    assert response["statusCode"] == 403

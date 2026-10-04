"""user-api no longer serves the Platform status routes.

Platform status (Identity, Registry, Browser, Optimization, Bedrock levers) is
admin-only now; those routes live in the admin-console Lambda under
``/v1/admin/platform/*`` (see ``test_admin_console.py``). This file proves the
user-api no longer exposes them, and keeps the Guardrails route coverage that
shares this wiring.
"""

from __future__ import annotations

import json

from support import load_module, patch_lambda_storage

handler = load_module(
    "backend/services/apis/user-api/handler.py", "user_api_platform_handler"
)

SUB = "auth0|platformtest"

_PLATFORM_ENV = (
    "AGENT_WORKLOAD_IDENTITY_ARN",
    "AGENT_TOKEN_VAULT_ID",
    "AGENT_IDENTITY_PROVIDERS",
    "AGENT_IDENTITY_RETURN_URL",
    "AGENTCORE_REGISTRY_ARN",
    "AGENTCORE_REGISTRY_ID",
    "BROWSER_ID",
    "BROWSER_REGION",
    "BROWSER_ALLOWED_DOMAINS",
    "AGENT_OPTIMIZATION_ENABLED",
    "AGENT_OPTIMIZATION_INSIGHTS_ARN",
    "BEDROCK_PROMPT_ROUTER_ARN",
    "BEDROCK_SERVICE_TIER",
    "BEDROCK_PROFILE_CHAT",
    "BEDROCK_PROFILE_EVAL",
    "BEDROCK_PROFILE_INGESTION",
    "GUARDRAIL_ID",
)


def _clear(monkeypatch) -> None:
    for name in _PLATFORM_ENV:
        monkeypatch.delenv(name, raising=False)


def _event(method: str, path: str, body=None, query=None, view: str = "user") -> dict:
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": SUB,
                        "https://get1agent.com/email": "platform@example.com",
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
    assert response["statusCode"] == expect, (
        method,
        path,
        response["statusCode"],
        response["body"],
    )
    return json.loads(response["body"])


def test_platform_routes_are_admin_only(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _clear(monkeypatch)

    # Platform status is admin-console only now.
    _call("GET", "/v1/identity", expect=404)
    _call("POST", "/v1/identity/token", {"provider": "github"}, expect=404)
    _call("GET", "/v1/browser", expect=404)
    _call("POST", "/v1/browser/check", {"url": "https://example.com"}, expect=404)
    _call("POST", "/v1/browser/session", {"url": "https://example.com"}, expect=404)
    _call("GET", "/v1/registry", expect=404)
    _call("GET", "/v1/optimization", expect=404)
    _call("GET", "/v1/bedrock-features", expect=404)


def test_guardrails_status_and_config_route(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _clear(monkeypatch)

    status = _call("GET", "/v1/guardrails")
    assert status["configured"] is False
    assert status["guardrailId"] is None

    saved = _call("PUT", "/v1/guardrails/config", {"guardrailId": "gr-abc123"})
    assert saved["configured"] is True
    assert saved["guardrailId"] == "gr-abc123"

    assert _call("GET", "/v1/guardrails")["guardrailId"] == "gr-abc123"

    # Invalid ids are rejected before they are stored.
    _call("PUT", "/v1/guardrails/config", {"guardrailId": "bad id!"}, expect=400)

"""user-api platform routes: the user-facing Platform status.

Users can request their own AgentCore Identity token and open an AgentCore
Browser session. The admin-only platform services (Registry, Optimization and
the Bedrock cost/latency levers) now live in the admin-console Lambda — see
``test_admin_console.py``. Also covers the Guardrails routes that share the same
wiring.
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


# --- unconfigured (the default local / fresh-deploy state) -------------------


def test_user_platform_endpoints_wire_up_when_unconfigured(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _clear(monkeypatch)

    identity = _call("GET", "/v1/identity")
    assert identity["configured"] is False
    assert identity["providers"] == []
    assert isinstance(identity["region"], str) and identity["region"]

    browser = _call("GET", "/v1/browser")
    assert browser["configured"] is False
    assert browser["allowedDomains"] == []
    assert browser["sessionTimeout"] >= 60


def test_admin_only_platform_routes_moved_off_user_api(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _clear(monkeypatch)

    # Registry / Optimization / Bedrock levers are admin-console routes now.
    _call("GET", "/v1/registry", expect=404)
    _call("GET", "/v1/optimization", expect=404)
    _call("GET", "/v1/bedrock-features", expect=404)


def test_browser_check_gates_by_allowlist(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _clear(monkeypatch)
    monkeypatch.setenv("BROWSER_ID", "br-test")
    monkeypatch.setenv("BROWSER_ALLOWED_DOMAINS", "northwind.example")

    status = _call("GET", "/v1/browser")
    assert status["configured"] is True
    assert "northwind.example" in status["allowedDomains"]

    allowed = _call("POST", "/v1/browser/check", {"url": "https://docs.northwind.example/x"})
    assert allowed["allowed"] is True

    blocked = _call("POST", "/v1/browser/check", {"url": "https://evil.example/x"})
    assert blocked["allowed"] is False
    assert "evil.example" in blocked["reason"]

    # A disallowed URL never starts a session (gated before any AWS call).
    _call("POST", "/v1/browser/session", {"url": "https://evil.example"}, expect=403)
    # But an unconfigured browser is a clean 400.
    monkeypatch.delenv("BROWSER_ID")
    _call("POST", "/v1/browser/session", {"url": "https://northwind.example"}, expect=400)


# --- configured branches -----------------------------------------------------


def test_browser_session_lifecycle_when_configured(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _clear(monkeypatch)
    monkeypatch.setenv("BROWSER_ID", "br-test")
    monkeypatch.setenv("BROWSER_ALLOWED_DOMAINS", "northwind.example")

    import core.browser as browser

    class _FakeBrowserClient:
        def __init__(self):
            self.session_id = None

        def start(self, identifier, session_timeout_seconds):
            return {"sessionId": "sess-1"}

        def generate_ws_headers(self):
            return "wss://live.example", {"X-Token": "t"}

        def generate_live_view_url(self):
            return "https://live.example/sess-1"

        def stop(self):
            return True

    monkeypatch.setattr(browser, "_client", lambda: _FakeBrowserClient())

    session = _call("POST", "/v1/browser/session", {"url": "https://northwind.example"})
    assert session["sessionId"] == "sess-1"
    assert session["browserId"] == "br-test"
    assert session["liveViewUrl"] == "https://live.example/sess-1"

    closed = _call("POST", "/v1/browser/session/close", {"sessionId": "sess-1"})
    assert closed["stopped"] is True


def test_identity_status_when_configured(fake_storage, monkeypatch):
    patch_lambda_storage(monkeypatch, handler, fake_storage)
    _clear(monkeypatch)
    monkeypatch.setenv(
        "AGENT_WORKLOAD_IDENTITY_ARN",
        "arn:aws:bedrock-agentcore:ap-south-1:1:workload-identity/agent-1",
    )
    monkeypatch.setenv(
        "AGENT_IDENTITY_PROVIDERS",
        "arn:aws:bedrock-agentcore:ap-south-1:1:credential-provider/google-provider/abc,"
        "arn:aws:bedrock-agentcore:ap-south-1:1:credential-provider/github-provider/def",
    )

    identity = _call("GET", "/v1/identity")
    assert identity["configured"] is True
    assert len(identity["providers"]) == 2


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

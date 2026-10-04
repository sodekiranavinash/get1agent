"""admin-console platform routes.

The admin-only Platform status: AgentCore Identity, Registry, Browser,
Optimization and the Bedrock cost/latency levers, all under
``/v1/admin/platform/*`` and gated by the admin role + admin view.
"""

from __future__ import annotations

import json

from support import load_module

handler = load_module(
    "backend/services/admin/admin-console/handler.py", "admin_console_platform_handler"
)

ADMIN_SUB = "auth0|platform-admin"

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
    "BEDROCK_PROMPT_CACHE",
    "BEDROCK_PROMPT_CACHE_TTL",
    "BEDROCK_SERVICE_TIER",
    "BEDROCK_PROMPT_ROUTER_ARN",
    "BEDROCK_PROFILE_CHAT",
    "BEDROCK_PROFILE_EVAL",
    "BEDROCK_PROFILE_INGESTION",
)


def _clear(monkeypatch) -> None:
    for name in _PLATFORM_ENV:
        monkeypatch.delenv(name, raising=False)


def _event(
    method: str,
    path: str,
    body=None,
    query=None,
    admin: bool = True,
    view: str = "admin",
) -> dict:
    claims = {
        "sub": ADMIN_SUB,
        "https://get1agent.com/email": "admin@example.com",
    }
    if admin:
        claims["https://get1agent.com/isAdmin"] = True
    event = {
        "rawPath": path,
        "requestContext": {
            "http": {"method": method},
            "authorizer": {"jwt": {"claims": claims}},
        },
        "headers": {"x-active-view": view},
    }
    if body is not None:
        event["body"] = json.dumps(body)
    if query:
        event["rawQueryString"] = "&".join(f"{k}={v}" for k, v in query.items())
    return event


def _call(
    method,
    path,
    body=None,
    query=None,
    expect=200,
    admin=True,
    view="admin",
):
    response = handler.lambda_handler(
        _event(method, path, body, query, admin, view), None
    )
    assert response["statusCode"] == expect, (
        method,
        path,
        response["statusCode"],
        response["body"],
    )
    return json.loads(response["body"])


def test_platform_routes_require_admin(monkeypatch):
    _clear(monkeypatch)

    # A non-admin is rejected outright.
    _call("GET", "/v1/admin/platform/identity", expect=403, admin=False)
    # An admin in the user view is rejected (admin view required).
    _call("GET", "/v1/admin/platform/identity", expect=403, view="user")


def test_platform_status_when_unconfigured(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("BEDROCK_PROMPT_CACHE", "auto")

    identity = _call("GET", "/v1/admin/platform/identity")
    assert identity["configured"] is False
    assert identity["providers"] == []

    registry = _call("GET", "/v1/admin/platform/registry")
    assert registry["configured"] is False
    assert registry["registryId"] is None and registry["registryArn"] is None

    browser = _call("GET", "/v1/admin/platform/browser")
    assert browser["configured"] is False
    assert browser["allowedDomains"] == []
    assert browser["sessionTimeout"] >= 60

    optimization = _call("GET", "/v1/admin/platform/optimization")
    assert optimization["configured"] is False
    assert optimization["targets"] == ["system_prompt", "tool_descriptions"]
    assert optimization["note"]

    bedrock = _call("GET", "/v1/admin/platform/bedrock-features")
    assert bedrock["promptCache"] == {"strategy": "auto", "ttl": None}
    assert bedrock["promptRouterArn"] is None
    assert set(bedrock["applicationProfiles"]) == {"chat", "eval", "ingestion"}


def test_registry_publish_and_search_when_configured(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("AGENTCORE_REGISTRY_ID", "reg-test")

    import core.registry as registry

    class _FakeRegistry:
        def __init__(self):
            self.published: list[dict] = []

        def create_registry_record(self, **kwargs):
            self.published.append(kwargs)
            return {"recordId": "rec-1", "name": kwargs["name"]}

        def search_registry_records(self, **kwargs):
            return {"records": [{"id": "rec-1", "name": "research-assistant"}]}

    fake = _FakeRegistry()
    monkeypatch.setattr(registry, "_client", lambda: fake)

    assert _call("GET", "/v1/admin/platform/registry")["configured"] is True

    created = _call(
        "POST",
        "/v1/admin/platform/registry/publish",
        {"name": "research-assistant", "description": "cited researcher", "recordType": "AGENT"},
        expect=201,
    )
    assert created["ok"] is True
    assert fake.published[0]["recordType"] == "AGENT"
    assert fake.published[0]["metadata"]["owner"].startswith("u_")

    found = _call("GET", "/v1/admin/platform/registry/search", query={"q": "research"})
    assert found["configured"] is True
    assert found["records"][0]["name"] == "research-assistant"

    # An invalid record type is rejected before any AWS call.
    _call(
        "POST",
        "/v1/admin/platform/registry/publish",
        {"name": "x", "recordType": "DATABASE"},
        expect=400,
    )


def test_browser_check_and_session_when_configured(monkeypatch):
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

    blocked = _call(
        "POST", "/v1/admin/platform/browser/check", {"url": "https://evil.example"}
    )
    assert blocked["allowed"] is False

    session = _call(
        "POST", "/v1/admin/platform/browser/session", {"url": "https://northwind.example"}
    )
    assert session["sessionId"] == "sess-1"
    assert session["liveViewUrl"] == "https://live.example/sess-1"

    closed = _call(
        "POST", "/v1/admin/platform/browser/session/close", {"sessionId": "sess-1"}
    )
    assert closed["stopped"] is True


def test_identity_token_when_configured(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv(
        "AGENT_WORKLOAD_IDENTITY_ARN",
        "arn:aws:bedrock-agentcore:ap-south-1:1:workload-identity/agent-1",
    )
    monkeypatch.setenv(
        "AGENT_IDENTITY_PROVIDERS",
        "arn:aws:bedrock-agentcore:ap-south-1:1:credential-provider/google-provider/abc",
    )

    import core.identity as identity

    class _FakeIdentityClient:
        def get_resource_oauth2_token(self, **kwargs):
            return {"accessToken": "secret", "expiresAt": "2030-01-01T00:00:00Z"}

    monkeypatch.setattr(identity, "_client", lambda: _FakeIdentityClient())

    assert _call("GET", "/v1/admin/platform/identity")["configured"] is True

    token = _call(
        "POST", "/v1/admin/platform/identity/token", {"provider": "google"}
    )
    assert token["obtained"] is True
    assert token["provider"] == "google"
    # Never echoes the live token.
    assert "accessToken" not in token

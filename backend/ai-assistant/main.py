"""Local ASGI server for AI Assistant — **the same handler production runs**.

Why this file exists at all: production is one Lambda behind API Gateway, and the
container's ASGI server was deleted with the MicroVM. That left no way to run AI
Assistant on a laptop. This is the smallest possible bridge back — it carries no
behaviour of its own beyond translating HTTP into the API Gateway event the handler
already understands, and translating the handler's response back out.

That translation is the whole point. The handler is not reimplemented or
conditionally bypassed here: `handler.lambda_handler` is called with a synthetic
payload-format-2.0 event and its result is returned verbatim. So:

* the **guest** route exercises the real IP-hash rate limit (the client IP is read
  from `X-Forwarded-For`, exactly as it is behind the gateway);
* the **signed-in** route reads `requestContext.authorizer.jwt.claims`, which this
  server fills in **only** for a verified Auth0 token — see below;
* the buffered SSE body the widget parses locally is byte-for-byte the one it
  parses in production.

## Identity, honestly

Production never verifies a JWT in application code: API Gateway's authorizer does
it and the Lambda reads the result. Locally there is no gateway, so something has
to do that step, and the two candidate shortcuts are both bad — trusting a
`userId` in the request body would be a real auth bypass, and skipping the
signed-in path entirely would leave the path that matters untested.

So this server **verifies the Auth0 token properly** against the tenant's JWKS
(`core.auth` does the same for the MCP servers) and only then writes the claims
into the event. An unverifiable token is rejected with 401, and a request with no
token is served as a guest. The result is that local dev has the same security
shape as production, with the *location* of the check moved, not removed.

Run it with `make ai-assistant-local-agent` (which points the widget at
`http://localhost:8091`), or directly:

    python tools/ai-assistant-knowledge/local_agent.py
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

# The packaged Lambda flattens everything to one directory; locally the repo layout
# is two levels up from this file (`backend/ai-assistant/main.py`).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from handler import lambda_handler  # noqa: E402
from src import settings  # noqa: E402

#: The two deployed routes, kept identical to `api_gateway.tf`. `AUTH` mirrors the
#: gateway's per-route `authorization_type`, so the authorizer runs on exactly the
#: route that has one in production.
ROUTES: dict[str, str] = {
    "/v1/ai-assistant/ask": "AUTH",
    "/v1/ai-assistant/guest": "NONE",
}


def _client_ip(request: Request) -> str:
    """The caller's address, preferring the proxy header the gateway also sets."""
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _claims_for(token: str) -> dict[str, Any]:
    """Verify an Auth0 bearer token and return its claims.

    Raises ``ValueError`` when the token cannot be verified, which the route turns
    into a 401 — the local equivalent of the gateway rejecting the request before
    the Lambda is ever invoked.
    """
    from src.local_auth import LocalAuthError, verify  # noqa: PLC0415

    try:
        return verify(token)
    except LocalAuthError as exc:
        raise ValueError(str(exc)) from exc


def _event(request: Request, body: bytes, claims: dict[str, Any] | None) -> dict[str, Any]:
    """Build the API Gateway payload-format-2.0 event the handler expects."""
    headers = {key.lower(): value for key, value in request.headers.items()}
    context: dict[str, Any] = {
        "http": {
            "method": request.method,
            "path": request.url.path,
            "sourceIp": _client_ip(request),
        }
    }
    # Only present when the route is AUTH **and** the token verified, which is what
    # `_authorizer_claims` keys off to choose the signed-in path.
    if claims is not None:
        context["authorizer"] = {"jwt": {"claims": claims}}
    return {
        "version": "2.0",
        "routeKey": f"{request.method} {request.url.path}",
        "rawPath": request.url.path,
        "rawQueryString": request.url.query or "",
        "headers": headers,
        "body": body.decode("utf-8", "replace"),
        "isBase64Encoded": False,
        "requestContext": context,
    }


def create_app() -> FastAPI:
    app = FastAPI(title="AI Assistant (local)", docs_url=None, redoc_url=None)

    # The widget may be served from a different origin locally (`:5173`) than this
    # server (`:8091`), and unlike the API Gateway path there is no CORS layer in
    # front of it. Loopback hosts only: this server is a development tool, and the
    # one thing it must never do is become a public, unauthenticated proxy.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_methods=["POST", "GET", "OPTIONS"],
        allow_headers=["authorization", "content-type"],
        max_age=3600,
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "config": settings.snapshot()}

    @app.post("/v1/ai-assistant/{route}")
    async def turn(route: str, request: Request) -> Response:
        path = f"/v1/ai-assistant/{route}"
        authorization = ROUTES.get(path)
        if authorization is None:
            return Response(
                content=json.dumps({"error": "Not found", "code": "not_found"}),
                status_code=404,
                media_type="application/json",
            )

        body = await request.body()
        claims: dict[str, Any] | None = None
        if authorization == "AUTH":
            header = request.headers.get("authorization") or ""
            token = header[7:].strip() if header.lower().startswith("bearer ") else ""
            # A JWT-protected route with no token is a 401 at the gateway — the
            # Lambda is never invoked. Matching that here (rather than quietly
            # serving it as a guest turn) is what keeps the local route honest
            # about which audience it serves.
            if not token:
                return Response(
                    content=json.dumps(
                        {"error": "Missing bearer token", "code": "unauthorized"}
                    ),
                    status_code=401,
                    media_type="application/json",
                    headers={"www-authenticate": "Bearer"},
                )
            try:
                claims = _claims_for(token)
            except ValueError as exc:
                return Response(
                    content=json.dumps({"error": str(exc), "code": "unauthorized"}),
                    status_code=401,
                    media_type="application/json",
                    headers={"www-authenticate": "Bearer"},
                )

        # Ask the **real** handler. `_run_frames` is what blocks on the event loop,
        # so it is offloaded to a thread and the response is returned unchanged.
        import anyio  # noqa: PLC0415

        result = await anyio.to_thread.run_sync(
            lambda: lambda_handler(_event(request, body, claims), None)
        )

        if isinstance(result, dict) and "statusCode" in result:
            status = int(result.get("statusCode") or 200)
            payload = result.get("body") or ""
            if result.get("isBase64Encoded"):
                import base64  # noqa: PLC0415

                content = base64.b64decode(payload)
            else:
                content = str(payload).encode("utf-8")
            headers = {
                str(key): str(value)
                for key, value in (result.get("headers") or {}).items()
            }
            return Response(content=content, status_code=status, headers=headers)

        # A streaming handler must be adapted deliberately rather than silently
        # serialised into something the widget cannot parse.
        return Response(
            content=json.dumps(
                {
                    "error": "This route returned a stream, which the local server does not support.",
                    "code": "unexpected_stream",
                }
            ),
            status_code=500,
            media_type="application/json",
        )

    return app


app = create_app()

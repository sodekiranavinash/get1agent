"""Streaming proxy: browser -> AgentCore Runtime ``/invocations``.

The AgentCore runtime is configured with a custom JWT authorizer (Auth0), so it
validates the caller's token itself. This Lambda is a thin, public Function URL
(response streaming) that forwards the browser's ``Authorization`` header and
body to the runtime and pipes the SSE stream back. CORS is configured on the
Function URL in Terraform.

The token is verified **here first** (``core.jwt``), so an unauthenticated or
expired request is rejected before it reaches AgentCore and starts a runtime
session. AgentCore re-validates the same token; this is the fail-fast gate.

Request headers:
    Authorization: Bearer <Auth0 access token>     (verified here, then forwarded)

Body: JSON ``{ "agentId": ..., "input": ..., "conversationId": ..., "model": ... }``
(``model`` is an optional per-run override of the agent's saved model.)
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
import uuid
from urllib.parse import quote

from awslambda import streamifyResponse  # type: ignore[import-not-found]
from core.jwt import TokenError, verify_token

_REGION = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or ""
_RUNTIME_ARN = os.environ.get("AGENT_RUNTIME_ARN") or ""
_QUALIFIER = os.environ.get("AGENT_RUNTIME_QUALIFIER") or "DEFAULT"
_TIMEOUT = int(os.environ.get("AGENT_RUN_TIMEOUT_SECONDS") or "900")


def _invocations_url() -> str:
    arn = quote(_RUNTIME_ARN, safe="")
    return (
        f"https://bedrock-agentcore.{_REGION}.amazonaws.com"
        f"/runtimes/{arn}/invocations?qualifier={_QUALIFIER}"
    )


def _lower_headers(event: dict) -> dict[str, str]:
    return {str(k).lower(): str(v) for k, v in (event.get("headers") or {}).items()}


def _bearer(value: str | None) -> str:
    if not value:
        return ""
    parts = value.split(" ", 1)
    if len(parts) == 2 and parts[0].lower() == "bearer":
        return parts[1].strip()
    return value.strip()


def _body_bytes(event: dict) -> bytes:
    body = event.get("body") or ""
    if event.get("isBase64Encoded"):
        import base64

        return base64.b64decode(body)
    return body.encode("utf-8") if isinstance(body, str) else bytes(body)


def _error(message: str) -> bytes:
    return (
        "event: error\n"
        f"data: {json.dumps({'type': 'run.error', 'message': message})}\n\n"
    ).encode("utf-8")


def _session_id(sub: str, conversation_id: str) -> str:
    """AgentCore microVM session id, bound to the authenticated user.

    AgentCore does not enforce session-to-user mappings, so a client-supplied
    session id could place two users on the same microVM. Deriving it from the
    verified ``sub`` keeps affinity (the same user + conversation resumes the
    same session) while making it unguessable and per-user. 64 hex chars.
    """
    scope = conversation_id or uuid.uuid4().hex
    return hashlib.sha256(f"{sub}:{scope}".encode("utf-8")).hexdigest()


@streamifyResponse
def lambda_handler(event, responseStream, context):  # noqa: ANN001
    if not _RUNTIME_ARN or not _REGION:
        responseStream.write(_error("Agent runtime is not configured"))
        return

    headers = _lower_headers(event)
    authorization = headers.get("authorization")
    if not authorization:
        responseStream.write(_error("Missing Authorization header"))
        return

    # Validate before the runtime hop: an invalid token must not start a session.
    # Any failure (bad token, missing config, JWKS unreachable) fails closed.
    try:
        claims = verify_token(_bearer(authorization))
    except TokenError as exc:
        print(json.dumps({"level": "warning", "message": "token rejected", "error": str(exc)}), flush=True)
        responseStream.write(_error("Unauthorized"))
        return
    except Exception as exc:  # noqa: BLE001 - never let a validator error open the gate
        print(json.dumps({"level": "error", "message": "token validation failed", "error": str(exc)}), flush=True)
        responseStream.write(_error("Unauthorized"))
        return

    body = _body_bytes(event)
    try:
        payload = json.loads(body) if body else {}
    except (ValueError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    session_id = _session_id(
        str(claims.get("sub") or ""), str(payload.get("conversationId") or "").strip()
    )

    request = urllib.request.Request(
        _invocations_url(),
        data=body,
        headers={
            "authorization": authorization,
            "content-type": "application/json",
            "accept": "text/event-stream",
            "x-amzn-bedrock-agentcore-runtime-session-id": session_id,
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            while True:
                chunk = response.read(4096)
                if not chunk:
                    break
                responseStream.write(chunk)
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:500].decode("utf-8", "replace")
        responseStream.write(_error(f"Agent runtime returned HTTP {exc.code}: {detail}"))
    except urllib.error.URLError as exc:
        responseStream.write(_error(f"Could not reach agent runtime: {exc.reason}"))
    except Exception as exc:  # noqa: BLE001 - stream any failure to the client
        responseStream.write(_error(str(exc)))

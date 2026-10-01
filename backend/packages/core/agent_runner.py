"""Run an agent or workflow turn server-side (no browser, no user JWT).

Scheduled runs have no user token, so this authenticates as the **platform
service** exactly like the evaluations worker:

1. fetch an Auth0 client-credentials (M2M) token whose ``sub`` is
   ``<client_id>@clients`` (the agent runtime trusts it via ``SERVICE_AUTH_CLIENT_ID``);
2. direct-invoke the agent-run control plane (IAM) to launch a Lambda MicroVM and
   get its ``{endpoint, token}``;
3. POST the run to the MicroVM ``/invocations`` (service bearer + ingress token)
   and read the SSE frames to completion.

The runtime persists the turn itself (``persist_turn``) when a ``conversationId``
is supplied, so the scheduled run appears in the chat sidebar / builder history.

Everything is stdlib + boto3 over public HTTPS.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_token_cache: dict[str, Any] = {"value": "", "expires_at": 0.0}


class AgentRunError(Exception):
    """The scheduled run could not be started or completed."""


def _env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def _token_url() -> str:
    url = _env("AUTH0_TOKEN_URL")
    if url:
        return url
    domain = _env("AUTH0_DOMAIN") or _env("AUTH0_ISSUER_BASE_URL")
    if domain and not domain.startswith("http"):
        domain = f"https://{domain}"
    return f"{domain.rstrip('/')}/oauth/token" if domain else ""


def _service_token() -> str:
    now = time.time()
    if _token_cache["value"] and float(_token_cache["expires_at"]) > now + 30:
        return str(_token_cache["value"])

    url = _token_url()
    client_id = _env("AGENT_SERVICE_CLIENT_ID")
    client_secret = _env("AGENT_SERVICE_CLIENT_SECRET")
    audience = _env("AUTH0_AUDIENCE")
    if not (url and client_id and client_secret and audience):
        raise AgentRunError("Agent service auth is not configured")

    body = urllib.parse.urlencode(
        {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "audience": audience,
        }
    ).encode()
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "content-type": "application/x-www-form-urlencoded",
            "accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise AgentRunError(f"Service token request failed ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        raise AgentRunError("Service token request failed") from exc

    token = str(payload.get("access_token") or "")
    if not token:
        raise AgentRunError("Service token response had no access token")
    _token_cache["value"] = token
    _token_cache["expires_at"] = now + int(payload.get("expires_in") or 3600)
    return token


def start_session() -> dict[str, str]:
    """Ask the control plane for a MicroVM ``{endpoint, token}``."""
    function = _env("AGENT_RUN_FUNCTION")
    if not function:
        raise AgentRunError("The agent runner is not configured")
    import boto3

    client = boto3.client("lambda", region_name=os.environ.get("AWS_REGION"))
    response = client.invoke(
        FunctionName=function,
        InvocationType="RequestResponse",
        Payload=b"{}",
    )
    raw = response["Payload"].read()
    if response.get("FunctionError"):
        raise AgentRunError("The agent runner failed to start a session")
    try:
        parsed = json.loads(raw or b"{}")
    except ValueError as exc:
        raise AgentRunError("The agent runner returned an invalid response") from exc
    if isinstance(parsed, dict) and "body" in parsed:
        try:
            parsed = json.loads(parsed["body"])
        except (TypeError, ValueError) as exc:
            raise AgentRunError("The agent runner returned an invalid body") from exc
    endpoint = str((parsed or {}).get("endpoint") or "").rstrip("/")
    token = str((parsed or {}).get("token") or "")
    if not (endpoint and token):
        raise AgentRunError("The agent runner returned no endpoint")
    return {"endpoint": endpoint, "token": token}


def _iter_frames(response: Any):
    for raw in response:
        line = raw.decode("utf-8", "replace").strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        try:
            frame = json.loads(data)
        except ValueError:
            continue
        if isinstance(frame, dict):
            yield frame


def run_turn(
    *,
    user_id: str,
    target_id: str,
    target_type: str,
    input_text: str,
    conversation_id: int | str | None = None,
    timeout_seconds: int = 600,
) -> dict[str, Any]:
    """Run one turn and return ``{answer, status, error, runId}``.

    ``target_type`` is ``agent`` or ``workflow``; the runtime dispatches on
    ``agentId`` / ``workflowId``.
    """
    if not target_id:
        raise AgentRunError("No target selected")
    bearer = _service_token()
    session = start_session()
    target_key = "workflowId" if target_type == "workflow" else "agentId"
    payload: dict[str, Any] = {
        "userId": user_id,
        target_key: target_id,
        "input": input_text or "Run the scheduled task.",
    }
    if conversation_id is not None:
        payload["conversationId"] = str(conversation_id)

    request = urllib.request.Request(
        f"{session['endpoint']}/invocations",
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "authorization": f"Bearer {bearer}",
            "x-aws-proxy-auth": session["token"],
            "content-type": "application/json",
            "accept": "text/event-stream",
        },
    )

    answer_parts: list[str] = []
    run_id = ""
    error = ""
    status = "completed"
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            for frame in _iter_frames(response):
                kind = frame.get("type")
                if kind == "run.started":
                    run_id = str(frame.get("runId") or "")
                elif kind == "text":
                    answer_parts.append(str(frame.get("data") or ""))
                elif kind == "run.error":
                    error = str(frame.get("message") or "run failed")
                    status = "failed"
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise AgentRunError(f"Run failed ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AgentRunError("Run timed out") from exc

    answer = "".join(answer_parts).strip()
    if error and not answer:
        raise AgentRunError(error)
    return {"answer": answer, "status": status, "error": error, "runId": run_id}

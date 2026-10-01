"""Run a saved agent as an evaluation task, server-side.

The background worker has no user JWT, so it authenticates to the AgentCore
runtime as the **platform service**:

1. fetch an Auth0 client-credentials (M2M) token whose ``sub`` is
   ``<client_id>@clients`` (the runtime trusts it via ``SERVICE_AUTH_CLIENT_ID``);
2. direct-invoke the agent-run control plane (IAM) to launch a Lambda MicroVM
   and get its ``{endpoint, token}``;
3. POST the run to the MicroVM ``/invocations`` (service bearer + ingress token)
   and read the SSE frames, collecting the final answer, tool calls and sources.

Everything is stdlib + boto3; the runtime is reached over public HTTPS.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from . import config


class AgentRunError(Exception):
    """The agent could not be run for evaluation."""


_token_cache: dict[str, Any] = {"value": "", "expires_at": 0.0}


def _service_token() -> str:
    now = time.time()
    if _token_cache["value"] and float(_token_cache["expires_at"]) > now + 30:
        return str(_token_cache["value"])

    url = config.auth0_token_url()
    client_id = config.service_client_id()
    client_secret = config.service_client_secret()
    audience = config.service_audience()
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


def _start_session() -> dict[str, str]:
    function = config.agent_run_function()
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


def _frames(line: str) -> dict[str, Any] | None:
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data:
        return None
    try:
        frame = json.loads(data)
    except ValueError:
        return None
    return frame if isinstance(frame, dict) else None


def run_agent(
    *,
    user_id: str,
    agent_name: str,
    question: str,
    timeout_seconds: int | None = None,
) -> dict[str, Any]:
    """Run one agent turn and return ``{answer, tools, sources}``."""
    if not agent_name:
        raise AgentRunError("No agent selected")
    bearer = _service_token()
    session = _start_session()
    body = json.dumps(
        {"userId": user_id, "agentId": agent_name, "input": question}
    ).encode()
    request = urllib.request.Request(
        f"{session['endpoint']}/invocations",
        data=body,
        method="POST",
        headers={
            "authorization": f"Bearer {bearer}",
            "x-aws-proxy-auth": session["token"],
            "content-type": "application/json",
            "accept": "text/event-stream",
        },
    )

    answer_parts: list[str] = []
    tools: list[str] = []
    sources: list[dict[str, Any]] = []
    error = ""
    try:
        with urllib.request.urlopen(
            request, timeout=timeout_seconds or config.agent_timeout()
        ) as response:
            for raw in response:
                line = raw.decode("utf-8", "replace").strip()
                frame = _frames(line)
                if not frame:
                    continue
                kind = frame.get("type")
                if kind == "text":
                    answer_parts.append(str(frame.get("text") or ""))
                elif kind in ("tool.start", "tool.result"):
                    name = (
                        frame.get("name")
                        or frame.get("tool")
                        or frame.get("toolName")
                        or frame.get("tool_name")
                    )
                    if name:
                        tools.append(str(name))
                    if kind == "tool.result" and isinstance(frame.get("sources"), list):
                        sources.extend(frame["sources"])
                elif kind == "run.error":
                    error = str(frame.get("error") or "agent run failed")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise AgentRunError(f"Agent run failed ({exc.code}): {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AgentRunError("Agent run timed out") from exc

    answer = "".join(answer_parts).strip()
    if error and not answer:
        raise AgentRunError(error)
    return {"answer": answer, "tools": tools, "sources": sources}

"""Thin boto3 wrapper around the Bedrock AgentCore Code Interpreter API.

The AgentCore client is only available on a recent boto3/botocore, which the
function bundles (the Lambda runtime version may predate the service model).
Sessions are isolated microVMs; ``execute`` streams the result and enforces a
wall-clock deadline via the client ``read_timeout`` plus an event-loop check.
"""

from __future__ import annotations

from typing import Any

from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectionError as BotoConnectionError,
    ReadTimeoutError,
)

DEFAULT_IDENTIFIER = "aws.codeinterpreter.v1"

# Session/identifier errors that mean "the mapping is stale, start a new one".
_SESSION_GONE_CODES = frozenset(
    {
        "ResourceNotFoundException",
        "ValidationException",
        "AccessDeniedException",
        "ServiceQuotaExceededException",
    }
)


class AgentCoreError(Exception):
    """A Code Interpreter call failed."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class SessionGone(AgentCoreError):
    """The stored session id is no longer usable."""


class ExecutionTimeout(AgentCoreError):
    """Execution exceeded the internal deadline."""


def client(region: str | None, read_timeout: int) -> Any:
    import boto3

    return boto3.client(
        "bedrock-agentcore",
        region_name=region,
        config=Config(
            connect_timeout=10,
            read_timeout=max(int(read_timeout), 30),
            retries={"max_attempts": 2, "mode": "standard"},
        ),
    )


def start_session(
    client: Any,
    identifier: str,
    *,
    name: str,
    ttl: int,
    client_token: str,
) -> str:
    try:
        response = client.start_code_interpreter_session(
            codeInterpreterIdentifier=identifier,
            name=name,
            sessionTimeoutSeconds=int(ttl),
            clientToken=client_token,
        )
    except ClientError as exc:
        raise _wrap(exc) from exc
    session_id = str(response.get("sessionId") or "")
    if not session_id:
        raise AgentCoreError("AgentCore did not return a session id")
    return session_id


def stop_session(client: Any, identifier: str, session_id: str) -> None:
    try:
        client.stop_code_interpreter_session(
            codeInterpreterIdentifier=identifier,
            sessionId=session_id,
        )
    except ClientError as exc:
        error = _wrap(exc)
        if isinstance(error, SessionGone):
            return
        raise error from exc


def get_session(client: Any, identifier: str, session_id: str) -> dict[str, Any]:
    try:
        return client.get_code_interpreter_session(
            codeInterpreterIdentifier=identifier,
            sessionId=session_id,
        )
    except ClientError as exc:
        raise _wrap(exc) from exc


def execute(
    client: Any,
    identifier: str,
    session_id: str,
    *,
    code: str,
    language: str,
    timeout: int,
    max_output: int,
) -> dict[str, Any]:
    """Run ``code`` and return ``{output, is_error, timed_out}``.

    Raises ``SessionGone`` when the session id is invalid/expired and
    ``ExecutionTimeout`` when the internal deadline is exceeded.
    """
    import time

    started = time.monotonic()
    try:
        response = client.invoke_code_interpreter(
            codeInterpreterIdentifier=identifier,
            sessionId=session_id,
            name="executeCode",
            arguments={"language": language, "code": code},
        )
        chunks: list[str] = []
        is_error = False
        total = 0
        for event in response.get("stream", []):
            if time.monotonic() - started > timeout:
                raise ExecutionTimeout(
                    f"Execution exceeded {timeout}s and the sandbox was stopped"
                )
            if not isinstance(event, dict):
                continue
            result = event.get("result")
            if not isinstance(result, dict):
                continue
            if result.get("isError"):
                is_error = True
            for item in result.get("content") or []:
                if not isinstance(item, dict) or item.get("type") != "text":
                    continue
                text = item.get("text") or ""
                total += len(text)
                if total <= max_output:
                    chunks.append(text)
                elif not chunks or chunks[-1] != "\n…[truncated]":
                    chunks.append("\n…[truncated]")
        return {"output": "".join(chunks), "is_error": is_error, "timed_out": False}
    except ReadTimeoutError as exc:
        raise ExecutionTimeout(
            f"Execution exceeded {timeout}s and the sandbox was stopped"
        ) from exc
    except BotoConnectionError as exc:
        # A dropped stream is treated as a timeout: the sandbox may be stuck.
        raise ExecutionTimeout("The sandbox stream was interrupted") from exc
    except ClientError as exc:
        raise _wrap(exc) from exc


def _wrap(exc: ClientError) -> AgentCoreError:
    error = exc.response.get("Error", {})
    code = str(error.get("Code") or "")
    message = str(error.get("Message") or "AgentCore request failed")
    if code in _SESSION_GONE_CODES:
        return SessionGone(message, code=code)
    return AgentCoreError(message, code=code)

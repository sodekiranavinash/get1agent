"""AI Assistant's Lambda — one function behind two API Gateway routes.

Why one function and not a MicroVM plus a control plane:

* Identity is not this function's problem. API Gateway validates the Auth0 JWT on
  ``/v1/ai-assistant/ask`` and hands the *verified* claims in
  ``requestContext.authorizer.jwt.claims``; this module reads them and never
  verifies, mints or forwards a token. There is no session secret to keep in sync
  between two halves of the system, and a ``userId`` in the request body is
  ignored on both routes.
* ``/v1/ai-assistant/guest`` has no authorizer. It is the same engine with
  ``is_guest=True``, so a guest gets the same classifier, the same retrieval and
  the same frames — and nothing is persisted, which is what makes the guest path
  stateless.

**The response is buffered, not streamed.** API Gateway caps an integration at
30s and cannot stream, so a turn is assembled in memory and returned as one SSE
body that the widget parses frame by frame. The Lambda's own timeout is 30s to
match the gateway ceiling exactly: a mismatch is the worst case, where the
gateway returns 504 at 30s while the Lambda keeps running and we pay for an
answer nobody receives. ``AI_ASSISTANT_TURN_BUDGET_SECONDS`` (default 24) is the
soft ceiling that makes a slow turn fail *cleanly* with an ``run.error`` frame
the widget can render, rather than as a 504 with no frames at all.

Environment:
    AI_ASSISTANT_GUEST_ENABLED     turn guests off entirely (the admin flag wins too)
    AI_ASSISTANT_GUEST_SALT        salt for the per-IP rate-limit bucket hash
    AI_ASSISTANT_TURN_BUDGET_SECONDS  soft ceiling before a turn gives up (24)
    AI_ASSISTANT_MODEL             answer model for the direct path
    AI_ASSISTANT_CLASSIFIER_MODEL  classifier model
    BEDROCK_REGION                 Bedrock region
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import sys
import time
import traceback
from typing import Any

# The packaged zip flattens everything to the root (see the Makefile), so the
# shared packages and this service's own package are importable directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from data.repositories.users import get_or_create_user, is_admin_claims  # noqa: E402

from src import metrics, settings  # noqa: E402
from src.frames import FrameWriter, sse  # noqa: E402
from src.identity import Identity, guest_identity  # noqa: E402
from src.limits import SURFACE_GUEST, Caller, check_and_count  # noqa: E402

#: A run's frames are JSON; this is a runaway guard, not a real limit. The answer
#: text is separately capped by ``MAX_ANSWER_CHARS``.
MAX_ANSWER_CHARS = 8_000

#: A buffered API Gateway response is capped at 6 MB. Frames are far smaller than
#: that (the cap above bounds the text), so this only guards a pathological loop.
MAX_RESPONSE_BYTES = 5_000_000

DEFAULT_TURN_BUDGET_SECONDS = 24.0


# --------------------------------------------------------------------------- #
# Event helpers
# --------------------------------------------------------------------------- #


def _claims(event: dict[str, Any]) -> dict[str, Any] | None:
    """The gateway's *verified* JWT claims, or ``None`` for the guest route.

    This is the whole of AI Assistant's authentication: the authorizer already ran,
    so anything in here is trustworthy and nothing else in the event is.
    """
    try:
        claims = event["requestContext"]["authorizer"]["jwt"]["claims"]
    except (KeyError, TypeError):
        return None
    return claims if isinstance(claims, dict) else None


def _client_ip(event: dict[str, Any]) -> str:
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    forwarded = str(headers.get("x-forwarded-for") or "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    request_context = event.get("requestContext") or {}
    http = request_context.get("http") or {}
    return str(http.get("sourceIp") or "")


def _guest_key(ip: str) -> str:
    """A stable, non-reversible bucket key — the raw IP is never stored."""
    salt = os.environ.get("AI_ASSISTANT_GUEST_SALT", "ai-assistant")
    return "guest_" + hashlib.sha256(f"{salt}|{ip or 'unknown'}".encode()).hexdigest()[:24]


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8", "replace")
        except Exception:  # noqa: BLE001 - a malformed body is an empty one
            return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _clean_history(value: Any) -> list[dict[str, str]]:
    """Accept a browser-supplied transcript, bounded on both axes."""
    if not isinstance(value, list):
        return []
    limit = settings.max_history_turns()
    cleaned: list[dict[str, str]] = []
    for item in value[-(limit * 2) :]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
            content = str(item.get("content") or "").strip()
            if content:
                cleaned.append({"role": str(item["role"]), "content": content[:2000]})
    return cleaned[-limit:]


def _json_response(status: int, body: dict[str, Any], *, retry_after: int = 0) -> dict[str, Any]:
    headers = {"content-type": "application/json", "cache-control": "no-store"}
    if retry_after:
        headers["retry-after"] = str(retry_after)
    return {"statusCode": status, "headers": headers, "body": json.dumps(body)}


def _error_response(
    status: int,
    code: str,
    message: str,
    *,
    retry_after: int = 0,
    sign_in_required: bool = False,
) -> dict[str, Any]:
    return _json_response(
        status,
        {
            "error": message,
            "code": code,
            "retryAfterSeconds": retry_after or None,
            "signInRequired": sign_in_required or None,
        },
        retry_after=retry_after,
    )


def _sse_response(frames: list[dict[str, Any]], *, status: int = 200) -> dict[str, Any]:
    """Buffer a finished run into one SSE body.

    ``text/event-stream`` is kept as the content type even though the body arrives
    whole: the widget's parser is the same one, and a proxy can then treat a
    partial failure the same way it treats a stream.
    """
    payload = "".join(sse(frame) for frame in frames)
    if len(payload) > MAX_RESPONSE_BYTES:
        payload = "".join(sse(frame) for frame in frames[:1]) + sse(
            {
                "type": "run.error",
                "runId": frames[0].get("runId") if frames else "",
                "message": "That answer was too large to deliver. Try a narrower question.",
            }
        )
    return {
        "statusCode": status,
        "headers": {
            "content-type": "text/event-stream; charset=utf-8",
            "cache-control": "no-cache, no-store",
        },
        "body": payload,
        "isBase64Encoded": False,
    }


# --------------------------------------------------------------------------- #
# The turn
# --------------------------------------------------------------------------- #


def _run_frames(
    *,
    question: str,
    history: list[dict[str, str]],
    route: str,
    run_id: str,
    conversation_id: str,
    identity: Identity,
    allow_admin: bool,
    model: str,
) -> list[dict[str, Any]]:
    """Drive one turn to completion and return the frames it produced.

    The async generator is the engine's contract (``agent.run_turn``), so it is
    drained here rather than duplicated — the buffered delivery is the only
    difference from the old streaming ingress.

    ``src.agent`` is imported **inside** this function on purpose: it is the only
    module that reaches for LangChain, so the guest route (which never sets
    ``use_agent``) keeps a small import graph and a shorter cold start.
    """
    from src.agent import TurnRequest, run_turn  # noqa: PLC0415

    request = TurnRequest(
        question=question,
        history=history,
        route=route,
        conversation_id=conversation_id,
        run_id=run_id,
        user_id=identity.user_id,
        is_guest=identity.is_guest,
        allow_admin=allow_admin,
        model=model,
        surface=identity.surface,
        # A guest gets the direct path: no tools, no agent graph, nothing to plan.
        use_agent=not identity.is_guest,
    )

    async def drive() -> list[dict[str, Any]]:
        frames: list[dict[str, Any]] = []
        answer_chars = 0
        async for frame in run_turn(request):
            if frame.get("type") == "text":
                answer_chars += len(str(frame.get("data") or ""))
                if answer_chars > MAX_ANSWER_CHARS:
                    break
            frames.append(frame)
        return frames

    return asyncio.run(drive())


def _answer_turn(
    *,
    identity: Identity,
    body: dict[str, Any],
    allow_admin: bool,
) -> dict[str, Any]:
    """Shared body of both routes: rate limit, run, persist, return frames."""
    question = str(body.get("question") or body.get("input") or "").strip()
    route = str(body.get("route") or "")[:200]
    model = str(body.get("model") or "") or settings.model()

    # ---- rate limit (per caller) ---------------------------------------
    caller = (
        Caller(key=identity.user_id, surface=SURFACE_GUEST, is_admin=False)
        if identity.is_guest
        else identity.to_caller()
    )
    allowed, retry_after = check_and_count(caller)
    if not allowed:
        metrics.rate_limited(surface=identity.surface, scope=caller.scope)
        return _error_response(
            429,
            "rate_limited",
            "That is a lot of questions! Sign in to keep going, or try again shortly.",
            retry_after=retry_after,
            sign_in_required=identity.is_guest,
        )

    # ---- run ------------------------------------------------------------
    budget = _turn_budget_seconds()
    started = time.perf_counter()
    frames: list[dict[str, Any]] = []
    error = ""
    try:
        frames = _run_frames(
            question=question,
            history=_clean_history(body.get("history")),
            route=route,
            run_id=str(body.get("runId") or ""),
            conversation_id=str(body.get("conversationId") or ""),
            identity=identity,
            allow_admin=allow_admin,
            model=model,
        )
    except Exception as exc:  # noqa: BLE001 - a failed turn is still a friendly turn
        error = f"{type(exc).__name__}: {exc}"
        print(traceback.format_exc(), file=sys.stderr)
        frames = [
            FrameWriter(
                run_id=str(body.get("runId") or ""), model=model, is_guest=identity.is_guest
            ).failed("Something went wrong. Please try again.", retryable=True)
        ]

    elapsed = time.perf_counter() - started
    if elapsed > budget and frames and frames[-1].get("type") != "run.error":
        # Slow, not broken. Say so in the same frame shape the widget already
        # renders, so a near-miss is a sentence rather than a 504.
        frames.append(
            {
                "type": "run.error",
                "runId": _run_id(frames),
                "message": (
                    "That took longer than I can keep a connection open. "
                    "Try a narrower question."
                ),
                "retryable": True,
            }
        )

    # ---- persist (signed-in only; guests are never stored) --------------
    if not identity.is_guest:
        _persist(body, frames, identity, error=error)

    return _sse_response(frames)


def _run_id(frames: list[dict[str, Any]]) -> str:
    for frame in frames:
        if frame.get("type") == "run.started":
            return str(frame.get("runId") or "")
    return ""


def _turn_budget_seconds() -> float:
    try:
        return float(os.environ.get("AI_ASSISTANT_TURN_BUDGET_SECONDS") or DEFAULT_TURN_BUDGET_SECONDS)
    except (TypeError, ValueError):
        return DEFAULT_TURN_BUDGET_SECONDS


def _persist(
    body: dict[str, Any],
    frames: list[dict[str, Any]],
    identity: Identity,
    *,
    error: str = "",
) -> None:
    """Write the finished turn and its trace. A storage failure never costs the answer."""
    from src import conversations, traces  # noqa: PLC0415

    intent = next(
        (frame for frame in frames if frame.get("type") == "ai-assistant.intent"), None
    )
    request = _PersistRequest(body)
    try:
        conversations.record_turn(
            request, frames, identity, intent=intent, error=error
        )
    except Exception:  # noqa: BLE001 - replay is nice to have; the answer is not
        print(
            json.dumps({"level": "error", "message": "ai-assistant transcript write failed"}),
            file=sys.stderr,
        )
        traceback.print_exc()
    try:
        traces.record_trace(
            request,
            frames,
            identity=identity,
            intent=intent,
            error=error,
            entry_route=request.route,
        )
    except Exception:  # noqa: BLE001
        print(
            json.dumps({"level": "error", "message": "ai-assistant trace write failed"}),
            file=sys.stderr,
        )
        traceback.print_exc()


class _PersistRequest:
    """The request fields ``conversations``/``traces`` read, without importing the agent.

    Both modules take ``Any`` and read a handful of attributes off it. Building the
    real ``TurnRequest`` here would import the agent framework on the guest path's
    behalf, so this carries only what persistence actually looks at.
    """

    def __init__(self, body: dict[str, Any]) -> None:
        self.question = str(body.get("question") or body.get("input") or "").strip()
        self.history: list[dict[str, str]] = []
        self.route = str(body.get("route") or "")[:200]
        self.conversation_id = str(body.get("conversationId") or "")
        self.run_id = str(body.get("runId") or "")
        self.model = str(body.get("model") or "") or settings.model()
        self.surface = "user"

# --------------------------------------------------------------------------- #
# Routes
# --------------------------------------------------------------------------- #


def _signed_in(event: dict[str, Any], claims: dict[str, Any]) -> dict[str, Any]:
    """``POST /v1/ai-assistant/ask`` — the gateway verified the JWT."""
    body = _parse_body(event)
    question = str(body.get("question") or body.get("input") or "").strip()
    if not question:
        return _error_response(400, "empty", "Ask me something about the platform.")
    limit = settings.max_input_chars()
    if len(question) > limit:
        return _error_response(
            413, "too_long", f"That question is longer than {limit} characters."
        )

    # The claims are authoritative; a userId in the body is never read.
    profile = get_or_create_user(claims)
    identity = Identity(
        user_id=str(profile.get("userId") or ""),
        sub=str(profile.get("sub") or claims.get("sub") or ""),
        email=str(profile.get("email") or ""),
        name=str(profile.get("name") or ""),
        is_admin=is_admin_claims(claims),
    )
    if not identity.user_id:
        return _error_response(403, "no_account", "No account found for this identity.")

    # A conversation is created up front so the turn has somewhere to land and
    # `run.started.sessionId` carries a real id the widget can adopt.
    from src import conversations  # noqa: PLC0415

    conversation_id = str(body.get("conversationId") or "")
    if not conversation_id:
        try:
            conversation_id = conversations.ensure_conversation(
                identity,
                entry_route=str(body.get("route") or "")[:200],
                model=str(body.get("model") or "") or settings.model(),
            )
        except Exception:  # noqa: BLE001 - a history write must not block an answer
            traceback.print_exc()
    if conversation_id:
        body["conversationId"] = conversation_id

    return _answer_turn(
        identity=identity,
        body=body,
        allow_admin=identity.is_admin,
    )


def _guest(event: dict[str, Any]) -> dict[str, Any]:
    """``POST /v1/ai-assistant/guest`` — no authorizer, nothing persisted."""
    body = _parse_body(event)
    question = str(body.get("question") or body.get("input") or "").strip()
    if not question:
        return _error_response(400, "empty", "Ask me something about the platform.")
    limit = settings.max_input_chars()
    if len(question) > limit:
        return _error_response(
            413, "too_long", f"That question is longer than {limit} characters."
        )

    identity = guest_identity(_client_ip(event), salt=os.environ.get("AI_ASSISTANT_GUEST_SALT", ""))
    # A guest may never read admin content, whatever the corpus says.
    return _answer_turn(identity=identity, body=body, allow_admin=False)


def lambda_handler(event: dict[str, Any], context: Any = None) -> Any:
    """API Gateway (payload format 2.0, ``AWS_PROXY``) entry point."""
    if not settings.enabled():
        return _error_response(503, "disabled", "AI Assistant is temporarily unavailable.")

    claims = _claims(event)
    if claims is not None:
        return _signed_in(event, claims)

    if not settings.guest_enabled():
        return _error_response(
            403, "guest_disabled", "Sign in to ask AI Assistant.", sign_in_required=True
        )
    return _guest(event)

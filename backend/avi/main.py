"""Avi's HTTP surface — what the MicroVM proxy and the guest Lambda both call.

Contract (deliberately narrow, so the ingress paths carry no logic):

    GET  /ping         liveness + effective config + a streaming self-test
    POST /invocations  run one turn, streaming SSE frames
    POST /feedback     record a thumb (signed-in only)
    GET  /conversations/{id}      the stored transcript (signed-in only)
    DELETE /conversations/{id}    forget a conversation

``/ping`` reports ``"streaming": true`` only when the streaming path has been
proven on this instance. That field exists because ``ChatBedrockConverse``
silently falls back to non-streaming for providers it does not recognise, and a
regression there is invisible except as a slow, blobby answer.

Run locally:

    AVI_MODE=local PYTHONPATH=../packages .venv/bin/python main.py
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from avi import settings
from avi.agent import TurnRequest, run_turn
from avi.conversations import ensure_conversation, record_turn
from avi.identity import resolve_identity
from avi.limits import check_and_count
from avi.traces import record_trace

app = FastAPI(title="get1agent avi-agent", version="1.0.0", docs_url=None, redoc_url=None)

# The agent service is called cross-origin in local development (the Vite dev
# server on :5173 talking to this process on :8091). Without CORS the browser's
# preflight fails and the widget cannot reach Avi at all — which is invisible from
# curl, where there is no preflight. In production the browser talks to the MicroVM
# proxy instead, so this is defence-in-depth rather than the only gate; the real
# barrier is the signed session token, which CORS never replaces.
_allowed_origins = [
    origin.strip()
    for origin in (os.environ.get("AVI_ALLOWED_ORIGINS") or "*").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins or ["*"],
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["authorization", "content-type", "accept"],
    expose_headers=["retry-after"],
    max_age=3600,
)

#: Set once at import; a cold container reports its configuration on /ping.
STARTED_AT = time.time()
_STREAMING_OK: bool | None = None


def _sse_headers() -> dict[str, str]:
    return {
        "content-type": "text/event-stream; charset=utf-8",
        "cache-control": "no-cache, no-transform",
        "connection": "keep-alive",
        # Nginx/Cloudflare buffering turns a token stream into one blob.
        "x-accel-buffering": "no",
    }


def _error_frame(message: str, *, code: str = "error", status: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message, "code": code})


@app.get("/ping")
async def ping() -> dict[str, Any]:
    """Liveness plus the effective configuration (used by the control plane)."""
    return {
        "status": "ok",
        "configured": True,
        "streaming": _STREAMING_OK is not False,
        "uptimeSeconds": int(time.time() - STARTED_AT),
        "mode": os.environ.get("AVI_MODE", "prod"),
        **settings.snapshot(),
    }


@app.post("/streaming-self-test")
async def streaming_self_test() -> dict[str, Any]:
    """Prove the streaming path once, so /ping can report it honestly."""
    global _STREAMING_OK
    from avi.agent import _model  # noqa: PLC0415
    from avi.frames import flatten_content  # noqa: PLC0415

    chunks = 0
    try:
        model = _model(settings.model())
        async for chunk in model.astream("Say ok"):
            if flatten_content(getattr(chunk, "content", "")):
                chunks += 1
        _STREAMING_OK = chunks > 1
    except Exception:  # noqa: BLE001 - a self-test must never crash the service
        _STREAMING_OK = None
    return {"streaming": _STREAMING_OK, "chunks": chunks}


def _parse_body(raw: bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw or b"{}")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="invalid JSON body")
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="body must be a JSON object")
    return data


def _client_ip(request: Request) -> str:
    """The caller's IP, for the guest rate-limit bucket.

    A MicroVM/Function URL sits behind a proxy, so the first entry of
    ``x-forwarded-for`` is the client. Only ever hashed (see ``identity``), never
    stored raw.
    """
    forwarded = request.headers.get("x-forwarded-for") or ""
    if forwarded:
        return forwarded.split(",")[0].strip()
    return str(getattr(request.client, "host", "") or "")


def _clean_history(history: Any) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in history[:40]:
        if isinstance(item, dict) and item.get("role") and item.get("content"):
            cleaned.append(
                {"role": str(item["role"]), "content": str(item["content"])[:4000]}
            )
    return cleaned


async def _turn_stream(
    body: dict[str, Any],
    *,
    identity: Any,
) -> AsyncIterator[str]:
    """Run the turn and serialise each frame, always closing with a terminal frame."""
    from avi.frames import sse  # noqa: PLC0415

    is_guest = bool(identity.is_guest)
    question = str(body.get("question") or body.get("input") or "").strip()
    surface = "guest" if is_guest else ("eval" if body.get("surface") == "eval" else "user")
    model_id = str(body.get("model") or "")

    # A signed-in turn must always have a conversation to land in, or
    # ``record_turn`` silently stores nothing and the admin conversation view is
    # permanently empty. The browser cannot mint an id, so the first turn of a
    # dialog creates one here and reports it as ``run.started.sessionId``; the
    # widget sends it back on every later turn. Guests are never persisted, so
    # they get no conversation at all.
    conversation_id = str(body.get("conversationId") or "")
    if not is_guest and not conversation_id:
        try:
            conversation_id = ensure_conversation(
                identity,
                entry_route=str(body.get("route") or "")[:200],
                model=model_id or settings.model(),
            )
        except Exception:  # noqa: BLE001 - storage must never block an answer
            conversation_id = ""

    request = TurnRequest(
        question=question,
        history=_clean_history(body.get("history")),
        route=str(body.get("route") or "")[:200],
        conversation_id=conversation_id,
        run_id=str(body.get("runId") or ""),
        user_id=identity.user_id,
        is_guest=is_guest,
        allow_admin=bool(identity.is_admin),
        model=model_id,
        answer_mode=str(body.get("answerMode") or "summarize"),
        retrieve=bool(body.get("retrieve", True)),
        use_agent=bool(body.get("useAgent", True)),
        surface=surface,
    )

    frames: list[dict[str, Any]] = []
    intent: dict[str, Any] | None = None
    error: str = ""

    try:
        async for frame in run_turn(request):
            if frame.get("type") == "avi.intent":
                intent = frame
            if frame.get("type") == "run.error":
                error = str(frame.get("message") or "")
            frames.append(frame)
            yield sse(frame)
    except Exception as exc:  # noqa: BLE001 - a crashed stream must still terminate
        error = f"{type(exc).__name__}: {exc}"
        from avi.frames import FrameWriter, sse as sse_encode  # noqa: PLC0415

        writer = FrameWriter(run_id=request.run_id or "avirun_error", model=request.model)
        terminal = writer.failed("Something went wrong on my side. Please try again.")
        frames.append(terminal)
        yield sse_encode(terminal)

    # Persistence is best-effort and only for signed-in users; a guest answer is
    # never stored, which is what makes the guest path stateless.
    if not identity.is_guest and request.conversation_id:
        try:
            record_turn(request, frames, identity, intent=intent, error=error)
        except Exception:  # noqa: BLE001
            pass
    if not identity.is_guest:
        try:
            record_trace(
                request,
                frames,
                identity=identity,
                intent=intent,
                error=error,
                entry_route=request.route,
            )
        except Exception:  # noqa: BLE001
            pass


@app.post("/invocations")
async def invocations(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Any:
    """Stream one Avi turn as SSE.

    Identity comes from the signed session token the control plane minted after API
    Gateway verified the Auth0 JWT. A guest arrives with a **guest badge** — the
    same signed mechanism with ``guest: true`` — so the service verifies a
    signature for both audiences rather than trusting a header or a body field.
    """
    body = _parse_body(await request.body())
    question = str(body.get("question") or body.get("input") or "").strip()

    if not settings.enabled():
        return _error_frame("Avi is temporarily unavailable.", code="disabled", status=503)
    if not question:
        return _error_frame("Ask me something about the platform.", code="empty", status=400)
    if len(question) > settings.max_input_chars():
        return _error_frame(
            f"That question is longer than {settings.max_input_chars()} characters. "
            "Could you shorten it?",
            code="too_long",
            status=413,
        )

    # An anonymous caller is a **guest**, identified by a hash of their IP and
    # subject to the tighter guest budget. Behind API Gateway a client_ip is always
    # present; served directly (local dev, or a Function URL), a missing one would
    # bucket every caller together, so guest access requires a real IP.
    try:
        identity = resolve_identity(
            authorization,
            allow_guest=settings.guest_enabled(),
            client_ip=_client_ip(request),
        )
    except PermissionError as exc:
        return _error_frame(str(exc), code="unauthorized", status=401)

    if identity.is_guest and not settings.guest_enabled():
        return _error_frame("Please sign in to ask Avi.", code="guest_disabled", status=403)
    if identity.is_guest and not _client_ip(request):
        return _error_frame(
            "Avi needs a caller address for guest rate limiting.",
            code="guest_unavailable",
            status=400,
        )

    allowed, retry_after = check_and_count(identity.to_caller())
    if not allowed:
        from avi import metrics  # noqa: PLC0415

        caller = identity.to_caller()
        metrics.rate_limited(surface=caller.surface, scope=caller.scope)
        return JSONResponse(
            status_code=429,
            headers={"retry-after": str(max(1, retry_after))},
            content={
                "error": "You have reached the Avi limit for now. Please try again shortly.",
                "code": "rate_limited",
                "retryAfterSeconds": max(1, retry_after),
                "signInRequired": identity.is_guest,
            },
        )

    return StreamingResponse(
        _turn_stream(body, identity=identity),
        media_type="text/event-stream",
        headers=_sse_headers(),
    )


@app.post("/feedback")
async def feedback(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Any:
    """Store a thumb (and its explanation) for one Avi answer."""
    body = _parse_body(await request.body())
    if str(body.get("guest") or "").lower() in ("1", "true"):
        # Guests have no account to attach feedback to, and we store nothing.
        return {"stored": False, "reason": "guest"}
    try:
        identity = resolve_identity(authorization)
    except PermissionError as exc:
        return _error_frame(str(exc), code="unauthorized", status=401)

    from avi.feedback import record_feedback  # noqa: PLC0415

    try:
        item = record_feedback(identity.user_id, body)
    except ValueError as exc:
        return _error_frame(str(exc), code="invalid", status=400)
    return {"stored": True, "runId": item.get("runId")}


@app.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> Any:
    """Replay a stored Avi conversation (owner-scoped)."""
    try:
        identity = resolve_identity(authorization)
    except PermissionError as exc:
        return _error_frame(str(exc), code="unauthorized", status=401)

    from data.repositories import avi as avi_repo  # noqa: PLC0415

    item = avi_repo.get_conversation(identity.user_id, conversation_id)
    if not item:
        return _error_frame("Conversation not found.", code="not_found", status=404)
    transcript = avi_repo.get_transcript(identity.user_id, conversation_id)
    return {"conversation": item, "turns": transcript.get("turns") or []}


@app.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    authorization: str | None = Header(default=None),
) -> Any:
    try:
        identity = resolve_identity(authorization)
    except PermissionError as exc:
        return _error_frame(str(exc), code="unauthorized", status=401)

    from data.repositories import avi as avi_repo  # noqa: PLC0415

    if not avi_repo.get_conversation(identity.user_id, conversation_id):
        return _error_frame("Conversation not found.", code="not_found", status=404)
    avi_repo.delete_conversation(identity.user_id, conversation_id)
    return {"deleted": True}


if __name__ == "__main__":
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("AVI_PORT") or "8091"),
        log_level=os.environ.get("AVI_LOG_LEVEL", "info"),
    )

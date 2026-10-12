"""Avi's guest Lambda — the stateless ingress for unauthenticated callers.

Why this exists as its own function rather than a route on the agent service:

* A guest needs **no tools and no session**, so booting a MicroVM (a 2.3 s cold
  start and a per-session cost) to answer "what does this button do" is waste.
* API Gateway HTTP APIs cannot stream and cap an integration at 30 s. A Lambda
  **Function URL in RESPONSE_STREAM mode** streams tokens immediately, which is
  what makes the guest experience feel as quick as the signed-in one.
* Nothing is persisted: no transcript, no trace, no feedback. That is the whole
  point of the guest path, and keeping it in a separate function makes that
  property structural rather than a conditional.

Invoked by the Function URL with an AWS_PROXY-2.0 event and
``invokeMode = RESPONSE_STREAM``. The response is a stream of the platform's SSE
frames, identical to the agent service, so the widget does not branch.

Environment:
    AVI_GUEST_ENABLED     turn guests off entirely (the admin flag wins too)
    AVI_SESSION_SECRET    unused here; guests have no session
    AVI_MODEL             answer model for the direct path
    AVI_CLASSIFIER_MODEL  classifier model
    BEDROCK_REGION        Bedrock region
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
from typing import Any, Iterator

# The packaged zip flattens everything to the root (see the Makefile), so the
# shared packages and this service's own package are importable directly.
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from avi import examples, metrics, prompts, retrieval, settings  # noqa: E402
from avi.classifier import Classifier  # noqa: E402
from avi.frames import (  # noqa: E402
    STAGE_INTENT,
    STAGE_KNOWLEDGE,
    STAGE_LINKS,
    FrameWriter,
    sse,
)
from avi.llm import stream_direct  # noqa: E402

#: CloudFront/Function URLs cap a streaming response at 20 MB; a refusal or a
#: short answer is a few KB, so this only matters as a runaway guard.
MAX_ANSWER_CHARS = 8_000


class _GuestCaller:
    """A stable, hashed bucket for rate limiting (raw IP is never stored)."""

    def __init__(self, event: dict[str, Any]) -> None:
        self.ip = _client_ip(event)
        self.key = _guest_key(self.ip)


def _client_ip(event: dict[str, Any]) -> str:
    headers = {str(k).lower(): v for k, v in (event.get("headers") or {}).items()}
    forwarded = str(headers.get("x-forwarded-for") or "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    request_context = event.get("requestContext") or {}
    http = request_context.get("http") or {}
    return str(http.get("sourceIp") or "")


def _guest_key(ip: str) -> str:
    import hashlib  # noqa: PLC0415

    salt = os.environ.get("AVI_GUEST_SALT", "avi")
    return "guest_" + hashlib.sha256(f"{salt}|{ip or 'unknown'}".encode()).hexdigest()[:24]


def _parse_body(event: dict[str, Any]) -> dict[str, Any]:
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64  # noqa: PLC0415

        raw = base64.b64decode(raw).decode("utf-8", "replace")
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _clean_history(history: Any) -> list[dict[str, str]]:
    if not isinstance(history, list):
        return []
    cleaned: list[dict[str, str]] = []
    for item in history[:20]:
        if isinstance(item, dict) and item.get("role") in ("user", "assistant"):
            content = str(item.get("content") or "").strip()
            if content:
                cleaned.append({"role": str(item["role"]), "content": content[:2000]})
    return cleaned


def _frames(
    body: dict[str, Any], caller: _GuestCaller
) -> Iterator[dict[str, Any]]:
    """Produce the guest frames: classify, then answer or nudge. Nothing stored."""
    question = str(body.get("question") or body.get("input") or "").strip()
    route = str(body.get("route") or "")[:200]
    model = str(body.get("model") or "") or settings.model()
    classifier_model = settings.classifier_model()

    writer = FrameWriter(
        run_id=f"avirun_g{int(time.time() * 1000)}",
        model=model,
        entry_route=route,
        is_guest=True,
    )
    yield writer.run_started()
    # The same live-progress frames the signed-in path emits, so the widget renders
    # one experience rather than branching on who is asking.
    yield writer.stage(STAGE_INTENT, "Working out what you're asking")

    classifier = Classifier(model_id=classifier_model)
    started = time.perf_counter()
    verdict = classifier.classify(question, route=route)
    classifier_ms = int((time.perf_counter() - started) * 1000)
    yield verdict.to_frame()

    usage_in = 0
    usage_out = 0
    answer_chars = 0

    def on_usage(tin: int, tout: int) -> None:
        nonlocal usage_in, usage_out
        usage_in = max(usage_in, tin)
        usage_out = max(usage_out, tout)

    if not verdict.is_platform:
        prompt = prompts.off_topic_prompt(question, route, verdict.examples)
        max_tokens = 220
    elif verdict.is_smalltalk:
        prompt = prompts.greeting_prompt(route)
        max_tokens = 160
    else:
        # A platform question is the signed-in experience's job: the guest path
        # has no knowledge index of its own to search here, so it answers from the
        # page catalogue and invites sign-in for anything account-specific.
        yield writer.stage(STAGE_KNOWLEDGE, "Searching the platform docs")
        passages, diagnostic = _guest_retrieval(question)
        metrics.retrieval(diagnostic, surface="guest")
        if passages:
            yield writer.stage(
                STAGE_LINKS,
                "Choosing the pages to cite",
                detail=f"{len(passages)} matched",
            )
        prompt = prompts.build_system_prompt(
            passages=retrieval.as_prompt_passages(passages),
            answer_mode="summarize",
            route=route,
            is_guest=True,
        )
        max_tokens = 500

    try:
        for delta in stream_direct(
            prompt,
            question,
            model=model,
            max_tokens=max_tokens,
            client=None,
            on_usage=on_usage,
        ):
            if answer_chars >= MAX_ANSWER_CHARS:
                break
            answer_chars += len(delta)
            frame = writer.text_delta(delta)
            if frame:
                compose = writer.composing()
                if compose:
                    yield compose
                yield frame
    except Exception as exc:  # noqa: BLE001 - a failed guest answer is still friendly
        yield writer.failed(
            "I could not reach my model just now. Please try again in a moment.",
            retryable=True,
        )
        metrics.turn(
            surface="guest",
            model=model,
            intent_kind=verdict.kind,
            intent_stage=verdict.stage,
            latency_ms=writer.latency_ms,
            ttft_ms=writer.ttft_ms,
            tokens_in=usage_in,
            tokens_out=usage_out,
            source_count=0,
            tool_calls=0,
            refused=not verdict.is_platform,
            failed=True,
            classifier_latency_ms=classifier_ms,
        )
        _ = exc
        return

    writer.usage.input_tokens = usage_in
    writer.usage.output_tokens = usage_out
    metrics.turn(
        surface="guest",
        model=model,
        intent_kind=verdict.kind,
        intent_stage=verdict.stage,
        latency_ms=writer.latency_ms,
        ttft_ms=writer.ttft_ms,
        tokens_in=usage_in,
        tokens_out=usage_out,
        source_count=0,
        tool_calls=0,
        refused=not verdict.is_platform,
        classifier_latency_ms=classifier_ms,
    )
    yield writer.completed(
        stop_reason="off_topic" if not verdict.is_platform else "end_turn"
    )


def _guest_retrieval(question: str) -> tuple[list[Any], dict[str, Any]]:
    """Guest retrieval: same platform index, no user scope, never cached per user."""
    try:
        return retrieval.search(question, top_k=5, audience="user")
    except Exception as exc:  # noqa: BLE001 - a guest never sees a retrieval error
        return [], {"stage": "guest-retrieval-failed", "error": str(exc)[:200]}


def _stream(event: dict[str, Any]) -> Iterator[bytes]:
    """Yield the SSE bytes for one guest turn."""
    body = _parse_body(event)
    caller = _GuestCaller(event)

    try:
        for frame in _frames(body, caller):
            yield sse(frame).encode("utf-8")
    except Exception:  # noqa: BLE001 - always terminate the stream cleanly
        print(traceback.format_exc(), file=sys.stderr)
        writer = FrameWriter(run_id="avirun_guest_error", model=settings.model())
        yield sse(writer.failed("Something went wrong. Please try again.")).encode("utf-8")


def _error_response(status: int, code: str, message: str, *, retry_after: int = 0) -> dict[str, Any]:
    headers = {"content-type": "application/json", "cache-control": "no-store"}
    if retry_after:
        headers["retry-after"] = str(retry_after)
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps({"error": message, "code": code, "retryAfterSeconds": retry_after or None}),
    }


def lambda_handler(event: dict[str, Any], context: Any = None) -> Any:
    """Function URL entry point (RESPONSE_STREAM invoke mode)."""
    if not settings.enabled():
        return _error_response(503, "disabled", "Avi is temporarily unavailable.")
    if not settings.guest_enabled():
        return _error_response(403, "guest_disabled", "Sign in to ask Avi.")

    body = _parse_body(event)
    question = str(body.get("question") or body.get("input") or "").strip()
    if not question:
        return _error_response(400, "empty", "Ask me something about the platform.")
    limit = settings.max_input_chars()
    if len(question) > limit:
        return _error_response(
            413, "too_long", f"That question is longer than {limit} characters."
        )

    # ---- rate limit (per IP hash) --------------------------------------
    from avi import limits  # noqa: PLC0415

    caller = _GuestCaller(event)
    allowed, retry_after = limits.check_and_count(
        limits.Caller(key=caller.key, surface=limits.SURFACE_GUEST)
    )
    if not allowed:
        metrics.rate_limited(surface="guest", scope="guest")
        return _error_response(
            429,
            "rate_limited",
            "That is a lot of questions! Sign in to keep going, or try again shortly.",
            retry_after=retry_after,
        )

    # ---- stream --------------------------------------------------------
    from avi.streaming import stream_response  # noqa: PLC0415

    return stream_response(_stream(event))

"""Langfuse tracing for the agent runtime.

Langfuse is the single tracing backend for the AgentCore worker. The Langfuse
SDK owns the OpenTelemetry ``TracerProvider``, so Strands' auto-instrumented
spans (the agent loop, generations and tool calls) attach to it automatically —
there is no separate ``StrandsTelemetry`` exporter. AgentCore's own ADOT
exporter is turned off with ``DISABLE_ADOT_OBSERVABILITY=true`` so traces are
not double-exported.

Tracing is opt-in through the environment: without ``LANGFUSE_PUBLIC_KEY`` and
``LANGFUSE_SECRET_KEY`` every function here is a no-op, so local dev and unit
tests are unaffected.

``LANGFUSE_BASE_URL`` must be set (even to the cloud default) because Strands
detects Langfuse by looking for the string "langfuse" in ``LANGFUSE_BASE_URL`` /
``OTEL_EXPORTER_OTLP_ENDPOINT``; that is what switches it to Langfuse-friendly
span attributes.
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import Any, Iterator

_initialized = False


def _quiet_known_noise() -> None:
    """Silence two known-benign logs that would otherwise spam every run.

    * ``opentelemetry.context``: the runtime streams through an async generator
      that AgentCore bridges across a worker loop. When a client disconnects the
      generator is closed (``GeneratorExit``) in a different execution context,
      so OpenTelemetry's public ``context.detach`` logs "Token was created in a
      different Context" for every open span (ours and Strands'). The detach is
      best-effort and the leaked attachment lives in a per-request task context
      that is discarded. Strands uses the public ``use_span`` internally, so the
      only place to silence it is the logger.
    * ``strands.models.openai``: warns that ``reasoningContent`` is dropped in
      multi-turn Chat Completions calls. Strands filters those blocks itself, so
      the warning is expected noise on every follow-up turn.
    """
    logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
    logging.getLogger("strands.models.openai").setLevel(logging.ERROR)


def enabled() -> bool:
    """True when Langfuse credentials are configured."""
    return bool(
        (os.environ.get("LANGFUSE_PUBLIC_KEY") or "").strip()
        and (os.environ.get("LANGFUSE_SECRET_KEY") or "").strip()
    )


def init_tracing() -> None:
    """Initialise Langfuse tracing once, before the AgentCore app is created.

    Must run before ``BedrockAgentCoreApp()`` so the AgentCore baggage span
    processor registers on the Langfuse tracer provider, and before any Strands
    ``Agent`` is built so its tracer picks up that provider.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True
    _quiet_known_noise()
    if not enabled():
        return
    try:
        from langfuse import get_client

        get_client()
    except Exception as exc:  # noqa: BLE001 - tracing must never block a run
        print(f"[observability] Langfuse init failed: {exc}", flush=True)
        return
    _install_public_processor()


def _install_public_processor() -> None:
    """Stamp every span with ``langfuse.trace.public = true``.

    Langfuse decides a trace's ``public`` flag from the observations it ingests,
    and only reliably honors it when the flag is present on the span it sees
    first. Our root observation ends last, so a child that arrives before it
    would leave the trace non-public. Stamping every span makes the flag
    independent of export order (and of which span is the root).
    """
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.trace import SpanProcessor

        class _PublicSpanProcessor(SpanProcessor):
            def on_start(self, span: Any, parent_context: Any = None) -> None:
                try:
                    span.set_attribute("langfuse.trace.public", True)
                except Exception:  # noqa: BLE001 - must never break a run
                    pass

        provider = otel_trace.get_tracer_provider()
        provider.add_span_processor(_PublicSpanProcessor())
    except Exception as exc:  # noqa: BLE001 - best-effort
        print(f"[observability] Public-trace processor not installed: {exc}", flush=True)


class _NoopObservation:
    """Stand-in for a Langfuse observation when tracing is disabled."""

    def update(self, **_: Any) -> None:
        pass


@contextlib.contextmanager
def trace_attributes(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    trace_name: str | None = None,
) -> Iterator[None]:
    """Propagate user/session/tags/metadata/name to the trace and its observations."""
    if not enabled():
        yield
        return

    cm = None
    try:
        from langfuse import get_client

        try:
            from langfuse import propagate_attributes

            cm = propagate_attributes(
                user_id=user_id,
                session_id=session_id,
                tags=tags,
                metadata=metadata,
                trace_name=trace_name,
            )
        except ImportError:
            # Older SDKs have no propagate_attributes; set them on the trace.
            get_client().update_current_trace(
                user_id=user_id,
                session_id=session_id,
                tags=tags,
                metadata=metadata,
            )
    except Exception:  # noqa: BLE001 - attribute propagation is best-effort
        cm = None

    if cm is None:
        yield
        return
    with cm:
        yield


@contextlib.contextmanager
def run_trace(
    name: str,
    *,
    input: Any = None,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> Iterator[Any]:
    """Root observation for one agent run; yields a span-like object.

    Everything created inside the ``with`` block (the planner, model calls, tool
    invocations) nests under this trace. Yields a no-op object when tracing is
    off, so callers can always call ``.update(...)``.
    """
    if not enabled():
        yield _NoopObservation()
        return

    try:
        from langfuse import get_client

        langfuse = get_client()
    except Exception as exc:  # noqa: BLE001
        print(f"[observability] Langfuse unavailable: {exc}", flush=True)
        yield _NoopObservation()
        return

    with trace_attributes(
        user_id=user_id,
        session_id=session_id,
        tags=tags,
        metadata=metadata,
        trace_name=name,
    ):
        try:
            # A manual observation (not the context-manager variant): we attach
            # its span context ourselves so the detach can be done *safely*.
            observation = langfuse.start_observation(
                as_type="agent", name=name, input=input
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[observability] Trace start failed: {exc}", flush=True)
            yield _NoopObservation()
            return
        token = _attach_span(observation)
        try:
            yield observation
        finally:
            try:
                observation.end()
            except Exception:  # noqa: BLE001
                pass
            _detach_safely(token)


def _attach_span(observation: Any) -> Any:
    """Make ``observation`` the current span so child spans nest under it."""
    try:
        from opentelemetry import context as otel_context
        from opentelemetry import trace as otel_trace

        otel_span = getattr(observation, "_otel_span", None)
        if otel_span is None:
            return None
        return otel_context.attach(otel_trace.set_span_in_context(otel_span))
    except Exception:  # noqa: BLE001 - tracing must never break a run
        return None


def _detach_safely(token: Any) -> None:
    """Detach an OTel context token without the public helper's error logging.

    OpenTelemetry tokens must be detached in the same execution context they
    were attached in. Our root span is attached inside an async generator that
    the AgentCore runtime drives across a worker loop; when the client
    disconnects, the generator is closed (``GeneratorExit``) in a different
    context and the public ``context.detach`` logs "Token was created in a
    different Context". The detach is best-effort and the leaked attachment lives
    in a per-request task context that is discarded, so we detach via the runtime
    directly and swallow the failure (the Langfuse SDK does the same for
    ``propagate_attributes``).
    """
    if token is None:
        return
    try:
        from opentelemetry.context import _RUNTIME_CONTEXT

        _RUNTIME_CONTEXT.detach(token)
    except Exception:  # noqa: BLE001 - harmless, per-request context
        pass


def flush() -> None:
    """Flush buffered spans (call at the end of a run; the container can suspend)."""
    if not enabled():
        return
    try:
        from langfuse import get_client

        get_client().flush()
    except Exception:  # noqa: BLE001
        pass


def trace_identity(
    observation: Any, *, make_public: bool = True
) -> tuple[str | None, str | None]:
    """Return ``(trace_id, trace_url)`` for the active run.

    Marks the trace public (so its URL opens without a Langfuse login) when
    ``make_public`` is set. Call while the root observation is still recording.
    Best-effort: returns ``(None, None)`` on any failure.
    """
    if not enabled():
        return None, None
    try:
        from langfuse import get_client

        langfuse = get_client()
        if make_public:
            try:
                observation.set_trace_as_public()
            except Exception:  # noqa: BLE001 - public flag is best-effort
                pass
        trace_id = langfuse.get_current_trace_id()
        if not trace_id:
            return None, None
        url = langfuse.get_trace_url(trace_id=trace_id)
        return str(trace_id), (str(url) if url else None)
    except Exception:  # noqa: BLE001 - tracing must never break a run
        return None, None

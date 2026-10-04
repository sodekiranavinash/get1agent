"""OpenTelemetry tracing for the agent runtime (AWS-native).

Strands auto-instruments the agent loop; this module opens **one root span per
run** and tags it with user/session/agent metadata. Export is handled by the
AgentCore Runtime's ADOT collector → **CloudWatch + X-Ray**, so no observability
vendor SDK is involved and there are no credentials to configure.

Set ``AGENT_TRACING_ENABLED=false`` to force a no-op (local unit tests). When no
OTel ``TracerProvider`` is configured the OpenTelemetry API returns a non-recording
span, so every helper here is naturally a safe no-op.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
from typing import Any, Iterator

_initialized = False


def _quiet_known_noise() -> None:
    """Silence benign logs that would otherwise spam every run."""
    logging.getLogger("opentelemetry.context").setLevel(logging.CRITICAL)
    logging.getLogger("strands.models.openai").setLevel(logging.ERROR)


def enabled() -> bool:
    """Tracing is on unless explicitly disabled."""
    return (os.environ.get("AGENT_TRACING_ENABLED") or "true").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _xray_direct_enabled() -> bool:
    """Local dev: export spans straight to X-Ray with the ambient credentials.

    Deployed runtimes rely on AgentCore's ADOT collector, so this is off unless
    ``AGENT_XRAY_EXPORT=true`` (set locally).
    """
    return (os.environ.get("AGENT_XRAY_EXPORT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _xray_trace_id(otel_trace_id: int) -> str:
    """Map a W3C (32-hex) trace id onto X-Ray's dashed ``1-xxxxxxxx-…`` id."""
    hex32 = format(otel_trace_id & ((1 << 128) - 1), "032x")
    return f"1-{hex32[:8]}-{hex32[8:]}"


class _XRaySpanExporter:
    """A minimal OTel exporter that writes span documents to X-Ray."""

    def __init__(self, region: str) -> None:
        self._region = region
        self._client: Any = None

    def _xray(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("xray", region_name=self._region)
        return self._client

    def export(self, spans: Any) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        documents: list[str] = []
        for span in spans:
            try:
                documents.append(self._document(span))
            except Exception:  # noqa: BLE001 - one bad span must not drop the batch
                continue
        if not documents:
            return SpanExportResult.SUCCESS
        try:
            self._xray().put_trace_segments(TraceSegmentDocuments=documents)
            return SpanExportResult.SUCCESS
        except Exception:  # noqa: BLE001 - X-Ray unavailability must not break a run
            return SpanExportResult.FAILURE

    @staticmethod
    def _document(span: Any) -> str:
        context = span.context
        start = (span.start_time or 0) / 1e9
        end = (span.end_time or span.start_time or 0) / 1e9
        document: dict[str, Any] = {
            "name": (span.name or "span")[:200],
            "id": format(context.span_id, "016x"),
            "trace_id": _xray_trace_id(context.trace_id),
            "start_time": start,
            "end_time": end,
        }
        parent = getattr(span, "parent", None)
        if parent is not None and getattr(parent, "span_id", 0):
            document["parent_id"] = format(parent.span_id, "016x")
        annotations: dict[str, Any] = {}
        for key, value in (span.attributes or {}).items():
            if len(annotations) >= 50:
                break
            if isinstance(value, bool):
                annotations[str(key)[:50]] = value
            elif isinstance(value, (int, float)):
                annotations[str(key)[:50]] = value
            elif isinstance(value, str):
                annotations[str(key)[:50]] = value[:1000]
        if annotations:
            document["annotations"] = annotations
        status = getattr(span, "status", None)
        if status is not None and getattr(status, "status_code", None) == 2:  # ERROR
            document["error"] = True
        return json.dumps(document)

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


def _install_xray_exporter() -> None:
    """Install a TracerProvider that exports to X-Ray (local dev only)."""
    try:
        from opentelemetry import trace as otel_trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception:  # noqa: BLE001
        return
    region = (
        os.environ.get("AGENT_XRAY_REGION")
        or os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or "ap-south-1"
    )
    service = os.environ.get("OTEL_SERVICE_NAME", "get1agent-agent-worker")
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(BatchSpanProcessor(_XRaySpanExporter(region)))
    otel_trace.set_tracer_provider(provider)


def init_tracing() -> None:
    """Initialise tracing attributes once, before the AgentCore app is created.

    Deployed: the TracerProvider/exporter is owned by AgentCore's ADOT runtime;
    we only set a service name (if unset) and quiet known noise. Local dev
    (``AGENT_XRAY_EXPORT=true``): install a direct X-Ray exporter so local runs
    produce real, pullable traces.
    """
    global _initialized
    if _initialized:
        return
    _initialized = True
    _quiet_known_noise()
    os.environ.setdefault("OTEL_SERVICE_NAME", "get1agent-agent-worker")
    if _xray_direct_enabled():
        _install_xray_exporter()


def _current_span() -> Any:
    try:
        from opentelemetry import trace as otel_trace

        return otel_trace.get_current_span()
    except Exception:  # noqa: BLE001 - tracing must never break a run
        return None


def _set(span: Any, key: str, value: Any) -> None:
    if span is None or value is None:
        return
    try:
        if isinstance(value, (bool, int, float, str)):
            span.set_attribute(key, value)
        elif isinstance(value, (list, tuple, set)):
            span.set_attribute(key, [str(item) for item in value])
        else:
            span.set_attribute(key, str(value))
    except Exception:  # noqa: BLE001
        pass


def _tag_span(
    span: Any,
    *,
    user_id: str | None,
    session_id: str | None,
    tags: list[str] | None,
    metadata: dict[str, Any] | None,
    trace_name: str | None,
) -> None:
    _set(span, "get1agent.user_id", user_id)
    _set(span, "get1agent.session_id", session_id)
    _set(span, "get1agent.trace_name", trace_name)
    if tags:
        _set(span, "get1agent.tags", tags)
    if metadata:
        try:
            _set(span, "get1agent.metadata", json.dumps(metadata)[:4000])
        except (TypeError, ValueError):
            pass


class _Observation:
    """Thin wrapper over an OTel span with a vendor-neutral ``update``."""

    def __init__(self, span: Any) -> None:
        self.span = span

    def update(self, **attributes: Any) -> None:
        for key, value in attributes.items():
            _set(self.span, f"get1agent.{key}", value)


@contextlib.contextmanager
def trace_attributes(
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    tags: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    trace_name: str | None = None,
) -> Iterator[None]:
    """Tag the current span (best-effort); yields immediately."""
    _tag_span(
        _current_span(),
        user_id=user_id,
        session_id=session_id,
        tags=tags,
        metadata=metadata,
        trace_name=trace_name,
    )
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
) -> Iterator[_Observation]:
    """Root span for one agent run; everything inside nests under it."""
    if not enabled():
        yield _Observation(None)
        return
    try:
        from opentelemetry import trace as otel_trace

        tracer = otel_trace.get_tracer("get1agent.agentflow")
    except Exception:  # noqa: BLE001
        yield _Observation(None)
        return

    with tracer.start_as_current_span(name) as span:
        _tag_span(
            span,
            user_id=user_id,
            session_id=session_id,
            tags=tags,
            metadata=metadata,
            trace_name=name,
        )
        if input is not None:
            _set(span, "get1agent.input", str(input)[:4000])
        yield _Observation(span)


def flush() -> None:
    """Flush buffered spans (the container can suspend between turns)."""
    try:
        from opentelemetry import trace as otel_trace

        provider = otel_trace.get_tracer_provider()
        force_flush = getattr(provider, "force_flush", None)
        if callable(force_flush):
            force_flush()
    except Exception:  # noqa: BLE001
        pass


def trace_identity(
    observation: Any = None, *, make_public: bool = True
) -> tuple[str | None, str | None]:
    """Return ``(trace_id, trace_url)`` for the active run.

    ``trace_url`` is ``None``: the trace lives in CloudWatch/X-Ray, and user-api
    mints a signed, expiring link for it. Best-effort: ``(None, None)`` on failure.
    """
    del make_public  # CloudWatch traces are not "published"; user-api signs links.
    span = getattr(observation, "span", None) or _current_span()
    if span is None:
        return None, None
    try:
        context = span.get_span_context()
        trace_id = getattr(context, "trace_id", 0)
        if not trace_id:
            return None, None
        # Local direct-to-X-Ray export uses the X-Ray dashed id (so the stored
        # id matches what BatchGetTraces expects); deployed runtimes keep the
        # plain OTel id (AgentCore's ADOT collector owns the mapping).
        if _xray_direct_enabled():
            return _xray_trace_id(trace_id), None
        return format(trace_id, "032x"), None
    except Exception:  # noqa: BLE001
        return None, None

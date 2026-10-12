"""Lambda response-streaming adapter.

The guest Lambda streams **SSE** from a Function URL configured with
``invokeMode = RESPONSE_STREAM``. Lambda's streaming API changed name and import
path across runtime generations, and the import is only available *inside* the
managed runtime (it is not a pip package), so this module probes the variants and
degrades to a buffered response rather than failing.

Degrading matters: a buffered guest answer is slightly worse (the text arrives at
once), while an ``ImportError`` would be a 502 on every guest question. The chosen
mode is reported on the response header and logged, so a deployment can confirm
which path it took.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Callable, Iterable

SSE_HEADERS = {
    "content-type": "text/event-stream; charset=utf-8",
    "cache-control": "no-cache, no-transform",
    "x-accel-buffering": "no",
}


def _probe() -> tuple[str, Callable[..., Any] | None]:
    """Find the runtime's streaming entry point. Returns ``(name, callable)``."""
    candidates: tuple[tuple[str, str, str], ...] = (
        # Python 3.13+ managed runtime (preferred, and the one prod will use).
        ("awslambda.streaming_response", "streaming_response", "awslambda-streaming"),
        # Older/alternative placement seen in 3.12 images.
        ("awslambda", "streaming_response", "awslambda-plain"),
        ("lambda_runtime", "streaming_response", "lambda_runtime"),
    )
    for module_name, attribute, label in candidates:
        try:
            module = __import__(module_name, fromlist=[attribute])
        except Exception:  # noqa: BLE001 - absent in dev and on other runtimes
            continue
        function = getattr(module, attribute, None)
        if callable(function):
            return label, function
    return "buffered", None


_STREAMER: tuple[str, Callable[..., Any] | None] | None = None


def mode() -> str:
    """Which streaming path this process will use (``buffered`` when none)."""
    global _STREAMER
    if _STREAMER is None:
        _STREAMER = _probe()
        print(
            json.dumps({"level": "info", "message": "avi guest streaming mode", "mode": _STREAMER[0]}),
            file=sys.stderr,
            flush=True,
        )
    return _STREAMER[0]


def stream_response(chunks: Iterable[bytes]) -> Any:
    """Return the Function URL response for an SSE byte stream."""
    label, function = _STREAMER or _probe()
    if function is not None:
        try:
            # The documented call shape: a content type plus the chunk iterator.
            return function(chunks, content_type="text/event-stream")
        except TypeError:
            # Some versions take only the iterator and read the content type from
            # a decorator or a header set on the response.
            try:
                return function(chunks)
            except Exception:  # noqa: BLE001 - fall through to buffering
                pass
        except Exception:  # noqa: BLE001
            pass

    payload = b"".join(chunks)
    return {
        "statusCode": 200,
        "headers": {**SSE_HEADERS, "x-avi-streaming": f"buffered({label})"},
        # A buffered Function URL response must be plain text (not base64), so the
        # SSE frames stay readable to the browser.
        "body": payload.decode("utf-8", "replace"),
        "isBase64Encoded": False,
    }


def is_streaming() -> bool:
    return mode() != "buffered"


def runtime_note() -> dict[str, Any]:
    """A diagnostic for the deployment smoke test."""
    return {
        "mode": mode(),
        "functionName": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", ""),
        "runtime": f"python{sys.version_info.major}.{sys.version_info.minor}",
    }

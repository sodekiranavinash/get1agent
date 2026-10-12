"""A lean Bedrock streaming client for the direct (non-agent) answer path.

The full agent path runs in the MicroVM container, where LangChain/Deep Agents are
already installed. The **guest Lambda must stay small** — a Function URL package
has a 250 MB unzipped ceiling and a cold start to pay — so this module talks to
Bedrock's Converse streaming API directly instead of bundling LangChain for one
call.

It is used for exactly the two cases that need no tools: the off-topic nudge and a
greeting. Both are a single model call with a system prompt, which is all this
client supports — deliberately, so it cannot grow into a second agent runtime.
"""

from __future__ import annotations

import os
from typing import Any, AsyncIterator, Callable, Iterable

DEFAULT_MAX_TOKENS = 600
DEFAULT_TEMPERATURE = 0.4


def _client() -> Any:
    import boto3  # noqa: PLC0415

    return boto3.client(
        "bedrock-runtime",
        region_name=(
            os.environ.get("BEDROCK_REGION")
            or os.environ.get("AWS_REGION")
            or "ap-south-1"
        ),
    )


def stream_direct(
    prompt: str,
    user_text: str,
    *,
    model: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    client: Any = None,
    on_usage: Callable[[int, int], None] | None = None,
) -> Iterable[str]:
    """Yield text deltas for one tool-free model call (synchronous).

    Synchronous on purpose: a Lambda streams by writing to the response stream from
    a normal handler, and the caller wraps this in whatever framing it needs.
    """
    runtime = client or _client()
    response = runtime.converse_stream(
        modelId=model,
        system=[{"text": prompt}],
        messages=[{"role": "user", "content": [{"text": user_text}]}],
        inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
    )
    for event in response.get("stream") or []:
        delta = event.get("contentBlockDelta")
        if delta:
            text = (delta.get("delta") or {}).get("text")
            if text:
                yield text
        metadata = event.get("metadata")
        if metadata and on_usage:
            usage = metadata.get("usage") or {}
            on_usage(
                int(usage.get("inputTokens") or 0), int(usage.get("outputTokens") or 0)
            )


async def astream_direct(
    prompt: str,
    user_text: str,
    *,
    model: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
    client: Any = None,
) -> AsyncIterator[str]:
    """Async wrapper (the agent service uses this; the Lambda uses the sync form)."""
    import asyncio  # noqa: PLC0415

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    sentinel = object()

    def produce() -> None:
        try:
            for text in stream_direct(
                prompt,
                user_text,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                client=client,
            ):
                loop.call_soon_threadsafe(queue.put_nowait, text)
        except Exception as exc:  # noqa: BLE001 - surfaced to the consumer
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    loop.run_in_executor(None, produce)
    while True:
        item = await queue.get()
        if item is sentinel:
            return
        if isinstance(item, Exception):
            raise item
        yield item

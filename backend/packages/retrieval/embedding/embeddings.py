from __future__ import annotations

import base64
import json
import os
import random
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from retrieval.embedding.config import IngestionConfig

_MAX_WORKERS = int(os.environ.get("EMBED_MAX_WORKERS", "4"))
_MAX_ATTEMPTS = int(os.environ.get("EMBED_MAX_ATTEMPTS", "6"))
_BASE_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 20.0

_RETRYABLE_ERROR_CODES = frozenset(
    {
        "ThrottlingException",
        "TooManyRequestsException",
        "ServiceUnavailableException",
        "ModelNotReadyException",
        "InternalServerException",
        "RequestTimeout",
    }
)


class EmbeddingError(RuntimeError):
    """A failed embedding request; ``retryable`` drives the backoff loop."""

    def __init__(
        self, message: str, *, status: int | None = None, retryable: bool = False
    ) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


def _bedrock_client(region: str) -> Any:
    import boto3
    from botocore.config import Config

    return boto3.client(
        "bedrock-runtime",
        region_name=region,
        config=Config(retries={"max_attempts": 8, "mode": "adaptive"}),
    )


def _is_retryable(error: BaseException) -> bool:
    if isinstance(error, EmbeddingError):
        return error.retryable
    from botocore.exceptions import ClientError

    if not isinstance(error, ClientError):
        return False
    code = error.response.get("Error", {}).get("Code", "")
    return code in _RETRYABLE_ERROR_CODES


def _throttle() -> None:
    """Honor the platform Bedrock rate limit, when configured.

    ``core.ratelimit_bedrock`` is best-effort: retrieval must never hard-depend
    on it, and any failure falls through to the normal (adaptive-retry) call.
    """
    try:
        from core import ratelimit_bedrock
    except Exception:  # noqa: BLE001 - optional shared dependency
        return
    try:
        ratelimit_bedrock.throttle()
    except Exception:  # noqa: BLE001 - never block embedding on the limiter
        return


def _with_retry(call: Callable[[], Any]) -> Any:
    for attempt in range(_MAX_ATTEMPTS):
        try:
            return call()
        except Exception as error:
            if attempt == _MAX_ATTEMPTS - 1 or not _is_retryable(error):
                raise
            backoff = min(
                _MAX_BACKOFF_SECONDS, _BASE_BACKOFF_SECONDS * 2**attempt
            )
            time.sleep(backoff + random.uniform(0, backoff))
    raise AssertionError("unreachable")


def _invoke_text(client: Any, model: str, text: str, dimensions: int) -> list[float]:
    """Embed one text with Titan Text Embeddings V2."""
    body = json.dumps(
        {"inputText": text, "dimensions": dimensions, "normalize": True}
    )
    response = client.invoke_model(
        modelId=model,
        body=body,
        accept="application/json",
        contentType="application/json",
    )
    return list(json.loads(response["body"].read())["embedding"])


def _invoke_image(client: Any, model: str, image: bytes, dimensions: int) -> list[float]:
    """Embed one image with Titan Multimodal Embeddings G1."""
    body = json.dumps(
        {
            "inputImage": base64.b64encode(image).decode("ascii"),
            "embeddingConfig": {"outputEmbeddingLength": dimensions},
        }
    )
    response = client.invoke_model(
        modelId=model,
        body=body,
        accept="application/json",
        contentType="application/json",
    )
    return list(json.loads(response["body"].read())["embedding"])


def _ollama_embed(texts: list[str], config: IngestionConfig) -> list[list[float]]:
    """Real embeddings from a local Ollama server (``/api/embed``)."""
    payload = json.dumps(
        {"model": config.local_embed_model, "input": texts}
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{config.local_embed_url}/api/embed",
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        body = json.loads(response.read())

    vectors = body.get("embeddings") or []
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Local embedding model {config.local_embed_model!r} returned "
            f"{len(vectors)} vectors for {len(texts)} inputs"
        )
    for vector in vectors:
        if len(vector) != config.embedding_dim:
            raise RuntimeError(
                f"Local embedding model {config.local_embed_model!r} returns "
                f"{len(vector)}-dim vectors but EMBED_DIM is {config.embedding_dim}"
            )
    return [[float(value) for value in vector] for vector in vectors]


def _run_parallel(fn, items: list) -> list[Any]:
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(items))) as pool:
        return list(pool.map(fn, items))


def _bedrock_embed_texts(
    texts: list[str], config: IngestionConfig
) -> list[list[float]]:
    client = _bedrock_client(config.bedrock_region)

    def embed_one(text: str) -> list[float]:
        _throttle()
        return _with_retry(
            lambda: _invoke_text(
                client, config.text_embed_model, text, config.embedding_dim
            )
        )

    return _run_parallel(embed_one, texts)


def _bedrock_embed_images(
    images: list[bytes], config: IngestionConfig
) -> list[list[float]]:
    client = _bedrock_client(config.bedrock_region)

    def embed_one(image: bytes) -> list[float]:
        _throttle()
        return _with_retry(
            lambda: _invoke_image(
                client, config.image_embed_model, image, config.embedding_dim
            )
        )

    return _run_parallel(embed_one, images)


def embed_texts(
    texts: list[str], config: IngestionConfig, *, input_type: str = "document"
) -> list[list[float]]:
    """Embed texts, reusing cached vectors for identical (model, input_type, text).

    Embeddings are deterministic, so the cache is keyed by a hash of the
    text/model and is global. Best-effort: any cache failure falls back to
    embedding directly.

    ``input_type`` is accepted for API compatibility (embeddings are shared for
    documents and queries); Titan embeds both the same way.
    """
    del input_type  # Titan has no document/query distinction
    if not texts:
        return []
    try:
        from core import cache
    except Exception:  # noqa: BLE001 - retrieval must not hard-depend on core
        cache = None  # type: ignore[assignment]
    if cache is None or not cache.enabled():
        return _embed_uncached(texts, config)

    keys = [
        cache.cache_key("emb", config.embed_mode, config.text_embed_model, text)
        for text in texts
    ]
    vectors = cache.get_many(keys)
    missing = [index for index, value in enumerate(vectors) if value is None]
    if missing:
        fresh = _embed_uncached([texts[index] for index in missing], config)
        ttl = cache.ttl("embedding", 2_592_000)  # 30 days
        cache.set_many(
            [(keys[index], fresh[position]) for position, index in enumerate(missing)],
            ttl,
        )
        for position, index in enumerate(missing):
            vectors[index] = fresh[position]
    return vectors


def _embed_uncached(
    texts: list[str], config: IngestionConfig
) -> list[list[float]]:
    if config.embed_mode == "local":
        return _ollama_embed(texts, config)
    return _bedrock_embed_texts(texts, config)


def embed_images(images: list[bytes], config: IngestionConfig) -> list[list[float]]:
    """Embed images with Titan Multimodal G1 (opt-in via ``EMBED_IMAGES``)."""
    if not images or not config.embed_images:
        return []
    if config.embed_mode == "local":
        # Local Ollama has no image-embedding model, so only text is indexed.
        return []
    return _bedrock_embed_images(images, config)

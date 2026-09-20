from __future__ import annotations

import base64
import json
import os
import random
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from retrieval.embedding.config import IngestionConfig

_MAX_WORKERS = int(os.environ.get("EMBED_MAX_WORKERS", "4"))
_MAX_ATTEMPTS = int(os.environ.get("EMBED_MAX_ATTEMPTS", "6"))
_BASE_BACKOFF_SECONDS = 0.5
_MAX_BACKOFF_SECONDS = 20.0

_VOYAGE_TIMEOUT_SECONDS = int(os.environ.get("VOYAGE_TIMEOUT_SECONDS", "120"))
# voyage-4-large caps a request at 120K tokens; 64 chunks keeps even the
# largest (1024-token) chunks under that limit.
_VOYAGE_BATCH_SIZE = int(os.environ.get("VOYAGE_BATCH_SIZE", "64"))
_VOYAGE_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

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


class VoyageError(RuntimeError):
    """A failed Voyage AI request; ``retryable`` drives the backoff loop."""

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
    if isinstance(error, VoyageError):
        return error.retryable
    from botocore.exceptions import ClientError

    if not isinstance(error, ClientError):
        return False
    code = error.response.get("Error", {}).get("Code", "")
    return code in _RETRYABLE_ERROR_CODES


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


def _image_media_type(blob: bytes) -> str:
    """Sniff one of the image types Voyage accepts from the magic bytes."""
    if blob.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if blob.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if blob.startswith(b"GIF87a") or blob.startswith(b"GIF89a"):
        return "image/gif"
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _voyage_post(path: str, payload: dict, config: IngestionConfig) -> dict:
    """POST ``payload`` to the Voyage API and return the parsed response.

    The key is read from ``VOYAGE_API_KEY`` here (not from the config) so it is
    never serialized into the Step Functions payload.
    """
    api_key = os.environ.get("VOYAGE_API_KEY", "").strip()
    if not api_key:
        raise VoyageError("VOYAGE_API_KEY is not configured")
    request = urllib.request.Request(
        f"{config.voyage_api_base_url}{path}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "accept": "application/json",
            "authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request, timeout=_VOYAGE_TIMEOUT_SECONDS
        ) as response:
            return json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read()[:500].decode("utf-8", "replace")
        message = f"Voyage API returned HTTP {exc.code}"
        try:
            parsed = json.loads(detail)
            message = str(parsed.get("detail") or parsed.get("error") or message)
        except ValueError:
            pass
        raise VoyageError(
            message,
            status=exc.code,
            retryable=exc.code in _VOYAGE_RETRYABLE_STATUS,
        ) from exc
    except urllib.error.URLError as exc:
        raise VoyageError(
            f"Could not reach Voyage: {exc.reason}", retryable=True
        ) from exc
    except ValueError as exc:
        raise VoyageError("Voyage returned invalid JSON") from exc


def _voyage_vectors(
    body: dict, expected: int, config: IngestionConfig, model: str
) -> list[list[float]]:
    data = body.get("data") or []
    vectors = [
        item.get("embedding") or []
        for item in sorted(data, key=lambda item: item.get("index", 0))
    ]
    if len(vectors) != expected:
        raise RuntimeError(
            f"Voyage model {model!r} returned {len(vectors)} vectors for "
            f"{expected} inputs"
        )
    for vector in vectors:
        if len(vector) != config.embedding_dim:
            raise RuntimeError(
                f"Voyage model {model!r} returns {len(vector)}-dim vectors but "
                f"EMBED_DIM is {config.embedding_dim}"
            )
    return [[float(value) for value in vector] for vector in vectors]


def _batches(items: list) -> list[list]:
    size = max(1, _VOYAGE_BATCH_SIZE)
    return [items[index : index + size] for index in range(0, len(items), size)]


def _voyage_embed_texts(
    texts: list[str], config: IngestionConfig, input_type: str
) -> list[list[float]]:
    def embed_batch(batch: list[str]) -> list[list[float]]:
        payload = {
            "input": batch,
            "model": config.text_embed_model,
            "input_type": input_type,
            "truncation": True,
            "output_dimension": config.embedding_dim,
            "output_dtype": "float",
        }
        body = _with_retry(lambda: _voyage_post("/embeddings", payload, config))
        return _voyage_vectors(body, len(batch), config, config.text_embed_model)

    return [
        vector
        for batch_vectors in _run_parallel(embed_batch, _batches(texts))
        for vector in batch_vectors
    ]


def _voyage_embed_images(
    images: list[bytes], config: IngestionConfig
) -> list[list[float]]:
    def embed_batch(batch: list[bytes]) -> list[list[float]]:
        inputs = [
            {
                "content": [
                    {
                        "type": "image_base64",
                        "image_base64": (
                            f"data:{_image_media_type(image)};base64,"
                            f"{base64.b64encode(image).decode('ascii')}"
                        ),
                    }
                ]
            }
            for image in batch
        ]
        payload = {
            "inputs": inputs,
            "model": config.image_embed_model,
            "input_type": "document",
            "output_dimension": config.embedding_dim,
            "output_dtype": "float",
        }
        body = _with_retry(
            lambda: _voyage_post("/multimodalembeddings", payload, config)
        )
        return _voyage_vectors(body, len(batch), config, config.image_embed_model)

    return [
        vector
        for batch_vectors in _run_parallel(embed_batch, _batches(images))
        for vector in batch_vectors
    ]


def embed_texts(
    texts: list[str], config: IngestionConfig, *, input_type: str = "document"
) -> list[list[float]]:
    if not texts:
        return []
    if config.embed_mode == "bedrock":
        client = _bedrock_client(config.bedrock_region)
        return _run_parallel(
            lambda text: _with_retry(
                lambda: _invoke_text(
                    client, config.text_embed_model, text, config.embedding_dim
                )
            ),
            texts,
        )
    if config.embed_mode == "voyage":
        return _voyage_embed_texts(texts, config, input_type)
    return _ollama_embed(texts, config)


def embed_images(images: list[bytes], config: IngestionConfig) -> list[list[float]]:
    if not images:
        return []
    if config.embed_mode == "bedrock":
        client = _bedrock_client(config.bedrock_region)
        return _run_parallel(
            lambda image: _with_retry(
                lambda: _invoke_image(
                    client, config.image_embed_model, image, config.embedding_dim
                )
            ),
            images,
        )
    if config.embed_mode == "voyage":
        return _voyage_embed_images(images, config)
    # Local Ollama has no image-embedding model, so only text is indexed.
    return []

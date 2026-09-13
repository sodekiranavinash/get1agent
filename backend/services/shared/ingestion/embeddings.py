from __future__ import annotations

import base64
import json
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from shared.ingestion.config import IngestionConfig

_MAX_WORKERS = 4


def _bedrock_client(region: str) -> Any:
    import boto3

    return boto3.client("bedrock-runtime", region_name=region)


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


def _run_parallel(fn, items: list) -> list[list[float]]:
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(items))) as pool:
        return list(pool.map(fn, items))


def embed_texts(texts: list[str], config: IngestionConfig) -> list[list[float]]:
    if not texts:
        return []
    if config.embed_mode == "bedrock":
        client = _bedrock_client(config.bedrock_region)
        return _run_parallel(
            lambda text: _invoke_text(
                client, config.text_embed_model, text, config.embedding_dim
            ),
            texts,
        )
    return _ollama_embed(texts, config)


def embed_images(images: list[bytes], config: IngestionConfig) -> list[list[float]]:
    if not images:
        return []
    if config.embed_mode == "bedrock":
        client = _bedrock_client(config.bedrock_region)
        return _run_parallel(
            lambda image: _invoke_image(
                client, config.image_embed_model, image, config.embedding_dim
            ),
            images,
        )
    # Local Ollama has no image-embedding model, so only text is indexed.
    return []

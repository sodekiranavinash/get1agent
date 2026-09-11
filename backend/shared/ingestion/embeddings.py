from __future__ import annotations

import base64
import hashlib
import json
import math
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from shared.ingestion.config import IngestionConfig

_MAX_WORKERS = 4


def _local_vector(seed: bytes, dimensions: int) -> list[float]:
    values: list[float] = []
    counter = 0
    while len(values) < dimensions:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for offset in range(0, len(digest), 4):
            if len(values) >= dimensions:
                break
            integer = int.from_bytes(digest[offset : offset + 4], "big")
            values.append((integer / 0xFFFFFFFF) * 2 - 1)
        counter += 1
    norm = math.sqrt(sum(value * value for value in values)) or 1.0
    return [value / norm for value in values]


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


def _run_parallel(fn, items: list) -> list[list[float]]:
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(items))) as pool:
        return list(pool.map(fn, items))


def embed_texts(texts: list[str], config: IngestionConfig) -> list[list[float]]:
    if not texts:
        return []
    if config.embed_mode != "bedrock":
        return [
            _local_vector(text.encode("utf-8"), config.embedding_dim)
            for text in texts
        ]

    client = _bedrock_client(config.bedrock_region)
    return _run_parallel(
        lambda text: _invoke_text(
            client, config.text_embed_model, text, config.embedding_dim
        ),
        texts,
    )


def embed_images(images: list[bytes], config: IngestionConfig) -> list[list[float]]:
    if not images:
        return []
    if config.embed_mode != "bedrock":
        return [
            _local_vector(image[:4096], config.embedding_dim) for image in images
        ]

    client = _bedrock_client(config.bedrock_region)
    return _run_parallel(
        lambda image: _invoke_image(
            client, config.image_embed_model, image, config.embedding_dim
        ),
        images,
    )

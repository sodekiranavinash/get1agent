from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields, replace

DEFAULT_TEXT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
DEFAULT_IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_LOCAL_EMBED_MODEL = "mxbai-embed-large"
DEFAULT_LOCAL_EMBED_URL = "http://ollama:11434"

# Values a knowledge base may choose from. Keep in sync with the UI
# (frontend/src/lib/knowledgeBases.ts).
SUPPORTED_TEXT_EMBED_MODELS = (DEFAULT_TEXT_EMBED_MODEL,)
SUPPORTED_IMAGE_EMBED_MODELS = (DEFAULT_IMAGE_EMBED_MODEL,)
SUPPORTED_CHUNK_SIZES = (512, 1024, 2048)
SUPPORTED_CHUNK_OVERLAPS = (0, 128, 256)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class IngestionConfig:
    embed_mode: str
    text_embed_model: str
    image_embed_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    max_images_per_doc: int
    min_image_bytes: int
    min_image_dimension: int
    bedrock_region: str
    local_embed_url: str
    local_embed_model: str


def load_config() -> IngestionConfig:
    """Read pipeline settings from the environment on every call.

    ``EMBED_MODE=bedrock`` uses Titan (production). ``EMBED_MODE=local`` calls a
    local Ollama server, so embeddings are real vectors without AWS.
    """
    region = (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or "ap-south-1"
    )
    return IngestionConfig(
        embed_mode=os.environ.get("EMBED_MODE", "bedrock").strip().lower(),
        text_embed_model=os.environ.get(
            "TEXT_EMBED_MODEL", DEFAULT_TEXT_EMBED_MODEL
        ),
        image_embed_model=os.environ.get(
            "IMAGE_EMBED_MODEL", DEFAULT_IMAGE_EMBED_MODEL
        ),
        embedding_dim=_int("EMBED_DIM", DEFAULT_EMBEDDING_DIM),
        chunk_size=_int("CHUNK_SIZE", 1024),
        chunk_overlap=_int("CHUNK_OVERLAP", 128),
        max_images_per_doc=_int("MAX_IMAGES_PER_DOC", 50),
        min_image_bytes=_int("MIN_IMAGE_BYTES", 5 * 1024),
        min_image_dimension=_int("MIN_IMAGE_DIMENSION", 100),
        bedrock_region=region,
        local_embed_url=os.environ.get(
            "LOCAL_EMBED_URL", DEFAULT_LOCAL_EMBED_URL
        ).rstrip("/"),
        local_embed_model=os.environ.get(
            "LOCAL_EMBED_MODEL", DEFAULT_LOCAL_EMBED_MODEL
        ),
    )


def config_to_dict(config: IngestionConfig) -> dict:
    """Serialize a config for the Step Functions payload (per-KB overrides).

    The embed worker runs outside the VPC, so it cannot read per-KB settings
    from RDS; the extract stage loads them and passes them along here.
    """
    return asdict(config)


def config_from_dict(base: IngestionConfig, data: dict | None) -> IngestionConfig:
    """Overlay a payload config onto the worker's env defaults."""
    if not data:
        return base
    known = {item.name for item in fields(IngestionConfig)}
    overrides = {
        key: value
        for key, value in data.items()
        if key in known and value is not None
    }
    return replace(base, **overrides)

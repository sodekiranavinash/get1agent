from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields, replace

# Amazon Bedrock (Amazon Titan) is the only hosted embedding backend. The
# ``local`` mode (Ollama) exists purely for offline development on Floci.
DEFAULT_TEXT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
DEFAULT_IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_LOCAL_EMBED_MODEL = "mxbai-embed-large"
DEFAULT_LOCAL_EMBED_URL = "http://ollama:11434"

# Values a knowledge base may choose from. Keep in sync with the UI
# (frontend/src/lib/knowledgeBases.ts).
SUPPORTED_TEXT_EMBED_MODELS = (DEFAULT_TEXT_EMBED_MODEL,)
SUPPORTED_IMAGE_EMBED_MODELS = (DEFAULT_IMAGE_EMBED_MODEL,)
SUPPORTED_CHUNK_SIZES = (256, 384, 512, 768, 1024)
SUPPORTED_CHUNK_OVERLAPS = (0, 32, 64, 128, 256)

# Child chunks are embedded and searched; parents are returned for context.
# 512 is the research-backed default (Azure/Pinecone) and stays within the
# Titan V2 window.
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
# Fixed-size parent window for non-paginated formats. Paginated formats use the
# source page as the parent instead.
DEFAULT_PARENT_SIZE = 1500
# Image embeddings are computed at ingest but never searched, and Titan
# Multimodal G1 is rate-limited to 20 RPM, so they are off by default.
DEFAULT_EMBED_IMAGES = False


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() not in ("0", "false", "no", "off")


@dataclass(frozen=True)
class IngestionConfig:
    embed_mode: str
    text_embed_model: str
    image_embed_model: str
    embedding_dim: int
    chunk_size: int
    chunk_overlap: int
    parent_size: int
    max_images_per_doc: int
    min_image_bytes: int
    min_image_dimension: int
    embed_images: bool
    bedrock_region: str
    local_embed_url: str
    local_embed_model: str


def load_config() -> IngestionConfig:
    """Read pipeline settings from the environment on every call.

    ``EMBED_MODE=bedrock`` (the default) calls Amazon Titan embeddings through
    ``bedrock-runtime``. ``EMBED_MODE=local`` calls a local Ollama server so
    embeddings work offline (Floci, tests). Image embeddings are produced only
    when ``EMBED_IMAGES=true`` (Bedrock only).
    """
    region = (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or "ap-south-1"
    )
    embed_mode = os.environ.get("EMBED_MODE", "bedrock").strip().lower()
    if embed_mode == "local":
        # The local backend ignores per-KB model ids; it uses one Ollama model
        # for text and does not produce image embeddings.
        text_embed_model = os.environ.get(
            "LOCAL_EMBED_MODEL", DEFAULT_LOCAL_EMBED_MODEL
        )
        image_embed_model = text_embed_model
    else:
        text_embed_model = os.environ.get(
            "TEXT_EMBED_MODEL", DEFAULT_TEXT_EMBED_MODEL
        )
        image_embed_model = os.environ.get(
            "IMAGE_EMBED_MODEL", DEFAULT_IMAGE_EMBED_MODEL
        )
    return IngestionConfig(
        embed_mode=embed_mode,
        text_embed_model=text_embed_model,
        image_embed_model=image_embed_model,
        embedding_dim=_int("EMBED_DIM", DEFAULT_EMBEDDING_DIM),
        chunk_size=_int("CHUNK_SIZE", DEFAULT_CHUNK_SIZE),
        chunk_overlap=_int("CHUNK_OVERLAP", DEFAULT_CHUNK_OVERLAP),
        parent_size=_int("PARENT_SIZE", DEFAULT_PARENT_SIZE),
        max_images_per_doc=_int("MAX_IMAGES_PER_DOC", 50),
        min_image_bytes=_int("MIN_IMAGE_BYTES", 5 * 1024),
        min_image_dimension=_int("MIN_IMAGE_DIMENSION", 100),
        embed_images=_bool("EMBED_IMAGES", DEFAULT_EMBED_IMAGES),
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
    directly; the extract stage loads them and passes them along here.
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

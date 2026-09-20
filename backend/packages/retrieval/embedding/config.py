from __future__ import annotations

import os
from dataclasses import asdict, dataclass, fields, replace

DEFAULT_TEXT_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
DEFAULT_IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
DEFAULT_EMBEDDING_DIM = 1024
DEFAULT_LOCAL_EMBED_MODEL = "mxbai-embed-large"
DEFAULT_LOCAL_EMBED_URL = "http://ollama:11434"
# Voyage AI (https://docs.voyageai.com) — used when EMBED_MODE=voyage, e.g. when
# Bedrock is not available yet. The API key is read from VOYAGE_API_KEY by the
# embedding client and is deliberately never part of this config, because the
# config is serialized into the Step Functions payload.
DEFAULT_VOYAGE_TEXT_MODEL = "voyage-4-large"
DEFAULT_VOYAGE_MULTIMODAL_MODEL = "voyage-multimodal-3.5"
DEFAULT_VOYAGE_API_BASE_URL = "https://api.voyageai.com/v1"

# Values a knowledge base may choose from. Keep in sync with the UI
# (frontend/src/lib/knowledgeBases.ts). Voyage is the active backend; the Titan
# ids are kept for the dormant ``EMBED_MODE=bedrock`` path.
SUPPORTED_TEXT_EMBED_MODELS = (DEFAULT_VOYAGE_TEXT_MODEL,)
SUPPORTED_IMAGE_EMBED_MODELS = (DEFAULT_VOYAGE_MULTIMODAL_MODEL,)
SUPPORTED_CHUNK_SIZES = (256, 384, 512, 768, 1024)
SUPPORTED_CHUNK_OVERLAPS = (0, 32, 64, 128, 256)

# Child chunks are embedded and searched; parents are returned for context.
# 512 is the research-backed default (Azure/Pinecone) and stays within every
# embedder window in production (Titan V2); local mxbai truncates past 512.
DEFAULT_CHUNK_SIZE = 512
DEFAULT_CHUNK_OVERLAP = 64
# Fixed-size parent window for non-paginated formats. Paginated formats use the
# source page as the parent instead.
DEFAULT_PARENT_SIZE = 1500


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
    parent_size: int
    max_images_per_doc: int
    min_image_bytes: int
    min_image_dimension: int
    bedrock_region: str
    local_embed_url: str
    local_embed_model: str
    voyage_api_base_url: str


def load_config() -> IngestionConfig:
    """Read pipeline settings from the environment on every call.

    ``EMBED_MODE=voyage`` (the default) calls the Voyage AI embeddings API
    (text and multimodal) using ``VOYAGE_API_KEY``. ``EMBED_MODE=local`` calls a
    local Ollama server, so embeddings are real vectors without any external
    API. ``EMBED_MODE=bedrock`` uses Titan — kept for when Bedrock access is
    added later.
    """
    region = (
        os.environ.get("BEDROCK_REGION")
        or os.environ.get("AWS_REGION")
        or "ap-south-1"
    )
    embed_mode = os.environ.get("EMBED_MODE", "voyage").strip().lower()
    # Non-Bedrock backends ignore the per-KB model ids (see
    # ``load_config_for_knowledge_base``), so resolve their model names here.
    # This also keeps the ``textModel``/``imageModel`` recorded in the staged
    # embeddings artifact accurate.
    if embed_mode == "voyage":
        text_embed_model = os.environ.get(
            "VOYAGE_TEXT_MODEL", DEFAULT_VOYAGE_TEXT_MODEL
        )
        image_embed_model = os.environ.get(
            "VOYAGE_MULTIMODAL_MODEL", DEFAULT_VOYAGE_MULTIMODAL_MODEL
        )
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
        bedrock_region=region,
        local_embed_url=os.environ.get(
            "LOCAL_EMBED_URL", DEFAULT_LOCAL_EMBED_URL
        ).rstrip("/"),
        local_embed_model=os.environ.get(
            "LOCAL_EMBED_MODEL", DEFAULT_LOCAL_EMBED_MODEL
        ),
        voyage_api_base_url=os.environ.get(
            "VOYAGE_API_BASE_URL", DEFAULT_VOYAGE_API_BASE_URL
        ).rstrip("/"),
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

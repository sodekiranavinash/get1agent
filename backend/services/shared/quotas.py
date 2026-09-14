"""Per-user quota caps + counters (DynamoDB, atomic ``ADD``)."""

from __future__ import annotations

from shared.dynamo.repositories.quotas import (
    DEFAULT_MAX_FILE_BYTES,
    DEFAULT_MAX_FILES_PER_KB,
    DEFAULT_MAX_FILES_PER_USER,
    DEFAULT_MAX_KNOWLEDGE_BASES,
    DEFAULT_MAX_STORAGE_BYTES,
    Quota,
    adjust_counters,
    get_quota,
)

__all__ = [
    "DEFAULT_MAX_FILE_BYTES",
    "DEFAULT_MAX_FILES_PER_KB",
    "DEFAULT_MAX_FILES_PER_USER",
    "DEFAULT_MAX_KNOWLEDGE_BASES",
    "DEFAULT_MAX_STORAGE_BYTES",
    "Quota",
    "adjust_counters",
    "get_quota",
]

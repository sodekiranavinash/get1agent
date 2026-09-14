"""Vector store abstraction: S3 Vectors (prod), local brute force (dev).

``VECTOR_STORE`` selects the implementation:

* ``s3vectors`` — Amazon S3 Vectors, one index per user (``idx-<userId>``).
* ``local``     — brute-force cosine over a single ``index/<userId>/vectors.json``
  object in S3 (the same S3 emulator the rest of local dev uses).
* ``dynamodb``  — reserved for DynamoDB native vectors; not implemented yet.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from shared.search.layout import vectors_key
from shared.storage import PreconditionFailed, Storage

DEFAULT_DIMENSION = int(os.environ.get("EMBED_DIM", "1024"))
# Metadata keys S3 Vectors may filter on (equality only, <=2KB / <=50 keys).
FILTERABLE_KEYS = ("kbId", "status", "page", "parentId", "tokenCount")
# Metadata returned with a match but not filterable (chunk text + labels).
NON_FILTERABLE_KEYS = ("text", "kbName", "fileName")


@dataclass
class VectorRecord:
    key: str
    vector: list[float]
    filterable: dict[str, Any] = field(default_factory=dict)
    non_filterable: dict[str, Any] = field(default_factory=dict)

    def metadata(self) -> dict[str, Any]:
        return {**self.filterable, **self.non_filterable}


@dataclass
class VectorMatch:
    key: str
    score: float
    metadata: dict[str, Any]


class VectorStore(Protocol):
    def upsert(self, sub: str, records: list[VectorRecord]) -> None: ...
    def delete(self, sub: str, keys: list[str]) -> None: ...
    def query(
        self,
        sub: str,
        vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorMatch]: ...
    def delete_user(self, sub: str) -> None: ...


def vector_store(storage: Storage | None = None) -> VectorStore:
    mode = (
        os.environ.get("VECTOR_STORE")
        or os.environ.get("VECTOR_MODE")
        or ("s3vectors" if os.environ.get("S3_VECTOR_BUCKET") else "local")
    ).strip().lower()
    if mode == "s3vectors":
        return S3VectorsStore()
    if mode == "dynamodb":
        raise NotImplementedError(
            "VECTOR_STORE=dynamodb (native vector search) is not implemented"
        )
    return LocalVectorStore(storage or Storage())


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _matches(metadata: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    for key, expected in (filters or {}).items():
        actual = metadata.get(key)
        if isinstance(expected, (list, tuple, set)):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


class LocalVectorStore:
    """Brute-force cosine over one JSON object per user (local dev)."""

    _MAX_ATTEMPTS = 6
    _BASE_BACKOFF_SECONDS = 0.05
    _MAX_BACKOFF_SECONDS = 2.0

    def __init__(self, storage: Storage) -> None:
        self._storage = storage

    def _read(self, sub: str) -> tuple[dict[str, Any], str | None]:
        return self._storage.get_json_with_etag(vectors_key(sub))

    def _mutate(self, sub: str, fn) -> None:
        key = vectors_key(sub)
        for attempt in range(self._MAX_ATTEMPTS):
            data, etag = self._read(sub)
            new_data = fn(dict(data or {}))
            try:
                self._storage.put_json_conditional(key, new_data, etag)
                return
            except PreconditionFailed:
                time.sleep(
                    min(self._MAX_BACKOFF_SECONDS, self._BASE_BACKOFF_SECONDS * 2**attempt)
                )
        raise PreconditionFailed(key)

    def upsert(self, sub: str, records: list[VectorRecord]) -> None:
        if not records:
            return

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            for record in records:
                data[record.key] = {
                    "vector": record.vector,
                    "metadata": record.metadata(),
                }
            return data

        self._mutate(sub, mutate)

    def delete(self, sub: str, keys: list[str]) -> None:
        if not keys:
            return
        drop = set(keys)

        def mutate(data: dict[str, Any]) -> dict[str, Any]:
            for key in drop:
                data.pop(key, None)
            return data

        self._mutate(sub, mutate)

    def query(
        self,
        sub: str,
        vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        data, _ = self._read(sub)
        if not data:
            return []
        scored: list[VectorMatch] = []
        for key, entry in data.items():
            metadata = entry.get("metadata") or {}
            if not _matches(metadata, filters):
                continue
            scored.append(
                VectorMatch(key=key, score=_cosine(vector, entry.get("vector") or []), metadata=metadata)
            )
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[: max(1, top_k)]

    def delete_user(self, sub: str) -> None:
        self._storage.delete(vectors_key(sub))


class S3VectorsStore:
    """Amazon S3 Vectors: one vector index per user."""

    def __init__(self) -> None:
        self._bucket = os.environ.get("S3_VECTOR_BUCKET") or ""
        if not self._bucket:
            raise RuntimeError("S3_VECTOR_BUCKET is required for VECTOR_STORE=s3vectors")
        self._region = (
            os.environ.get("S3_VECTOR_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
        )
        self._client = None
        self._ready: set[str] = set()

    def _s3vectors(self):
        if self._client is None:
            import boto3

            self._client = boto3.client("s3vectors", region_name=self._region)
        return self._client

    def _index_name(self, sub: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9-]", "-", sub)[:40].strip("-") or "user"
        digest = hashlib.sha1(sub.encode("utf-8")).hexdigest()[:10]
        return f"idx-{safe}-{digest}"

    def _ensure_index(self, sub: str) -> str:
        index_name = self._index_name(sub)
        if index_name in self._ready:
            return index_name
        from botocore.exceptions import ClientError

        try:
            self._s3vectors().create_index(
                vectorBucketName=self._bucket,
                indexName=index_name,
                dimension=DEFAULT_DIMENSION,
                distanceMetric="cosine",
                dataType="float32",
                metadataConfiguration={
                    "nonFilterableMetadataKeys": list(NON_FILTERABLE_KEYS)
                },
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"ConflictException", "ResourceAlreadyExistsException"}:
                raise
        self._ready.add(index_name)
        return index_name

    def upsert(self, sub: str, records: list[VectorRecord]) -> None:
        if not records:
            return
        index_name = self._ensure_index(sub)
        client = self._s3vectors()
        # S3 Vectors accepts up to 500 vectors per request.
        for start in range(0, len(records), 500):
            batch = records[start : start + 500]
            client.put_vectors(
                vectorBucketName=self._bucket,
                indexName=index_name,
                vectors=[
                    {
                        "key": record.key,
                        "data": {"float32": record.vector},
                        "metadata": record.metadata(),
                    }
                    for record in batch
                ],
            )

    def delete(self, sub: str, keys: list[str]) -> None:
        if not keys:
            return
        index_name = self._ensure_index(sub)
        client = self._s3vectors()
        for start in range(0, len(keys), 500):
            client.delete_vectors(
                vectorBucketName=self._bucket,
                indexName=index_name,
                keys=keys[start : start + 500],
            )

    def query(
        self,
        sub: str,
        vector: list[float],
        top_k: int,
        filters: dict[str, Any] | None = None,
    ) -> list[VectorMatch]:
        index_name = self._ensure_index(sub)
        kwargs: dict[str, Any] = {
            "vectorBucketName": self._bucket,
            "indexName": index_name,
            "queryVector": {"float32": vector},
            "topK": max(1, top_k),
            "returnMetadata": True,
            "returnDistance": True,
        }
        s3_filter = _to_s3_filter(filters)
        if s3_filter:
            kwargs["filter"] = s3_filter
        response = self._s3vectors().query_vectors(**kwargs)
        matches: list[VectorMatch] = []
        for item in response.get("vectors", []):
            # S3 Vectors returns cosine *distance* (lower is better); convert to
            # a similarity so the score matches the local store's semantics.
            if "distance" in item:
                score = 1.0 - float(item["distance"])
            else:
                score = float(item.get("score", 0.0))
            matches.append(
                VectorMatch(
                    key=str(item.get("key") or ""),
                    score=score,
                    metadata=item.get("metadata") or {},
                )
            )
        return matches

    def delete_user(self, sub: str) -> None:
        index_name = self._index_name(sub)
        from botocore.exceptions import ClientError

        try:
            self._s3vectors().delete_index(
                vectorBucketName=self._bucket, indexName=index_name
            )
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "ResourceNotFoundException":
                raise
        self._ready.discard(index_name)


def _to_s3_filter(filters: dict[str, Any] | None) -> dict[str, Any] | None:
    if not filters:
        return None
    clauses: list[dict[str, Any]] = []
    for key, value in filters.items():
        if isinstance(value, (list, tuple, set)):
            clauses.append({"$or": [{key: item} for item in value]})
        else:
            clauses.append({key: value})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}

"""Custom Strands ``MemoryStore`` backed by DynamoDB + S3 Vectors + Voyage.

Memory text lives in small DynamoDB items (``USER#<userId>`` /
``MEM#<agentId>#<memId>``); the embeddings live in the per-user vector index
under ``status="memory"`` so they never leak into knowledge-base search (which
filters ``status="ready"``).
"""

from __future__ import annotations

import dataclasses
import uuid
from typing import Any

from core.storage import Storage
from data.client import now_iso, table
from data.keys import user_pk
from retrieval.embedding.config import load_config
from retrieval.embedding.embeddings import embed_texts
from retrieval.s3_vectors import VectorRecord, vector_store

_MEM_PREFIX = "MEM#"


def _mem_sk(agent_id: str, mem_id: str) -> str:
    return f"{_MEM_PREFIX}{agent_id}#{mem_id}"


def _entry(content: str, metadata: dict[str, Any], store_name: str) -> Any:
    """Construct a Strands ``MemoryEntry`` defensively across SDK versions."""
    from strands.memory.types import MemoryEntry

    try:
        fields = {field.name for field in dataclasses.fields(MemoryEntry)}
    except TypeError:
        return MemoryEntry(content)  # type: ignore[call-arg]
    kwargs: dict[str, Any] = {}
    if "content" in fields:
        kwargs["content"] = content
    if "metadata" in fields:
        kwargs["metadata"] = metadata
    if "store_name" in fields:
        kwargs["store_name"] = store_name
    return MemoryEntry(**kwargs)  # type: ignore[call-arg]


class DynamoMemoryStore:
    """Per-user, per-agent durable memory."""

    def __init__(self, user_id: str, agent_id: str) -> None:
        self._user_id = user_id
        self._agent_id = agent_id
        self.name = "user_memory"
        self.description = "Durable facts and preferences about the user."
        self.max_search_results = 5
        self.writable = True
        self.extraction = False

    def _store(self):
        return vector_store(Storage())

    def _embed(self, text: str, input_type: str) -> list[float]:
        vectors = embed_texts([text], load_config(), input_type=input_type)
        return vectors[0] if vectors else []

    async def search(
        self, query: str, options: dict[str, Any] | None = None
    ) -> list[Any]:
        query = (query or "").strip()
        if not query:
            return []
        vector = self._embed(query, "query")
        if not vector:
            return []
        matches = self._store().query(
            self._user_id,
            vector,
            self.max_search_results,
            filters={"status": "memory", "agentId": self._agent_id},
        )
        entries: list[Any] = []
        for match in matches:
            content = str((match.metadata or {}).get("text") or "").strip()
            if not content:
                continue
            entries.append(
                _entry(content, {"score": match.score, "memId": match.key}, self.name)
            )
        return entries

    async def add(self, content: str, metadata: dict[str, Any] | None = None) -> str:
        content = (content or "").strip()
        if not content:
            return ""
        mem_id = uuid.uuid4().hex
        vector = self._embed(content, "document")
        if vector:
            self._store().upsert(
                self._user_id,
                [
                    VectorRecord(
                        key=f"mem#{mem_id}",
                        vector=vector,
                        filterable={
                            "status": "memory",
                            "agentId": self._agent_id,
                            "memId": mem_id,
                        },
                        non_filterable={"text": content, "kind": "memory"},
                    )
                ],
            )
        table().put_item(
            Item={
                "pk": user_pk(self._user_id),
                "sk": _mem_sk(self._agent_id, mem_id),
                "entity": "agentMemory",
                "memId": mem_id,
                "agentId": self._agent_id,
                "userId": self._user_id,
                "content": content,
                "metadata": metadata or {},
                "createdAt": now_iso(),
            }
        )
        return mem_id

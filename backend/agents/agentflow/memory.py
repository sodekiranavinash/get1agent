"""User memory for the agent runtime.

**One user-scoped store, shared by every agent and workflow.** Long-term memory
lives under ``/users/<userId>/`` (facts + preferences + past decisions), never
under a session or agent id, so what the user tells one agent is recalled in
chat, the agent builder, workflows and scheduled runs.

The deployed backend is the managed **AgentCore Memory** service through
:func:`build_memory_manager`; ``AGENT_MEMORY_BACKEND=dynamo`` selects the in-app
:class:`DynamoMemoryStore` used by local development and tests (the Floci stack
sets it). Text lives in small DynamoDB items (``USER#<userId>`` /
``MEM#<memId>``) and the embeddings (Amazon Titan) live in the per-user vector
index under ``status="memory"`` so they never leak into knowledge-base search
(which filters ``status="ready"``).
"""

from __future__ import annotations

import dataclasses
import json
import uuid
from typing import Any, Callable

from core import memory as core_memory
from core.storage import Storage
from data.client import now_iso, table
from data.keys import user_pk
from retrieval.embedding.config import load_config as load_embed_config
from retrieval.embedding.embeddings import embed_texts
from retrieval.s3_vectors import VectorRecord, vector_store

from agentflow.config import RuntimeConfig

_MEM_PREFIX = "MEM#"


def _mem_sk(mem_id: str) -> str:
    return f"{_MEM_PREFIX}{mem_id}"


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
    """Per-user durable memory (local development + tests).

    Mirrors the deployed AgentCore store's user scope: records are not scoped by
    agent, so any agent/workflow of the same user recalls them.
    """

    def __init__(self, user_id: str) -> None:
        self._user_id = user_id
        self.name = "user_memory"
        self.description = "Durable facts, preferences and past decisions about the user."
        self.max_search_results = 5
        self.writable = True
        self.extraction = False

    def _store(self):
        return vector_store(Storage())

    def _embed(self, text: str, input_type: str) -> list[float]:
        vectors = embed_texts([text], load_embed_config(), input_type=input_type)
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
            filters={"status": "memory"},
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
                        filterable={"status": "memory", "memId": mem_id},
                        non_filterable={"text": content, "kind": "memory"},
                    )
                ],
            )
        table().put_item(
            Item={
                "pk": user_pk(self._user_id),
                "sk": _mem_sk(mem_id),
                "entity": "agentMemory",
                "memId": mem_id,
                "userId": self._user_id,
                "content": content,
                "metadata": metadata or {},
                "createdAt": now_iso(),
            }
        )
        return mem_id


def _extraction_config() -> Any:
    """Extract after every invocation so a fact is recallable immediately.

    The default Strands cadence is every 5 turns, which makes "remember this"
    feel broken; the extra ``create_event`` calls are the cost of immediacy.
    """
    try:
        from strands.memory import ExtractionConfig
        from strands.memory.extraction.triggers import InvocationTrigger

        return ExtractionConfig(trigger=[InvocationTrigger()])
    except Exception:  # noqa: BLE001 - fall back to the SDK default cadence
        return True


def build_memory_manager(config: RuntimeConfig, user_id: str, *, session_id: str) -> Any:
    """Build the Strands ``MemoryManager`` for this run.

    **AgentCore Memory is the only production backend.** ``AGENT_MEMORY_BACKEND=dynamo``
    selects the in-app :class:`DynamoMemoryStore`, but that path exists solely for
    local development and tests — a deployed runtime always uses the managed
    service, and a missing ``AGENTCORE_MEMORY_ID`` is a hard error here (the run
    loop degrades gracefully around it).
    """
    from strands.memory import MemoryManager

    if config.memory_backend == core_memory.MEMORY_DYNAMO:
        return MemoryManager(
            stores=[DynamoMemoryStore(user_id)], add_tool_config=True
        )

    if not config.memory_id:
        raise RuntimeError(
            "AGENTCORE_MEMORY_ID is not configured; AgentCore Memory is required"
        )

    from bedrock_agentcore.memory.integrations.strands.memorystore import (
        AgentCoreMemoryStore,
    )

    # The user is the actor and the namespace is user-scoped (no session/agent
    # component), so every agent and workflow of this user shares one memory and
    # recall works across sessions. The read target must match the strategy
    # namespace templates provisioned in Terraform (`/users/{actorId}/...`).
    store = AgentCoreMemoryStore(
        memory_id=config.memory_id,
        actor_id=user_id,
        session_id=session_id,
        namespace_path="/users/{actorId}/",
        name="user_memory",
        description="Durable facts, preferences and past decisions about the user.",
        region_name=core_memory.region(),
        writable=True,
        extraction=_extraction_config(),
        max_search_results=5,
    )
    # ``add_tool_config`` stays off: ``AgentCoreMemoryStore`` has ``add_messages``
    # (server-side extraction) but no ``add``, so enabling the add tool raises.
    # The search tool and passive memory injection are on by default.
    return MemoryManager(stores=[store])


def memory_enabled(user_id: str) -> bool:
    """Whether memory is on for this user (workspace default: on)."""
    return core_memory.memory_enabled(user_id)


def build_forget_tool(user_id: str) -> Any:
    """A Strands tool that lets the user erase a memory by asking the agent."""
    from strands import tool

    def forget_memory(query: str) -> str:
        """Forget a stored memory about the user.

        Use when the user asks you to forget or delete something you remember
        about them. Searches the user's memory for the best match and permanently
        removes it.

        Args:
            query: What to forget, described in natural language.

        Returns:
            A JSON summary with the number of memories removed.
        """
        text = (query or "").strip()
        if not text:
            return json.dumps({"deleted": 0, "message": "query is required"})
        try:
            found = core_memory.list_records(user_id, limit=5, query=text)
            records = found.get("records") or []
            if not records:
                return json.dumps({"deleted": 0, "message": "no matching memory"})
            target = records[0]
            namespace = (target.get("namespaces") or [core_memory.user_namespace(user_id)])[0]
            core_memory.delete_record(user_id, str(target.get("id") or ""), namespace)
            return json.dumps(
                {"deleted": 1, "memory": str(target.get("text") or "")[:200]}
            )
        except Exception as exc:  # noqa: BLE001 - surface the failure to the model
            return json.dumps({"deleted": 0, "error": str(exc)})

    return tool(forget_memory)


def build_guard(checker: Any) -> Callable[[str, dict[str, Any]], tuple[bool, str]]:
    """Build the tool-call admission callable used by ``build_tools``.

    ``checker`` is a ``(tool_name, arguments) -> (allowed, reason)`` callable (the
    AgentCore Policy evaluator). With no checker every call is admitted (policy is
    opt-in per deployment); a checker that raises fails **closed**, so a broken
    policy can never silently open up.
    """
    if checker is None:
        return lambda _name, _args: (True, "")
    evaluator = checker

    def guard(tool_name: str, arguments: dict[str, Any]) -> tuple[bool, str]:
        try:
            return evaluator(tool_name, arguments)
        except Exception as exc:  # noqa: BLE001 - fail closed
            return False, f"policy evaluation failed: {exc}"

    return guard

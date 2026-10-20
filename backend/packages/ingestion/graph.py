"""LLM-extracted knowledge graph built from a document's chunks (Graph RAG).

Graph RAG augments retrieval with the **relationships** between the things a
document talks about. This module is the ingest half: it reads the staged
``chunks.json``, asks an Amazon Bedrock model to extract typed entities and
relationships from each batch of chunks, embeds the entities, and merges the
result into the user's S3 graph (:mod:`retrieval.graph`).

It runs as its own state-machine stage, **gated on the knowledge base's retrieval
mode**, so only Graph RAG knowledge bases pay the extraction cost. Extraction is
best-effort: a model hiccup leaves the document's hybrid index intact and records
a ``graph`` event rather than failing the whole ingestion.

The relationship vocabulary follows the GraphRAG pattern catalog (Microsoft
GraphRAG / LightRAG / FalkorDB): entities are typed nodes and relationships are
one generic typed edge rather than one graph relationship per predicate.
"""

from __future__ import annotations

import json
import os
from typing import Any

from core import bedrock_chat
from core.logging import get_logger
from core.storage import Storage
from retrieval import graph as graph_store
from retrieval.embedding.config import IngestionConfig
from retrieval.embedding.embeddings import embed_texts

logger = get_logger("ingestion")

# Entity node types. Kept deliberately general so the extractor has a closed set
# to choose from (a tight ontology is what keeps two batches from inventing two
# spellings of the same thing).
DEFAULT_ENTITY_TYPES = (
    "Person",
    "Organization",
    "Location",
    "Event",
    "Product",
    "Technology",
    "Concept",
    "Method",
    "Metric",
    "Date",
    "Document",
    "Other",
)

# Predicates. The extractor prefers one of these and falls back to RELATED_TO.
DEFAULT_RELATION_TYPES = (
    "WORKS_AT",
    "WORKS_FOR",
    "FOUNDED",
    "OWNS",
    "PART_OF",
    "CONTAINS",
    "LOCATED_IN",
    "LOCATED_AT",
    "PRODUCES",
    "USES",
    "PROVIDES",
    "SUPPORTS",
    "DEPENDS_ON",
    "IMPLEMENTS",
    "INTEGRATES_WITH",
    "MANAGES",
    "REPORTS_TO",
    "MEMBER_OF",
    "PARTNERS_WITH",
    "ACQUIRED",
    "SUBSIDIARY_OF",
    "RELATED_TO",
    "CAUSES",
    "ENABLES",
    "REQUIRES",
    "MEASURES",
    "PUBLISHED",
    "AUTHORED",
    "DEFINES",
    "DEFINED_BY",
    "SCHEDULED_FOR",
    "COMPARED_WITH",
)

DEFAULT_MODEL = "zai.glm-4.7-flash"


class GraphExtractionError(RuntimeError):
    """The model returned nothing usable for a batch."""


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if not raw:
        return default
    values = tuple(part.strip() for part in raw.split(",") if part.strip())
    return values or default


def entity_types() -> tuple[str, ...]:
    return _csv("GRAPH_ENTITY_TYPES", DEFAULT_ENTITY_TYPES)


def relation_types() -> tuple[str, ...]:
    return _csv("GRAPH_RELATION_TYPES", DEFAULT_RELATION_TYPES)


def _extraction_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": list(entity_types())},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "type"],
                },
            },
            "relationships": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "source": {"type": "string"},
                        "target": {"type": "string"},
                        "type": {"type": "string", "enum": list(relation_types())},
                        "description": {"type": "string"},
                        "weight": {"type": "number"},
                    },
                    "required": ["source", "target", "type"],
                },
            },
        },
        "required": ["entities", "relationships"],
    }


def _system_prompt() -> str:
    return (
        "You extract a knowledge graph from source text for retrieval augmentation.\n"
        "Return ONLY JSON matching the given schema.\n\n"
        f"Entity types: {', '.join(entity_types())}.\n"
        f"Relationship types: {', '.join(relation_types())} "
        "(use RELATED_TO only when none of the others fit).\n\n"
        "Rules:\n"
        "- Extract only entities and relationships that the text states explicitly. "
        "Never infer from outside knowledge.\n"
        "- Use canonical, self-contained names: 'Acme Corp', not 'the company' or "
        "'it'. Resolve pronouns to the entity they refer to.\n"
        "- Merge spelling/case variants of the same entity into ONE entity with one "
        "canonical name.\n"
        "- Every relationship endpoint must also appear in `entities`.\n"
        "- `description` is one short sentence of what the entity is, grounded in "
        "the text (empty if the text only names it).\n"
        "- `weight` is 1.0 for an explicit statement, 0.5 for a strong implication, "
        "0.2 for a weak association.\n"
        "- At most 40 entities and 60 relationships per batch; prefer the most "
        "important ones.\n"
    )


def _parse_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.split("```")[1] if len(text.split("```")) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end <= start:
            return None
        try:
            value = json.loads(text[start : end + 1])
        except (ValueError, TypeError):
            return None
    return value if isinstance(value, dict) else None


def _extract_batch(bundle: str, *, model: str, max_tokens: int) -> dict[str, Any]:
    """One Bedrock Structured-Outputs call for a batch of chunks.

    Isolated so tests can stub it; returns ``{entities, relationships}``.
    """
    result = bedrock_chat.chat_result(
        _system_prompt(),
        bundle,
        model=model,
        max_tokens=max_tokens,
        temperature=0.0,
        output_schema=_extraction_schema(),
        # zai.glm-4.7-flash is a reasoning model: left to itself it can spend the
        # whole output budget on hidden reasoning and never emit the JSON. The
        # extraction task is mechanical, so turn thinking off for it.
        extra_fields={"thinking": {"type": "disabled"}},
    )
    data = result.get("structured")
    if not isinstance(data, dict):
        data = _parse_json(str(result.get("text") or ""))
    if not isinstance(data, dict):
        stop = str(result.get("stopReason") or "")
        usage = result.get("usage") or {}
        detail = ""
        if stop:
            detail = f" (stopReason={stop}, outputTokens={usage.get('outputTokens')})"
        raise GraphExtractionError("model returned no usable JSON" + detail)
    return data


def _extract_or_split(
    records: list[dict],
    *,
    model: str,
    max_tokens: int,
    depth: int = 0,
) -> list[tuple[dict[str, Any], list[dict]]]:
    """Extract one batch, halving it if the model truncates its reply.

    A dense batch can still hit ``max_tokens`` (the reasoning model sometimes
    keeps thinking, and a batch of chunks can simply have more entities than the
    budget allows). Losing the whole batch is worse than paying for a second,
    smaller call, so split it — down to two levels.
    """
    try:
        return [
            (
                _extract_batch(_bundle(records), model=model, max_tokens=max_tokens),
                records,
            )
        ]
    except GraphExtractionError as exc:
        if depth >= 2 or len(records) <= 1 or "max_tokens" not in str(exc):
            raise
        mid = max(1, len(records) // 2)
        return _extract_or_split(
            records[:mid], model=model, max_tokens=max_tokens, depth=depth + 1
        ) + _extract_or_split(
            records[mid:], model=model, max_tokens=max_tokens, depth=depth + 1
        )


def _normalize_type(value: Any, allowed: tuple[str, ...]) -> str:
    text = str(value or "").strip()
    if not text:
        return "Other"
    for candidate in allowed:
        if candidate.lower() == text.lower():
            return candidate
    return "Other"


def _normalize_relation(value: Any) -> str:
    allowed = relation_types()
    text = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    if not text:
        return "RELATED_TO"
    for candidate in allowed:
        if candidate.upper() == text:
            return candidate
    return "RELATED_TO"


def _clean_text(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def _chunk_records(payload: dict[str, Any], document_id: str, limit: int) -> list[dict]:
    records: list[dict] = []
    for ordinal, item in enumerate(payload.get("chunks") or []):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        parent_ordinal = item.get("parentOrdinal")
        parent_ordinal = int(parent_ordinal) if parent_ordinal is not None else None
        records.append(
            {
                "chunkId": f"{document_id}#{ordinal}",
                "ordinal": ordinal,
                "parentOrdinal": parent_ordinal,
                "parentId": _parent_id(document_id, parent_ordinal),
                "page": item.get("page"),
                "text": text,
            }
        )
        if len(records) >= limit:
            break
    return records


def _parent_id(document_id: str, parent_ordinal: Any) -> str | None:
    if parent_ordinal is None:
        return None
    return f"{document_id}#{int(parent_ordinal)}"


def _attribute(
    name: str, batch_chunks: list[dict], *, extra: str = ""
) -> tuple[list[str], list[str]]:
    """Which chunks of a batch mention ``name`` (fallback: the whole batch).

    A lightweight mention check keeps entity→parent provenance honest without
    asking the model to echo chunk ids, which it does unreliably.
    """
    needle = graph_store.normalize_name(name)
    extra_needle = graph_store.normalize_name(extra)
    chunk_ids: list[str] = []
    parent_ids: list[str] = []
    if needle:
        for chunk in batch_chunks:
            haystack = graph_store.normalize_name(chunk["text"])
            if needle in haystack or (extra_needle and extra_needle in haystack):
                chunk_ids.append(chunk["chunkId"])
                if chunk.get("parentId"):
                    parent_ids.append(chunk["parentId"])
    if not chunk_ids:
        chunk_ids = [chunk["chunkId"] for chunk in batch_chunks]
        parent_ids = [
            chunk["parentId"] for chunk in batch_chunks if chunk.get("parentId")
        ]
    return list(dict.fromkeys(chunk_ids)), list(dict.fromkeys(parent_ids))


def _merge_entities(entities: dict[str, dict], raw_entities: Any, batch_chunks: list[dict]) -> None:
    for item in raw_entities or []:
        if not isinstance(item, dict):
            continue
        name = _clean_text(item.get("name"), 160).strip()
        if len(name) < 2:
            continue
        entity_type = _normalize_type(item.get("type"), entity_types())
        nid = graph_store.node_id(name, entity_type)
        chunk_ids, parent_ids = _attribute(name, batch_chunks)
        entry = entities.get(nid)
        if entry is None:
            entry = {
                "nodeId": nid,
                "name": name,
                "type": entity_type,
                "description": "",
                "chunkIds": [],
                "parentIds": [],
            }
            entities[nid] = entry
        description = _clean_text(item.get("description"), 400)
        if len(description) > len(entry["description"]):
            entry["description"] = description
        for chunk_id in chunk_ids:
            if chunk_id not in entry["chunkIds"]:
                entry["chunkIds"].append(chunk_id)
        for parent_id in parent_ids:
            if parent_id not in entry["parentIds"]:
                entry["parentIds"].append(parent_id)


def _resolve_entity(
    name: str, by_name: dict[str, dict], entities: dict[str, dict]
) -> dict | None:
    normalized = graph_store.normalize_name(name)
    if not normalized:
        return None
    found = by_name.get(normalized)
    if found:
        return found
    # A relationship endpoint the model did not list as an entity: create a
    # minimal stub so the edge has a real node to attach to.
    nid = graph_store.node_id(name, "Other")
    stub = entities.get(nid)
    if stub is None:
        stub = {
            "nodeId": nid,
            "name": name,
            "type": "Other",
            "description": "",
            "chunkIds": [],
            "parentIds": [],
        }
        entities[nid] = stub
        by_name[normalized] = stub
    return stub


def _merge_relations(
    relations: dict[str, dict],
    raw_relations: Any,
    batch_chunks: list[dict],
    entities: dict[str, dict],
    *,
    kb_id: str,
    doc_id: str,
) -> None:
    by_name = {
        graph_store.normalize_name(entry["name"]): entry for entry in entities.values()
    }
    for item in raw_relations or []:
        if not isinstance(item, dict):
            continue
        source_name = _clean_text(item.get("source"), 160).strip()
        target_name = _clean_text(item.get("target"), 160).strip()
        if not source_name or not target_name:
            continue
        source = _resolve_entity(source_name, by_name, entities)
        target = _resolve_entity(target_name, by_name, entities)
        if source is None or target is None or source["nodeId"] == target["nodeId"]:
            continue
        rel_type = _normalize_relation(item.get("type"))
        edge_id = graph_store.edge_id(source["nodeId"], rel_type, target["nodeId"])
        try:
            weight = float(item.get("weight"))
        except (TypeError, ValueError):
            weight = 1.0
        weight = min(1.0, max(0.0, weight))
        chunk_ids, parent_ids = _attribute(
            source["name"], batch_chunks, extra=target["name"]
        )
        description = _clean_text(item.get("description"), 400)
        fact = f"{source['name']} {rel_type.replace('_', ' ').lower()} {target['name']}"
        existing = relations.get(edge_id)
        if existing is None:
            relations[edge_id] = {
                "edgeId": edge_id,
                "from": source["nodeId"],
                "to": target["nodeId"],
                "fromName": source["name"],
                "toName": target["name"],
                "fromType": source["type"],
                "toType": target["type"],
                "type": rel_type,
                "description": description,
                "fact": fact,
                "weight": weight,
                "kbId": kb_id,
                "docId": doc_id,
                "chunkId": chunk_ids[0] if chunk_ids else None,
                "parentId": parent_ids[0] if parent_ids else None,
                "chunkIds": chunk_ids,
            }
            continue
        existing["weight"] = max(float(existing["weight"]), weight)
        if len(description) > len(existing["description"]):
            existing["description"] = description
        for chunk_id in chunk_ids:
            if chunk_id not in existing["chunkIds"]:
                existing["chunkIds"].append(chunk_id)


def build_graph(
    storage: Storage,
    config: IngestionConfig,
    *,
    user_id: str,
    knowledge_base_id: str,
    document_id: str,
    chunks_key: str,
    file_name: str | None = None,
    kb_name: str | None = None,
) -> dict[str, Any]:
    """Extract a document's entities/relationships and merge them into the graph.

    Idempotent: any previous graph contribution from this document is removed
    first (so a re-index or retry re-indexes cleanly). Best-effort by design —
    individual batch failures are counted and reported, never raised, so a
    throttled model cannot fail the document.
    """
    del file_name, kb_name  # accepted for call symmetry; provenance is the doc + chunks
    model = (os.environ.get("GRAPH_EXTRACT_MODEL") or DEFAULT_MODEL).strip()
    max_tokens = _int("GRAPH_EXTRACT_MAX_TOKENS", 16000)
    batch_size = max(1, _int("GRAPH_EXTRACT_BATCH_CHUNKS", 6))
    max_chunks = max(1, _int("GRAPH_EXTRACT_MAX_CHUNKS", 400))
    max_entities = max(1, _int("GRAPH_EXTRACT_MAX_ENTITIES", 400))

    payload = json.loads(storage.get_bytes(chunks_key).decode("utf-8"))
    records = _chunk_records(payload, document_id, max_chunks)
    if not records:
        return {"entities": 0, "relationships": 0, "batches": 0, "failedBatches": 0}

    entities: dict[str, dict] = {}
    relations: dict[str, dict] = {}
    failed_batches = 0
    batches = 0

    for start in range(0, len(records), batch_size):
        batch = records[start : start + batch_size]
        batches += 1
        try:
            parts = _extract_or_split(batch, model=model, max_tokens=max_tokens)
        except Exception:  # noqa: BLE001 - one bad batch must not fail the document
            failed_batches += 1
            logger.warning(
                "graph extraction batch failed",
                extra={"documentId": document_id, "batch": batches},
                exc_info=True,
            )
            continue
        for extracted, part in parts:
            _merge_entities(entities, extracted.get("entities"), part)
            _merge_relations(
                relations,
                extracted.get("relationships"),
                part,
                entities,
                kb_id=knowledge_base_id,
                doc_id=document_id,
            )
        if len(entities) >= max_entities:
            break

    nodes = list(entities.values())[:max_entities]
    kept_ids = {node["nodeId"] for node in nodes}
    edges = [
        edge
        for edge in relations.values()
        if edge["from"] in kept_ids and edge["to"] in kept_ids
    ]

    store = None
    try:
        from retrieval.s3_vectors import vector_store

        store = vector_store(storage)
    except Exception:  # noqa: BLE001 - graph nodes still work without entity vectors
        store = None

    # Delete-then-write so a re-index/retry is clean.
    graph_store.delete_document_graph(storage, user_id, document_id, store)

    if nodes and store is not None:
        texts = [
            f"{node['name']} ({node['type']}): {node['description']}"
            if node["description"]
            else f"{node['name']} ({node['type']})"
            for node in nodes
        ]
        try:
            vectors = embed_texts(texts, config)
            records_to_store = [
                graph_store.entity_vector_record(
                    node=node, vector=vector, kb_id=knowledge_base_id
                )
                for node, vector in zip(nodes, vectors)
            ]
            store.upsert(user_id, records_to_store)
        except Exception:  # noqa: BLE001 - name-index seeding still reaches the nodes
            pass

    if nodes:
        graph_store.upsert_graph(
            storage,
            user_id,
            kb_id=knowledge_base_id,
            doc_id=document_id,
            nodes=nodes,
            edges=edges,
        )

    return {
        "entities": len(nodes),
        "relationships": len(edges),
        "batches": batches,
        "failedBatches": failed_batches,
    }


def _bundle(batch: list[dict]) -> str:
    lines: list[str] = ["Extract the knowledge graph from these numbered excerpts:\n"]
    for index, chunk in enumerate(batch, start=1):
        page = chunk.get("page")
        header = f"[{index}]" + (f" (page {int(page)})" if page is not None else "")
        lines.append(header)
        lines.append(chunk["text"])
        lines.append("")
    return "\n".join(lines)

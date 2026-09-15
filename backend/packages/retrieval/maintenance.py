"""Manifest-driven cleanup of a document's retrieval artifacts.

The manifest (``index/<sub>/docs/<docId>/manifest.json``) lists exactly the
chunkIds, parentIds, tokens and token totals a document contributed, so delete
and re-index remove precisely those vectors, parent objects and postings without
scanning the corpus.
"""

from __future__ import annotations

from retrieval.layout import manifest_key, parent_key
from retrieval.s3_vectors import VectorStore
from retrieval.term_index import remove_document_postings, update_stats
from core.storage import Storage


def delete_document_index(
    storage: Storage, store: VectorStore, sub: str, doc_id: str
) -> None:
    manifest = storage.get_json(manifest_key(sub, doc_id))
    if not manifest:
        return
    chunk_ids = list(manifest.get("chunkIds") or [])
    parent_ids = list(manifest.get("parentIds") or [])
    tokens = list(manifest.get("tokens") or [])
    total_tokens = int(manifest.get("totalTokens") or 0)

    if chunk_ids:
        store.delete(sub, chunk_ids)
    for parent_id in parent_ids:
        storage.delete(parent_key(sub, parent_id))
    if tokens:
        remove_document_postings(storage, sub, tokens, doc_id)
    if chunk_ids or total_tokens:
        update_stats(
            storage,
            sub,
            delta_chunks=-len(chunk_ids),
            delta_tokens=-total_tokens,
        )
    storage.delete(manifest_key(sub, doc_id))

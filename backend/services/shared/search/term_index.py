"""S3-backed term (posting) index with BM25 statistics.

One object per term: ``index/<sub>/terms/<token>.json`` holding ``df`` and the
postings ``[{chunkId, docId, kbId, parentId, tf}]``. A per-first-char catalog
shard enables prefix expansion (``project:*``) with one extra read.

Writes are read-modify-write with a conditional ``If-Match`` PUT and bounded
exponential backoff, so concurrent indexers never lose updates.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from shared.search.layout import (
    catalog_key,
    stats_key,
    term_key,
    term_frequencies,
    tokenize,
)
from shared.storage import PreconditionFailed, Storage

_MAX_ATTEMPTS = 6
_BASE_BACKOFF_SECONDS = 0.05
_MAX_BACKOFF_SECONDS = 2.0
# Cap prefix expansion so one prefix cannot fan out into thousands of GETs.
MAX_PREFIX_EXPANSION = 50


def _read_modify_write(
    storage: Storage,
    key: str,
    mutate: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    last: dict[str, Any] = {}
    for attempt in range(_MAX_ATTEMPTS):
        data, etag = storage.get_json_with_etag(key)
        last = mutate(dict(data or {}))
        try:
            storage.put_json_conditional(key, last, etag)
            return last
        except PreconditionFailed:
            backoff = min(_MAX_BACKOFF_SECONDS, _BASE_BACKOFF_SECONDS * 2**attempt)
            time.sleep(backoff)
    raise PreconditionFailed(key)


def read_term(storage: Storage, sub: str, token: str) -> dict[str, Any] | None:
    data, _ = storage.get_json_with_etag(term_key(sub, token))
    return data


def add_postings(
    storage: Storage,
    sub: str,
    postings_by_token: dict[str, dict[str, Any]],
) -> None:
    """Add one posting per token, replacing any prior posting for the chunk."""
    for token, posting in postings_by_token.items():
        chunk_id = posting["chunkId"]

        def mutate(data: dict[str, Any], token=token, posting=posting) -> dict[str, Any]:
            existing = [
                item
                for item in (data.get("postings") or [])
                if item.get("chunkId") != chunk_id
            ]
            existing.append(posting)
            return {"df": len(existing), "postings": existing}

        _read_modify_write(storage, term_key(sub, token), mutate)


def remove_document_postings(
    storage: Storage, sub: str, tokens: list[str], doc_id: str
) -> None:
    """Drop every posting for ``doc_id`` (delete / re-index cleanup)."""
    for token in tokens:
        key = term_key(sub, token)
        data, etag = storage.get_json_with_etag(key)
        if not data:
            continue
        postings = [
            item
            for item in (data.get("postings") or [])
            if item.get("docId") != doc_id
        ]
        if len(postings) == len(data.get("postings") or []):
            continue
        try:
            storage.put_json_conditional(
                key, {"df": len(postings), "postings": postings}, etag
            )
        except PreconditionFailed:
            # Best effort: a racing indexer will re-write this term anyway.
            continue


def update_catalog(storage: Storage, sub: str, tokens: list[str]) -> None:
    shards: dict[str, set[str]] = {}
    for token in tokens:
        if not token:
            continue
        shards.setdefault(token[0], set()).add(token)
    for first_char, values in shards.items():
        key = catalog_key(sub, first_char)

        def mutate(data: dict[str, Any], values=values) -> dict[str, Any]:
            existing = set(data.get("tokens") or [])
            existing.update(values)
            return {"tokens": sorted(existing)}

        _read_modify_write(storage, key, mutate)


def expand_prefix(storage: Storage, sub: str, term: str) -> list[str]:
    """Exact term plus any catalog token starting with it (prefix match)."""
    if not term:
        return []
    data, _ = storage.get_json_with_etag(catalog_key(sub, term[0]))
    tokens = data.get("tokens") if isinstance(data, dict) else None
    if not isinstance(tokens, list):
        return [term]
    matches = [str(token) for token in tokens if str(token).startswith(term)]
    if term not in matches:
        matches.append(term)
    return matches[:MAX_PREFIX_EXPANSION]


def read_stats(storage: Storage, sub: str) -> dict[str, Any]:
    data, _ = storage.get_json_with_etag(stats_key(sub))
    if not data:
        return {"chunkCount": 0, "totalTokens": 0, "avgdl": 0.0}
    return data


def update_stats(
    storage: Storage, sub: str, *, delta_chunks: int, delta_tokens: int
) -> dict[str, Any]:
    key = stats_key(sub)

    def mutate(data: dict[str, Any]) -> dict[str, Any]:
        chunk_count = max(0, int(data.get("chunkCount") or 0) + delta_chunks)
        total_tokens = max(0, int(data.get("totalTokens") or 0) + delta_tokens)
        return {
            "chunkCount": chunk_count,
            "totalTokens": total_tokens,
            "avgdl": (total_tokens / chunk_count) if chunk_count else 0.0,
        }

    return _read_modify_write(storage, key, mutate)


def build_postings(
    *,
    chunk_id: str,
    doc_id: str,
    kb_id: str,
    parent_id: str,
    text: str,
) -> dict[str, dict[str, Any]]:
    """Tokenize a chunk into ``{token: posting}`` with term frequencies."""
    frequencies = term_frequencies(tokenize(text))
    dl = sum(frequencies.values()) or 1
    postings: dict[str, dict[str, Any]] = {}
    for token, tf in frequencies.items():
        postings[token] = {
            "chunkId": chunk_id,
            "docId": doc_id,
            "kbId": kb_id,
            "parentId": parent_id,
            "tf": tf,
            "dl": dl,
        }
    return postings

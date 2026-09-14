"""S3-backed search: layout, term (BM25) index, S3 Vectors and hybrid fusion."""

from shared.search.errors import RetrievalError
from shared.search.hybrid import RRF_K, search_candidates
from shared.search.layout import (
    catalog_key,
    chunks_key,
    derived_prefix,
    embeddings_key,
    manifest_key,
    parent_key,
    raw_key,
    stats_key,
    term_key,
    tokenize,
    vectors_key,
)
from shared.search.rerank import rerank_candidates, rerank_mode
from shared.search.s3_vectors import VectorMatch, VectorRecord, vector_store
from shared.search.service import (
    cap_per_document,
    group_sources,
    list_knowledge_bases,
    resolve_knowledge_bases,
    search,
    source_url,
)
from shared.search.term_index import (
    add_postings,
    expand_prefix,
    read_stats,
    remove_document_postings,
    update_catalog,
    update_stats,
)

__all__ = [
    "RRF_K",
    "RetrievalError",
    "VectorMatch",
    "VectorRecord",
    "add_postings",
    "cap_per_document",
    "catalog_key",
    "chunks_key",
    "derived_prefix",
    "embeddings_key",
    "expand_prefix",
    "group_sources",
    "list_knowledge_bases",
    "manifest_key",
    "parent_key",
    "raw_key",
    "read_stats",
    "remove_document_postings",
    "rerank_candidates",
    "rerank_mode",
    "resolve_knowledge_bases",
    "search",
    "search_candidates",
    "source_url",
    "stats_key",
    "term_key",
    "tokenize",
    "update_catalog",
    "update_stats",
    "vector_store",
    "vectors_key",
]

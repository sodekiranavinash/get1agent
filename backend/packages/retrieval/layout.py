"""S3 key layout and tokenization for the keyword index.

```
raw/<userId>/<kbId>/<docId>/<fileName>            original upload (triggers ingestion)
derived/<userId>/<kbId>/<docId>/text.md           extracted text
derived/<userId>/<kbId>/<docId>/images/<page>-<i>.<ext>
derived/<userId>/<kbId>/<docId>/chunks.json       staged parents + children
derived/<userId>/<kbId>/<docId>/embeddings.json   staged vectors
index/<userId>/parents/<parentId>.json            parent + children text (hydration)
index/<userId>/terms/<token>.json                 postings + df (BM25)
index/<userId>/catalog/<c0>.json                  token strings per first char
index/<userId>/docs/<docId>/manifest.json         chunkIds, parentIds, tokens
index/<userId>/stats.json                         chunkCount, totalTokens, avgdl
index/<userId>/vectors.json                       local vector store (VECTOR_STORE=local)
```
"""

from __future__ import annotations

import re

RAW_PREFIX = "raw"
DERIVED_PREFIX = "derived"
INDEX_PREFIX = "index"

TOKEN_RE = re.compile(r"\w+", re.UNICODE)

# Short English stopword list. The corpus may be multilingual, so we only strip
# obvious filler rather than relying on a language-specific analyzer.
STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
        "did", "do", "does", "for", "from", "had", "has", "have", "he", "her",
        "here", "his", "how", "i", "if", "in", "into", "is", "it", "its", "me",
        "my", "no", "not", "of", "on", "or", "our", "should", "so", "than",
        "that", "the", "their", "them", "then", "there", "these", "they",
        "this", "to", "too", "up", "us", "was", "we", "were", "what", "when",
        "where", "which", "who", "why", "will", "with", "would", "you", "your",
    }
)


def raw_key(sub: str, kb_id: str, doc_id: str, file_name: str) -> str:
    return f"{RAW_PREFIX}/{sub}/{kb_id}/{doc_id}/{file_name}"


def raw_prefix(sub: str) -> str:
    return f"{RAW_PREFIX}/{sub}/"


def derived_prefix(sub: str, kb_id: str, doc_id: str) -> str:
    return f"{DERIVED_PREFIX}/{sub}/{kb_id}/{doc_id}"


def text_key(sub: str, kb_id: str, doc_id: str) -> str:
    return f"{derived_prefix(sub, kb_id, doc_id)}/text.md"


def chunks_key(sub: str, kb_id: str, doc_id: str) -> str:
    return f"{derived_prefix(sub, kb_id, doc_id)}/chunks.json"


def embeddings_key(sub: str, kb_id: str, doc_id: str) -> str:
    return f"{derived_prefix(sub, kb_id, doc_id)}/embeddings.json"


def image_key(sub: str, kb_id: str, doc_id: str, page: int | None, index: int, ext: str) -> str:
    return f"{derived_prefix(sub, kb_id, doc_id)}/images/{page or 0}-{index}.{ext}"


def parent_key(sub: str, parent_id: str) -> str:
    return f"{INDEX_PREFIX}/{sub}/parents/{parent_id}.json"


def term_key(sub: str, token: str) -> str:
    return f"{INDEX_PREFIX}/{sub}/terms/{token}.json"


def catalog_key(sub: str, first_char: str) -> str:
    return f"{INDEX_PREFIX}/{sub}/catalog/{first_char}.json"


def manifest_key(sub: str, doc_id: str) -> str:
    return f"{INDEX_PREFIX}/{sub}/docs/{doc_id}/manifest.json"


def stats_key(sub: str) -> str:
    return f"{INDEX_PREFIX}/{sub}/stats.json"


def vectors_key(sub: str) -> str:
    return f"{INDEX_PREFIX}/{sub}/vectors.json"


def index_prefix(sub: str) -> str:
    return f"{INDEX_PREFIX}/{sub}/"


def tokenize(text: str) -> list[str]:
    """Indexing tokenizer: lowercased words minus stopwords/single chars."""
    return [
        token
        for token in TOKEN_RE.findall((text or "").lower())
        if len(token) >= 2 and token not in STOPWORDS
    ]


def query_terms(query: str) -> list[str]:
    """Query tokenizer: de-duplicated meaningful terms (OR/prefix semantics)."""
    terms: list[str] = []
    seen: set[str] = set()
    for token in TOKEN_RE.findall((query or "").lower()):
        if len(token) < 2 or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        terms.append(token)
    if not terms:
        terms = TOKEN_RE.findall((query or "").lower())[:8]
    return terms


def term_frequencies(tokens: list[str]) -> dict[str, int]:
    frequencies: dict[str, int] = {}
    for token in tokens:
        frequencies[token] = frequencies.get(token, 0) + 1
    return frequencies

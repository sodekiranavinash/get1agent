"""The reserved ingestion scope AI Assistant answers from.

AI Assistant's knowledge is an **ordinary knowledge base** owned by a reserved scope, not
a special store. That is what lets AI Assistant reuse the whole existing retrieval stack —
hybrid S3 Vectors + BM25 search, RRF fusion, opt-in Bedrock rerank, small-to-big
parent hydration, the exact cache, the semantic cache and single-flight — with no
new retrieval code to maintain.

The scope is a pseudo-user: there is no profile, no login and no session for it,
so it can never be listed to a real user, and every key it owns is namespaced by
the same ``platform`` id the pipeline already uses:

    DynamoDB  USER#platform / KB#platform-docs   (the knowledge base item)
              KB#<kbId> / DOC#<lowerFileName>    (one document per corpus file)
    S3        raw/platform/<kbId>/<docId>/<file>.md   (the ONLY triggering prefix)
              index/platform/…                        (parents, terms, catalog, stats)
    Vectors   idx-platform                            (S3 Vectors index)
"""

from __future__ import annotations

#: The pseudo-user id that owns the platform corpus. Deliberately not shaped like
#: a real user id (``u_`` + 16 chars) so it can never collide with one.
PLATFORM_USER_ID = "platform"

#: The knowledge base name; S3-bucket-style, as the platform requires.
PLATFORM_KB_NAME = "platform-docs"

#: A fixed, human-readable UUID for the knowledge base. Fixed rather than random
#: so a re-bootstrap is idempotent and a corpus upload always targets the same KB.
PLATFORM_KB_ID = "kb_platform_docs_0001"

KB_DESCRIPTION = (
    "Generated platform documentation for AI Assistant, the in-product assistant. "
    "Rebuilt from the repository by `make ai-assistant-knowledge` — do not edit in place."
)

#: Chunking for a question-shaped corpus: smaller than the 512-token default so a
#: chunk is one heading-delimited section with its breadcrumb intact.
PLATFORM_CHUNK_SIZE = 384
PLATFORM_CHUNK_OVERLAP = 32

#: The embedding configuration the corpus is indexed with. Titan Text Embeddings
#: V2, matching the platform default.
PLATFORM_EMBED_MODEL = "amazon.titan-embed-text-v2:0"
PLATFORM_IMAGE_EMBED_MODEL = "amazon.titan-embed-image-v1"
PLATFORM_EMBEDDING_DIM = 1024

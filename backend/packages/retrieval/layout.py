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
# Standalone user storage (files to attach to agents later). Not under `raw/`,
# so the EventBridge ingestion rule never fires for these.
STORAGE_PREFIX = "storage"
# Chat/builder conversation transcripts (one JSON per conversation).
CONVERSATION_PREFIX = "conversations"
# User-defined custom MCP tool sources (one .py per tool). Not under `raw/`, so
# the EventBridge ingestion rule never fires for these.
CUSTOM_PREFIX = "custom"
# Playground build-chat transcripts (one JSON per session). Not under `raw/`, so
# the EventBridge ingestion rule never fires for these.
PLAYGROUND_PREFIX = "playground"
# Evaluation-lab per-case artifacts (retrieved contexts, generated answer, judge
# reasoning). Not under `raw/`, so the EventBridge ingestion rule never fires.
EVAL_PREFIX = "evals"
# Cached remote-MCP tool schemas (one JSON per connection).
MCP_PREFIX = "mcp"
# AgentCore runtime conversation sessions (S3SessionManager), per user/agent.
AGENT_SESSION_PREFIX = "agent-sessions"
# Agent-run traces: the full Langfuse-style observation tree, one JSON per run.
# Not under `raw/`, so the ingestion EventBridge rule never fires for these.
TRACE_PREFIX = "traces"

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


def storage_key(sub: str, file_id: str, file_name: str) -> str:
    return f"{STORAGE_PREFIX}/{sub}/{file_id}/{file_name}"


def conversation_key(sub: str, conversation_id: int | str) -> str:
    """S3 key for a conversation transcript (all turns, one JSON object)."""
    return f"{CONVERSATION_PREFIX}/{sub}/{conversation_id}.json"


def custom_tool_key(sub: str, server_slug: str, tool_name: str) -> str:
    """S3 key for a user-defined tool's Python source."""
    return f"{CUSTOM_PREFIX}/{sub}/{server_slug}/{tool_name}.py"


def custom_prefix(sub: str) -> str:
    return f"{CUSTOM_PREFIX}/{sub}/"


def playground_key(sub: str, session_id: str) -> str:
    """S3 key for a Playground build-chat transcript (all messages, one JSON)."""
    return f"{PLAYGROUND_PREFIX}/{sub}/{session_id}.json"


def eval_case_key(sub: str, run_id: str, case_id: str) -> str:
    """S3 key for one eval case's full artifact (contexts, answer, reasoning)."""
    return f"{EVAL_PREFIX}/{sub}/{run_id}/{case_id}.json"


def eval_prefix(sub: str, run_id: str) -> str:
    return f"{EVAL_PREFIX}/{sub}/{run_id}/"


def mcp_prefix(sub: str) -> str:
    """Every cached remote-MCP artifact for a user (tool schemas)."""
    return f"{MCP_PREFIX}/{sub}/"


def agent_sessions_prefix(sub: str) -> str:
    """AgentCore runtime conversation sessions for a user."""
    return f"{AGENT_SESSION_PREFIX}/{sub}/"


def trace_key(sub: str, trace_id: str) -> str:
    """S3 key for one run's full trace/observation tree (Langfuse-style)."""
    return f"{TRACE_PREFIX}/{sub}/{trace_id}.json"


def trace_prefix(sub: str) -> str:
    """Every trace object for a user (account-erasure cleanup)."""
    return f"{TRACE_PREFIX}/{sub}/"


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

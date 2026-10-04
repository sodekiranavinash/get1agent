# Ingestion Logic

Design reference for the document ingestion pipeline:
**PDF → pages → markdown → chunks → embeddings → index**, with idempotent
re-ingestion when a document is re-uploaded with new content.

> **Status: historical design rationale.** The shipped pipeline is the 3-stage
> **S3 → EventBridge → SQS → Step Functions (Standard) → extract → embed → index**
> design described in [`AGENTS.md`](../../AGENTS.md) → "Document ingestion". The
> pgvector/pgvector-on-RDS schema and migration snippets below describe the earlier
> Postgres design and are kept only to explain the rationale; the live stores are
> **S3 Vectors** (embeddings) and **S3 objects** (BM25 postings, parents,
> manifests). `AGENTS.md` is authoritative.
> Last updated: 2026-09-12 (pre-migration).

---

## 1. Why Step Functions (and not just SQS + Lambda)

The pipeline steps have **heterogeneous failure semantics**. A single Lambda
cannot express "retry embedding 5× with backoff, but fail the whole doc if OCR
fails."

| Step | Failure mode | Retry behavior |
|---|---|---|
| PDF → pages | corrupt / encrypted file | fail fast, no retry |
| pages → markdown | OCR/LLM timeout, rate limit | retry with backoff |
| chunk | deterministic | no retry |
| embed | API 429/5xx, partial batch fail | retry, throttle concurrency |
| store | DB conflict / deadlock | retry |

Step Functions gives per-step retry/timeout policies plus **per-file execution
history** (invaluable for "why isn't my document searchable?" support cases).

Cost is negligible relative to embeddings: a ~7-state Standard workflow at
100k files/month ≈ **$1.65/mo** in state transitions. The embedding bill will
be orders of magnitude larger.

### Standard vs Express

Use **Standard**, not Express. Ingestion is long-running (OCR/LLM calls) and
Express caps at 5 minutes. Standard also gives exactly-once execution, which
matters for idempotent writes.

---

## 2. High-level flow

```
S3 upload
  → EventBridge rule
    → Step Functions: IngestDocument (Standard)
        ├─ GetDocumentVersion     # hash check, idempotency
        ├─ Choice: unchanged?  → End (no-op)
        ├─ ExtractPages           # PDF → page text/images
        ├─ PagesToMarkdown        # OCR / LLM → markdown
        ├─ Chunk                  # deterministic splitter
        ├─ Map (embed chunks)     # MaxConcurrency bounded
        │     └─ EmbedChunk       # batch embeddings API, retry 429/5xx
        ├─ UpsertChunks           # transactional write
        └─ MarkVersionReady
```

Notes:
- **Fan-out from S3 via EventBridge**, not `S3 → Lambda → StartExecution`. You
  get native retry/DLQ and avoid paying a Lambda just to start a workflow.
- **Don't over-split states.** Each state costs a transition and adds latency.
  Combine deterministic work (e.g. chunk into the markdown step) unless it needs
  independent retry.
- **Inline `Map`** with `MaxConcurrency` for per-file chunk embedding.
  **Distributed Map** only for bulk backfills of thousands of documents.
- Execution name = `ingest-{doc_id}-{content_hash}` so duplicate S3 events
  cannot start a second run.

---

## 3. Idempotency & update logic

### Correct mental model

Two rules:

1. **Hash the raw file bytes** (`doc_id + content_hash`) — this is the
   idempotency key. Never hash embeddings.
2. **Similarity search is the read/query path only.** On the write path, match
   by **deterministic keys**, never by vector similarity. Deciding "which chunks
   to update" via nearest-neighbor search will corrupt the index: unrelated
   chunks score high and chunk boundaries shift when text changes.

### Re-ingestion flow

```
raw file changed?
  → re-extract + re-chunk the WHOLE document
  → compute chunk_hash per chunk (hash of chunk text)
  → UPSERT by (document_id, chunk_hash)
  → DELETE chunks for document_id whose chunk_hash is not in the new set
```

Chunk-level hashing lets us **skip re-embedding unchanged chunks** — the real
saving, since embeddings cost money and re-chunking is free. Caveat: any edit
shifts boundaries downstream, so expect most chunks after the edit point to
change hash. Still a win for append-only or small localized edits.

### Idempotent SQL

```sql
INSERT INTO chunks (document_id, chunk_hash, content, embedding)
VALUES (...)
ON CONFLICT (document_id, chunk_hash) DO NOTHING;
```

The unique key *is* the dedup mechanism. Retries are safe by construction.

---

## 4. Schema (pgvector on existing RDS)

Reuses the existing RDS Postgres instance (`DATABASE_URL`). Enable the
`vector` extension via an Alembic migration in `backend/migrations/versions/`.

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
  id             uuid PRIMARY KEY,
  content_hash   text        NOT NULL,   -- raw file hash
  version        int         NOT NULL,
  status         text        NOT NULL,   -- processing | ready | failed
  embed_model    text        NOT NULL,   -- e.g. text-embedding-3-small
  updated_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE chunks (
  id           bigserial PRIMARY KEY,
  document_id  uuid REFERENCES documents(id) ON DELETE CASCADE,
  chunk_hash   text        NOT NULL,
  content      text        NOT NULL,
  embedding    vector(1536),
  UNIQUE (document_id, chunk_hash)
);

CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
```

- `status = processing` until the run completes, so the query path ignores
  partial documents.
- `embed_model` is stored per document: switching models changes the vector
  dimension and requires a full re-embed. Version it explicitly.

---

## 5. Tool choices

| Stage | Choice | Why |
|---|---|---|
| Orchestration | Step Functions (Standard) | per-step retries + history |
| PDF → pages | Lambda + `pymupdf` / `unstructured` | fast, handles scanned docs |
| pages → markdown | Lambda + OCR/LLM | retryable, isolated |
| chunking | `langchain-text-splitters` | deterministic, free |
| embeddings | `text-embedding-3-small` | $0.02 / 1M tokens, best price/quality |
| vector DB | **pgvector on existing RDS** | zero new infra |

Embeddings run on **Amazon Bedrock Titan Text Embeddings V2** (1024-d, in-region);
locally, Ollama `mxbai-embed-large` is the offline fallback.

---

## 6. Gotchas

- **Partial writes.** Embed-then-write is not atomic. If the run dies mid-`Map`
  you get partial chunks. Either write per-batch inside the Map and keep
  `status = processing`, or write everything at the end and flip status only on
  success. The query path must filter on `status = ready`.
- **Batch embeddings.** Use the batch endpoint (up to ~2048 inputs/call), not
  one API call per chunk. This dominates both cost and latency.
- **Model versioning.** Different embedding model = different vector dimension =
  full re-embed. Never mix dimensions in one column.
- **Dead-letter / failure state.** Add a terminal `Failed` state that sets
  `documents.status = failed` so retries and support queries are possible.
- **Concurrency limits.** Bound the embed `Map` (`MaxConcurrency`) to respect
  provider rate limits; rely on step-level retry with exponential backoff.

---

## 7. Alignment with this repo (current)

- Lambdas live in `backend/services/<category>/<name>/` with `handler.py` at the
  app root and code in `src/`, registered in `backend/registry.json`, runtime
  `python3.14`, shared `backend/packages/` bundled per app.
- The shipped pipeline is **3 stages** (`extract+chunk → embed → index`) under
  Step Functions **Standard**; the schema is DynamoDB + S3 Vectors + S3 objects
  (no RDS/migrations).
- Local testing via `make floci-*` targets only.
- The Step Functions definition and S3/EventBridge resources live in
  `infra/terraform/modules/ingestion/`.

### Historical open questions (resolved)

- Embedding provider/model: **Amazon Bedrock Titan Text Embeddings V2** (1024-d),
  Ollama `mxbai-embed-large` locally.
- Chunking: **512-token children with 64 overlap**, parents per PDF page (or a
  fixed window).
- OCR: text-layer PDFs plus extracted images; image embeddings are opt-in and not
  yet searched.

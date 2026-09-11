# Ingestion Logic

Design reference for the document ingestion pipeline:
**PDF → pages → markdown → chunks → embeddings → pgvector**, with idempotent
re-ingestion when a document is re-uploaded with new content.

Status: design / not yet implemented.
Last updated: 2026-09-11.

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

Alternative embeddings if cost-sensitive: `voyage-3-lite`, or self-hosted
`bge-small` / `all-MiniLM` (free API, pay compute only).

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

## 7. Alignment with this repo

- Lambdas live in `backend/<name>/src/handler.py`, registered in
  `backend/registry.json`, runtime `python3.14`, shared `data` layer.
- New schema changes go through `backend/migrations/versions/` and
  `bash scripts/migrate.sh up`.
- Local testing via `make` targets / `local/` scripts only — never invoke
  Lambdas through AWS or Docker locally.
- Step Functions definition and S3/EventBridge resources belong in
  `infra/terraform/`.

### Open questions

- Which embedding provider / model do we standardize on?
- Chunking strategy and target chunk size / overlap?
- Do we need OCR (scanned PDFs) in v1, or text-layer PDFs only?
- Retention: keep raw files in S3 indefinitely, or expire after ingestion?

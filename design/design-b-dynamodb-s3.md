# Design B — Serverless Migration: Discussion, Decisions & Implementation Plan

**Status:** approved design, not yet implemented.
**Purpose:** single source of truth for replacing the current
Postgres/pgvector + VPC backend with a serverless design where **DynamoDB is the
database**, **S3 Vectors** holds embeddings, and **S3 objects** hold the keyword
index and retrieval artifacts.
**Audience:** implement this in a fresh session. Everything needed is here.
**Last updated:** 2026-09-14.

---

# Part 1 — Context & problem

The app currently stores everything in **RDS Postgres + pgvector inside a VPC**.
That VPC is the source of pain:

- RDS is VPC-only, so every Lambda that touches the DB must join the VPC
  (ENIs, subnets, security groups, cold-start overhead).
- The VPC has no NAT, so in-VPC Lambdas can only reach S3 (gateway endpoint) and
  a small set of interface endpoints.
- Because of the VPC split, the system is fragmented: some Lambdas run in the
  VPC, some outside, and data is split between RDS and DynamoDB
  (`code-interpreter-sessions`).
- The user wants **all data in one place**, **no VPC friction**, **fast search**,
  and **equal-or-better relevance**.

The current retrieval quality comes from **hybrid search**: a pgvector cosine
leg + a Postgres full-text (`tsvector`/`ts_rank_cd`) leg, fused with Reciprocal
Rank Fusion, then optionally Bedrock Rerank. Any replacement must preserve this.

---

# Part 2 — Options evaluated

| Option | Results | Speed | One place | VPC | Cost | Local dev | Verdict |
|---|---|---|---|---|---|---|---|
| **Keep Postgres/pgvector (current)** | best | ms | yes | ⚠️ VPC | ~$12–30/mo idle | Floci supports it | best results, VPC pain |
| **Aurora Serverless v2 + Data API** | best | ms | yes | ✅ no (Data API) | ~$44/mo min or cold start | works | keeps SQL, big rewrite + Data API limits (1 MB, 45 s) |
| **DynamoDB native vectors + custom lexical** | good | ms | yes | ✅ none | cheap metadata, vector meters | ❌ not emulated | fast, but hand-rolled BM25 |
| **DynamoDB + OpenSearch Serverless** | best | ms | source + index | ✅ none | ~$175/mo warm (1 OCU) or 10–30 s cold start | ❌ not emulated | native hybrid, fixed cost / cold start |
| **S3 Vectors + S3 term index (Design B)** | good | 100–300 ms | source + index | ✅ none | $0.023 + $0.06/GB-mo, no idle floor | S3 emulated; vectors need local mode | **chosen** |
| **S3-only brute force** | exact | slow at scale | yes | ✅ none | cheapest storage | works | O(corpus)/query, breaks at max quota |

### Key facts that drove the decision

- **DynamoDB has native vector search** (GA Aug 2026): `SearchVectors`, COSINE /
  DOT_PRODUCT / EUCLIDEAN, ≤4096 dims, inline filters (equality only), TopK ≤100,
  on-demand only, ≤5 vector indexes/table, **asynchronous indexing after write**.
  It is scalable (AWS: "trillions of vectors") but has **no full-text search**.
- **S3 Vectors** (GA Dec 2025): serverless, no cold start, strongly consistent,
  ~100–300 ms, `$0.06/GB-mo`, 2 B vectors/index, 10,000 indexes/bucket, rich
  filterable metadata. **Vector-only — no lexical search.**
- **OpenSearch Serverless**: Classic has a ~$350/mo 2-OCU floor; NextGen scales
  to zero but has a **10–30 s cold start** (can time out API Gateway's 29 s cap).
  It is the only store with **native hybrid (vector + BM25 + RRF)**.
- **The keyword index is the cost/scalability trap.** A DynamoDB term-posting
  index is ~150 postings per KB of text. At 500 MB that's ~$62 one-time to build;
  at 10 GB ~$1,250 one-time and ~$25/mo. DynamoDB storage is also ~10× S3
  (`$0.25` vs `$0.023/GB-mo`) and vectors are billed twice (base item + index).
- **S3 has no query engine.** "Do it in Lambda" means full-scan per query unless
  you build an index in S3. Design B builds that index in S3.

### Decision

Go with **Design B**: DynamoDB for operational data, **S3 Vectors** for the
semantic leg, **S3 objects** for the keyword (BM25) index and retrieval
artifacts. This keeps DynamoDB cheap (small metadata only), avoids the posting
write-amplification cost, needs no VPC, and keeps local S3 dev working. The
accepted trade-off is S3 Vectors' 100–300 ms semantic latency (with a
`VECTOR_STORE=dynamodb` switch if ms is ever required).

---

# Part 3 — Locked decisions

1. **Prefix matching:** kept. Keyword search supports `term:*` prefix matching
   (plurals/inflections) via a per-first-char token catalog plus per-term posting
   objects.
2. **Parents:** stored as **S3 objects** (`index/<userId>/parents/<parentId>.json`),
   not DynamoDB items.
3. **Vectors:** **S3 Vectors** is primary. A
   `VECTOR_STORE=s3vectors|dynamodb|local` switch is retained so the semantic leg
   can later use DynamoDB native vectors (ms) or a local brute force without a
   rewrite.
4. **Term-object concurrency:** conditional `If-Match` PUT + bounded
   exponential-backoff retry. Correct at any concurrency (no lost updates).
   Upgrade path if one user ever ingests many documents concurrently: per-user
   FIFO serialization of the Index stage.
5. **health-check:** removed entirely (no database to ping). There is no
   `/health` route — API Gateway HTTP APIs only allow proxy integrations, so a
   MOCK route is not possible.
6. **Ingestion stages:** **3 — `extract+chunk → embed → index`**. Matches the
   existing code (`extract_document` already chunks), so it is the smallest
   change.
7. **Data-access model (mandatory, locked):** **single DynamoDB table +
   adjacency list, one item per entity.** A user is a *partition*
   (`pk=USER#<userId>`), not a single row; profile, settings, notifications, quota,
   each KB, each skill, each session are **separate items** distinguished by
   `sk`. Never store a user (or any aggregate) as one JSON blob.
8. **Keep large data out of DynamoDB (mandatory, locked):** embeddings →
   **S3 Vectors**; keyword postings, parent text, manifests, staged artifacts and
   uploads → **S3 objects**. DynamoDB holds **only small metadata**. Nothing
   binary/large/vector ever goes in a DynamoDB item.
9. **Reads are `GetItem`/`Query` only (mandatory, locked):** every hot-path read
   targets a known `pk` (+ optional `sk` prefix) and uses the three sparse
   overloaded GSIs. **No `Scan` on the request path.** No N+1 (batch-get, not
   per-row get).
10. **Write patterns (mandatory, locked):** atomic `ADD` counters live on their
    own item (`#QUOTA`); ephemeral items (sessions, events) carry a TTL
    (`expiresAt`); conditional writes give uniqueness; idempotent delete-then-write
    per document.

### Why these are non-negotiable (the speed argument)

- **One round trip per concern.** A user's data is one `Query` on the partition;
  a page needs its own item, not a whole-user read. This is what keeps the app
  fast and avoids N+1.
- **No 400 KB ceiling.** A single blob would hit DynamoDB's item limit as soon as
  a user has a few skills (100 KB each) or documents. Splitting is the only thing
  that scales.
- **No whole-blob write contention.** Counters update atomically; two concurrent
  uploads don't fight over one user object.
- **Small items = cheap, fast reads.** DynamoDB reads are rounded to 1 KB (4 KB
  for eventually-consistent). Small per-entity items keep RCU/latency low; a fat
  blob pays for every read.
- **The big data is in the cheap store.** Vectors/postings/parents are ~all of
  the bytes and live in S3 Vectors / S3 at a fraction of the cost. DynamoDB
  metadata is tiny, so the ~100 bytes/item overhead of splitting is noise.

---

# Part 4 — Goals / non-goals

**Goals**
- No VPC, no RDS, no Alembic migrations, no data backfill (app is greenfield).
- One database (DynamoDB) for operational data; S3 for vectors + search index.
- Search stays fast and relevance stays at least as good as the current hybrid.
- All existing routes/methods/responses work unchanged.
- No N+1 query patterns.
- Lower idle cost than RDS; no posting write amplification in DynamoDB.

**Non-goals**
- Multi-region / global tables.
- Cross-document transactions.
- Keeping the old Postgres code path alive.

---

# Part 5 — Architecture

```
API Gateway (JWT) ─► user-api        (all /v1 CRUD: KBs, documents, skills, settings)
                  └─► knowledge-mcp   (MCP tools + retrieval; direct invoke + HTTP)

S3 ObjectCreated (raw/ only) ─► EventBridge ─► SQS ─► ingestion-dispatcher ─► Step Functions
   Extract+Chunk (Lambda) → Embed (Lambda) → Index (Lambda)   (catch → MarkFailed)
EventBridge rate(10m) ─► ingestion-watchdog

DynamoDB   = operational data only (users, KBs, documents, tags, skills, events, quotas, sessions)
S3 Vectors = embeddings (one index per user)          ← semantic leg
S3 (data)  = raw, derived, parents, term postings, catalog, manifests  ← keyword leg + artifacts
Bedrock    = embeddings + optional rerank
```

No VPC. No NAT. No RDS. No DB migrations.

---

# Part 6 — DynamoDB — main table `get1agent`

Single-table design, adjacency list. Keys `pk` (S), `sk` (S). Three overloaded,
sparse GSIs. **No vectors, chunks, or postings in DynamoDB.**

| Entity | pk | sk | GSI | Key attributes |
|---|---|---|---|---|
| Identity (sub→userId) | `SUB#<sub>` | `#PROFILE` | — | userId, createdAt |
| User | `USER#<userId>` | `#PROFILE` | — | userId, sub, email, emailVerified, fullName, pictureUrl, createdAt, updatedAt, lastLoginAt |
| Settings | `USER#<userId>` | `#SETTINGS` | — | preferredTheme, timezone |
| Notification prefs | `USER#<userId>` | `#NOTIF` | — | emailOnWorkflowFailure, creditThresholdAlerts |
| Quota counters | `USER#<userId>` | `#QUOTA` | — | kbCount, fileCount, storageBytes (atomic `ADD`) |
| Knowledge base | `USER#<userId>` | `KB#<name>` | `g1pk=KB#<kbId>, g1sk=#META`; `g2pk=USER#<userId>, g2sk=KB#<updatedAt>#<name>` | kbId, name, description, status, embedModel, imageEmbedModel, embeddingDim, chunkSize, chunkOverlap, docCount, timestamps |
| Document | `KB#<kbId>` | `DOC#<lowerFileName>` | `g1pk=DOC#<docId>, g1sk=#META`; `g3pk=DOCSTATUS#<status>, g3sk=<updatedAt>#<docId>` | docId, kbId, userId, fileName, s3Key, contentType, sizeBytes, source, contentHash, status, chunkCount, imageCount, timestamps |
| Tag | `DOC#<docId>` | `TAG#<lowerName>` | `g2pk=USER#<userId>, g2sk=TAG#<lowerName>#<docId>` | name, description |
| Ingestion event | `DOC#<docId>` | `EVENT#<ts>#<seq>` | `g3pk=USER#<userId>#EVENT, g3sk=<ts>#<docId>` | stage, status, message, details, TTL |
| Skill | `USER#<userId>` | `SKILL#<lowerName>` | `g1pk=SKILL#<skillId>, g1sk=#META`; `g2pk=USER#<userId>, g2sk=SKILL#<name>` | skillId, name, description, allowedTools, content, source, timestamps |
| Session (code-interp) | `USER#<userId>` | `CONV#<conversationId>` | — | sessionId, expiresAt (TTL), createdAt, lastUsedAt |

**GSIs (all sparse):**
- **GSI1 "byId"** — `gsi1pk`, `gsi1sk`: resolve KB/document/skill by UUID.
- **GSI2 "byUser/type"** — `gsi2pk=USER#<userId>`, `gsi2sk=<TYPE>#…`: list KBs,
  skills, tags, documents by user (prefix queries).
- **GSI3 "byStatus/time"** — `gsi3pk`: watchdog (`DOCSTATUS#processing`) and
  recent events (`USER#<userId>#EVENT`).

**Table config:** on-demand (`PAY_PER_REQUEST`); TTL attribute `expiresAt`.

## 6.1 Access-pattern matrix

| Operation | Store | Call |
|---|---|---|
| Upsert user / settings / prefs | DDB | `UpdateItem` / `PutItem` |
| Get account + settings | DDB | `GetItem` (2–3 keys) |
| Create KB (unique name) | DDB | `PutItem` `ConditionExpression=attribute_not_exists(pk)` |
| List KBs (+counts) | DDB | `Query g2pk=USER#<userId>, begins_with(g2sk,'KB#')` |
| Get KB by id | DDB | `Query g1pk=KB#<id>` |
| Delete KB | DDB | query docs → delete each (cascade walk) + S3 prefix delete + S3 Vectors delete |
| Presign upload | S3 | `generate_presigned_url` (key `raw/...`) |
| Complete upload | DDB+S3 | `HeadObject`, `UpdateItem status=uploaded`, emit event |
| Create inline doc | S3+DDB | `PutObject` + `PutItem` |
| List documents | DDB | `Query pk=KB#<kbId>, begins_with(sk,'DOC#')` |
| Delete document | DDB+S3+Vec | manifest → delete postings/vectors/parents + S3 prefix + doc item |
| List tags | DDB | `Query g2pk=USER#<userId>, begins_with(g2sk,'TAG#')` |
| List events | DDB | `Query g3pk=USER#<userId>#EVENT` (desc), optional kb filter |
| Skills CRUD | DDB | same patterns as KBs |
| Semantic search | S3 Vectors | `QueryVectors(topK=100, filter kbId/status)` |
| Lexical search | S3 | per-term `GetObject` + catalog prefix expansion |
| Watchdog | DDB | `Query g3pk=DOCSTATUS#processing, g3sk < now-75m` |
| Sessions | DDB | `PutItem`/`GetItem`/`DeleteItem`, TTL |

## 6.2 NoSQL patterns used

Single-table + adjacency list, overloaded sparse GSIs, composite keys,
conditional writes for uniqueness, atomic counters (`ADD`) for quotas, TTL for
sessions/events, denormalized counts (`docCount`), idempotent writes keyed by
`docId`/`contentHash`.

---

# Part 7 — S3 data bucket layout

```
s3://get1agent-data/
  raw/<userId>/<kbId>/<docId>/<fileName>              # original upload; ONLY prefix that triggers ingestion
  derived/<userId>/<kbId>/<docId>/text.md             # extracted text
  derived/<userId>/<kbId>/<docId>/images/<page>-<i>.<ext>
  derived/<userId>/<kbId>/<docId>/chunks.json         # staged parents + children
  derived/<userId>/<kbId>/<docId>/embeddings.json     # staged vectors
  index/<userId>/parents/<parentId>.json              # parent context for retrieval (small-to-big)
  index/<userId>/terms/<token>.json                   # postings: {df, postings:[{chunkId,docId,kbId,tf}]}
  index/<userId>/catalog/<c0>.json                    # token strings per first char (prefix expansion)
  index/<userId>/docs/<docId>/manifest.json           # chunkIds, parentIds, tokens (delete/rebuild)
```

- **Deterministic IDs:** `chunkId=<docId>#<ord>`, `parentId=<docId>#<ord>` — no
  id-generation round trips.
- **EventBridge rule filters `detail.object.key` prefix `raw/`**, so derived and
  index writes never re-trigger ingestion (a real efficiency win vs today's
  match-everything rule).
- `manifest.json` lists the document's `chunkId`s, `parentId`s and tokens so
  delete/re-index removes exactly its vectors, parents and postings without
  scanning.

---

# Part 8 — S3 Vectors — embeddings

- **One vector index per user** (`idx-<userId>`), created lazily on first
  KB/ingest. S3 Vectors supports 10,000 indexes per vector bucket. Per-user keeps
  query cost tiny (query cost scales with index size) and isolates tenants.
- Vector key = `chunkId`; dimension **1024**; distance **COSINE**.
- **Filterable metadata (≤2 KB / ≤50 keys):** `kbId`, `status`, `page`,
  `parentId`, `tokenCount`.
- **Non-filterable metadata:** `text` (chunk content), `kbName`, `fileName` — so
  a search result hydrates with **no DynamoDB join**.
- Writes batched via `PutVectors` (≤500 vectors/request; 128 KB minimum per PUT).
- Deletes via `DeleteVectors` (by key) on re-index and document/KB delete.

---

# Part 9 — Retrieval (implemented in `knowledge-mcp`) — no N+1

1. Resolve user + knowledge bases (DynamoDB).
2. Embed the query (Titan V2 prod / Ollama local) — existing code path.
3. **Run both legs in parallel** (`asyncio.gather`):
   - **Semantic:** one S3 Vectors `QueryVectors` on the user's index, `topK=100`,
     filter `kbId` and `status=ready`.
   - **Lexical:** tokenize the query (reuse the `lexical_tsquery` tokenizer in
     `shared/retrieval/hybrid.py`); for each term, **one `GetObject`** on
     `index/<userId>/terms/<token>.json`; for prefix matching, one `GetObject` on
     the catalog shard `index/<userId>/catalog/<c0>.json`, expand prefixes to exact
     tokens, then GET those term objects. Score BM25 in-Lambda
     (`k1=1.2, b=0.75`; `df` from the term object, `tokenCount` from vector
     metadata, `avgdl` from a per-user stats object).
4. RRF fuse (`RRF_K=60`, unchanged).
5. Hydrate parents: **one `GetObject` per unique parent** (bounded by topK,
   typically a handful).
6. Small-to-big dedupe (port `shared/retrieval/hybrid.py:241-262`), in-Lambda
   snippets (term-window highlighting replaces `ts_headline`), cap per document,
   group sources.
7. Optional Bedrock Rerank (unchanged `shared/retrieval/rerank.py`).
8. Return the **exact same** `chunks` / `sources` / `meta` shape as today.

**Round trips are fixed:** 1 vector query + ~10 term GETs + ~1 catalog GET + a
few parent GETs — independent of corpus size. No per-chunk or per-document
queries.

**Vector-store switch:** `VECTOR_STORE=s3vectors|dynamodb|local` selects the
semantic-leg implementation behind one interface.

---

# Part 10 — Ingestion — 3 stages + Step Functions

```
SQS ─► ingestion-dispatcher ─► Step Functions (STANDARD, TimeoutSeconds 3600)
  Extract+Chunk : download → parse text+images → chunk → derived/ + chunks.json
  Embed         : chunks.json → Bedrock → embeddings.json          [retry on throttling]
  Index         : PutVectors → parents + terms + catalog + manifest → status ready + counters
  Catch → MarkFailed → emit event
Watchdog (Lambda) : scheduled backstop (GSI3 DOCSTATUS#processing)
```

- Pass only S3 keys between states (well under the 256 KB Step Functions payload
  limit).
- Add per-state `Retry` with exponential backoff on
  `ThrottlingException` / `TooManyRequestsException` for the Embed state; keep
  the existing `DocumentNotReady` retry on Extract.
- **Idempotent:** skip if `contentHash` already `ready`; delete-then-write per
  document.
- **Failure:** mark `failed`, emit `failed` event, ack poison messages to the
  DLQ. Watchdog is the backstop.
- **Index write concurrency:** read-modify-write term/catalog objects with
  `If-Match` ETag and bounded retry on `412`. No cross-item transactions
  (DynamoDB `TransactWriteItems` caps at 100 items) — replaced by
  delete-then-write per document + status gating + manifest-driven cleanup.

---

# Part 11 — Lambda set (17 → 11)

| Before | After |
|---|---|
| `knowledge-bases` + `agent-skills` + `account-settings` | **`user-api`** |
| `knowledge-mcp` + `get-user-knowledge-bases` + `search-user-knowledge-bases` + `retrieval-query` | **`knowledge-mcp`** |
| `ingestion-dispatcher`, `ingestion-extract`, `ingestion-embed`, `ingestion-index`, `ingestion-mark-failed` | same names; extract already chunks (3-stage shape) |
| `ingestion-watchdog`, `web-search`, `code-interpreter`, `mcp-tester` | unchanged |
| `health-check` | **removed** (no `/health` route) |

Per-search Lambda invokes drop **3 → 1**. Per-upload stays staged through Step
Functions (per locked decision 6).

---

# Part 12 — API surface — unchanged

Every existing route/method/status/response is preserved:

- `GET/POST /v1/knowledge-bases`
- `GET /v1/knowledge-bases/tags`
- `GET /v1/knowledge-bases/events`
- `GET/DELETE /v1/knowledge-bases/{id}`
- `POST /v1/knowledge-bases/{id}/documents/presign`
- `POST /v1/knowledge-bases/{id}/documents/inline`
- `POST /v1/knowledge-bases/{id}/documents/{docId}/complete`
- `DELETE /v1/knowledge-bases/{id}/documents/{docId}`
- `GET/POST /v1/agent-skills`, `GET /v1/agent-skills/tools`, `POST /v1/agent-skills/parse`
- `GET/PUT/DELETE /v1/agent-skills/{id}`
- `GET/POST /v1/user/settings`
- `POST /mcp`, `POST /mcp/web-search`, `POST /mcp/code-interpreter`
- `GET /v1/admin/mcp/tools`, `POST /v1/admin/mcp/call`

Do not add `PATCH` aliases unless requested.

---

# Part 13 — Local development

- Floci already emulates **S3** → the raw/derived/index data paths work locally
  as-is.
- Add **DynamoDB Local** to `infra/local/floci/docker-compose.yml` (Floci does
  not emulate DynamoDB today; `code-interpreter` currently fakes it in-process).
- `VECTOR_MODE=local`: brute-force cosine over a local vector file (same pattern
  as `EMBED_MODE` / `RERANK_MODE` / `CODE_INTERPRETER_MODE`).
- Update `infra/local/floci/init/ready.d/10-provision.py` to create the table +
  GSIs and the SQS/EventBridge rule, and to skip S3 Vectors.
- Keep the `*_MODE=local` convention; do not add Floci-specific branches to
  application code.

---

# Part 14 — Infrastructure changes

**Delete**
- `infra/terraform/modules/network` (VPC)
- `infra/terraform/modules/rds`
- `infra/terraform/modules/lambda_rds`
- `backend/migrations/*`
- `.github/workflows/migrate.yml`
- `infra/scripts/migrate*.sh`, `infra/local/floci/migrate.sh`
- jumpbox, all `DB_*` env vars, all Lambda `vpc_config`

**Add**
- DynamoDB `get1agent` (on-demand) + GSI1/2/3
- S3 Vectors vector bucket (+ per-user indexes created lazily)
- SQS queue + DLQ
- EventBridge rule with `raw/` prefix filter
- IAM: DynamoDB CRUD, S3, `s3vectors:*`, Bedrock (and
  `dynamodb:SearchVectors` only if the DynamoDB vector switch is used)

**Update**
- `infra/terraform/envs/prod/backend.tf`, `api_gateway.tf`, ingestion module
- `infra/aws/*` deploy scripts (remove migration/jumpbox steps)
- `backend/services/registry.json` (remove health-check; add user-api)
- `AGENTS.md` (architecture, local dev, migrations sections)

---

# Part 15 — Performance & cost

**Latency**
- No VPC ENI cold start, no TLS/IAM DB handshake, no Lambda-to-Lambda chain.
- Warm path ≈ S3 Vectors (100–300 ms) ∥ term GETs (~10–30 ms each, parallel)
  + a few parent GETs + optional rerank.
- Cold start is much faster than today.
- **Honest caveat:** the S3 Vectors semantic leg is slower than pgvector HNSW
  (ms). The `VECTOR_STORE=dynamodb` switch restores single-digit-ms latency if
  needed.

**Cost**
- DynamoDB stores only small operational metadata → no posting write
  amplification.
- S3 Standard `$0.023/GB-mo`; S3 Vectors `$0.06/GB-mo`.
- No always-on RDS instance and no OpenSearch floor → idle cost approaches `$0`;
  pay per use.

---

# Part 16 — Risks & mitigations

| Risk | Mitigation |
|---|---|
| S3 term read-modify-write contention | Conditional `If-Match` PUT + bounded retry; upgrade path: per-user FIFO serialization of the Index stage |
| S3 Vectors latency (100–300 ms) | `VECTOR_STORE=dynamodb` switch |
| S3 Vectors not emulated locally | `VECTOR_MODE=local` brute force |
| Prefix expansion GET count | Catalog shard keeps it to ~1 extra GET |
| Hand-rolled BM25 quality | Tune `k1`/`b`; rerank on top; compare against current results |
| S3 event fan-out from index writes | `raw/` prefix filter on the EventBridge rule |
| No transactions / cascades | Manifest-driven cleanup + idempotent status-gated writes |
| Single ingestion Lambda 15-min cap | 3-stage Step Functions with per-stage timeout; split Embed if ever needed |

---

# Part 17 — Build order (file-by-file)

## Phase 1 — Shared layer
- Add `backend/services/shared/dynamo/`
  - `client.py` (table resource, config from env)
  - `keys.py` (key builders)
  - `batch.py` (BatchGetItem/BatchWriteItem helpers)
  - `repositories/{users,settings,quotas,knowledge_bases,documents,tags,skills,events,sessions}.py`
- Add `backend/services/shared/search/`
  - `layout.py` (S3 key builders for raw/derived/index)
  - `s3_vectors.py` (PutVectors / QueryVectors / DeleteVectors; per-user index)
  - `term_index.py` (postings + catalog read/write with conditional PUT; BM25)
  - `hybrid.py` (RRF / hydration / snippets — ported from `shared/retrieval/hybrid.py`)
- Rewrite `shared/users.py`, `shared/quotas.py` to DynamoDB
- Keep `shared/ingestion/{chunking,extractors,embeddings,config}.py`,
  `shared/skills/*`, `shared/observability.py`
- Delete `shared/db/*`, `shared/models/*`, `shared/retrieval/*` (superseded)

## Phase 2 — `user-api`
- Merge `knowledge-bases` + `agent-skills` + `account-settings` into one router
- Port handlers to the repositories; atomic quota counters; conditional
  uniqueness; preserve status codes and response bodies

## Phase 3 — Ingestion
- `ingestion-extract` → extract + chunk, write `derived/` + `chunks.json`
- `ingestion-embed` → unchanged shape, read `chunks.json`, write `embeddings.json`
- `ingestion-index` → S3 Vectors `PutVectors` + parents + terms + catalog +
  manifest + DynamoDB status/counters
- `ingestion-dispatcher` → parse `raw/` key, start Step Functions
- `ingestion-mark-failed`, `ingestion-watchdog`
- Update `infra/terraform/modules/ingestion/statemachine.asl.json` (3 stages)

## Phase 4 — `knowledge-mcp`
- Merge `get-user-knowledge-bases` + `search-user-knowledge-bases` +
  `retrieval-query` into one Lambda
- Delete those three services

## Phase 5 — Tools
- `backend/tools/code-interpreter/src/sessions.py` → main table + TTL
- `backend/tools/web-search` → unchanged

## Phase 6 — Infra
- Delete VPC/RDS/migrations (see Part 14)
- Add DynamoDB table + GSIs, S3 Vectors, SQS + DLQ, EventBridge `raw/` rule, IAM
- Strip `vpc_config` + `DB_*`; update `infra/aws/*`

## Phase 7 — Local dev
- DynamoDB Local in `docker-compose.yml`
- `VECTOR_MODE=local` brute force
- Update `10-provision.py` + `env.example`

## Phase 8 — Docs/registry
- `backend/services/registry.json`, `AGENTS.md`

## Phase 9 — Validation
- Route-by-route CRUD tests (KBs, documents, tags, events, skills, settings)
- Ingestion end-to-end (upload → ready → searchable)
- Retrieval relevance comparison vs the current hybrid results
- Delete/cascade correctness (KB delete, document delete, re-index)

---

# Part 18 — Open questions

None. All decisions in Part 3 are locked. Record any change here before
deviating.

## Deviations (recorded during implementation, 2026-09-14)

- **`/health` removed entirely (no route, no Lambda).** API Gateway **HTTP** APIs
  only allow `AWS_PROXY` / `HTTP_PROXY` integrations — a `MOCK` integration is
  rejected (`BadRequestException: ... may only be associated with proxy
  integrations`). Rather than keep a health Lambda, the route was dropped; the
  app does not call it. Part 3 decision 5 is updated accordingly.
- **`S3VectorsStore.query` requests `returnDistance=True`.** The QueryVectors
  response omits the score unless asked; cosine *distance* is converted to a
  similarity (`1 - distance`) so it matches the local store's score semantics.
- **`get-user-knowledge-bases` tags come from the tag GSI** (`kbId` is stored on
  each tag item) instead of walking documents per KB.
- **Internal `userId` is a short base32 id, not the Auth0 `sub`.** Every
  user-scoped key (`USER#<userId>`, S3 prefixes, the per-user vector index,
  sessions) uses the internal id. The id is `u_` + 16 Crockford base32 chars
  (`0-9a-z` minus `i l o u`), ~80 bits, minted with `secrets` and made unique by a
  conditional `PutItem` on `USER#<userId>` (regenerate on collision). The `sub` is
  stored as a `User` attribute and resolved through a strongly-consistent
  `SUB#<sub>` identity item (`GetItem`); a GSI was rejected because its eventual
  consistency could create duplicate profiles on first login. The
  `code-interpreter`/`mcp-tester`/`knowledge-mcp` MCP paths carry the internal
  `userId` as the transport identity key (`auth0Sub` is gone; there is no separate
  display code — the id is shown as-is).

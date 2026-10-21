# AGENTS.md

Context and rules for AI coding agents working in this repository.
Edit this file freely — opencode loads it automatically as project context.

## Project

`get1agent` monorepo.

```
frontend/              React + TypeScript + Tailwind (Vite)
backend/
  services/            Lambda apps, grouped by category (see below)
  services/apis/       user-api
  services/admin/      admin-console
  services/mcp/        knowledge-mcp, code-interpreter, http-fetch, storage, browser, custom-tools, mcp-connections
  services/ingestion/  ingestion-{dispatcher,extract,embed,index,mark-failed,watchdog}
  services/scheduler/  scheduled agent/workflow runs
  services/agent-run/  AgentCore control-plane Lambda + MicroVM proxy
  services/integration-tests/   moto + in-memory S3 integration tests
  agents/              AgentCore runtime (agentflow: single-agent; workflow: multi-agent)
  ai-assistant/                 AI Assistant Lambda (LangChain Deep Agents) + src/* — one zip, two routes
  packages/            shared modules: core, data, retrieval, ingestion
infra/                 Terraform, deploy scripts, local Floci stack
```

## Current status

- The platform is **fully AWS-native on 10+ AWS services**: embeddings, rerank,
  every LLM call, the agent platform, tracing and caching all run on AWS. The AI
  layer is **Amazon Bedrock** (Titan embeddings + multimodal, Bedrock Rerank, the
  curated models, Guardrails, prompt caching, structured outputs, batch inference)
  and **AgentCore** (Runtime, Code Interpreter, Memory, Policy, Gateway, Identity,
  Registry, Evaluations, Optimization, Browser). Web search is **Amazon Bedrock
  Web Search** (the gateway's built-in `web-search` connector, no model access
  required), so the only deliberate non-AWS dependencies are **Auth0** (identity)
  and **Cloudflare** (DNS/CDN). Model ids, quotas and the account's Bedrock limits are documented
  under "Agent runtime"; the cost/latency levers under "Bedrock cost & latency
  levers".

## Architecture

The backend is **fully serverless**: managed AWS services, scaled automatically
and billed per request.

- **DynamoDB** (single table `get1agent`) holds all operational data.
- **S3 Vectors** holds the semantic (embedding) index; **S3 objects** hold the
  keyword (BM25) index, parents, manifests and staged artifacts.
- Every Lambda reaches DynamoDB, S3, S3 Vectors and Amazon Bedrock over public
  HTTPS endpoints.
- The frontend talks to API Gateway only; uploads use presigned S3 URLs.

### Lambda code layout — bundled dependencies (no layers)

Deployables live under `backend/services/` (all Lambda apps, including the
`web-search`/`code-interpreter` MCP servers) and `backend/agents/`. Shared
application code lives once in **`backend/packages/`** as four top-level modules
(`core`, `data`, `retrieval`, `ingestion`) and is **bundled into each Lambda's
zip**. **Third-party dependencies are also bundled per Lambda** (no Lambda layers):

```
packages/core/       core       auth, mcp_server, mcp_client, storage, json_utils, logging
packages/data/       data       client, keys, repositories/*
packages/retrieval/  retrieval  layout, s3_vectors, term_index, maintenance, embedding/
packages/ingestion/  ingestion  pipeline, chunking, extractors, actions
```

Each app keeps its Lambda entry point as `handler.py` at the app root and the
rest of its code in `src/`; the `Makefile` copies `handler.py`, `src/`, the
shared modules it uses, **and all third-party dependencies** to the zip root and zips it.

**Dependencies are defined per Lambda in `pyproject.toml`** and installed via `uv sync` at build time:

| Lambda | Key Dependencies |
|---|---|
| `user-api` | `python-dateutil`, `tzdata`, `redis` |
| `knowledge-mcp` | `awslabs.mcp-lambda-handler`, `boto3`, `python-dateutil`, `tzdata`, `redis` (the exact cache, the semantic cache and the Bedrock token bucket all use Redis when `REDIS_URL` is set) |
| `code-interpreter`, `http-fetch`, `storage`, `mcp-connections`, `browser` | `awslabs.mcp-lambda-handler`, `boto3`, `python-dateutil`, `tzdata` |
| `custom-tools` | `awslabs.mcp-lambda-handler`, `boto3`, `python-dateutil`, `tzdata`, `redis`, `requests`, `beautifulsoup4` (the last two mirror the AgentCore sandbox so `CUSTOM_TOOLS_MODE=local` behaves like prod; `lxml` is intentionally omitted — its native wheel isn't portable, so tools parse HTML with `BeautifulSoup(..., "html.parser")`) |
| `ingestion-extract` | `pymupdf`, `python-docx`, `openpyxl`, `python-dateutil`, `tzdata` |
| `ingestion-embed` | `python-dateutil`, `tzdata`, `redis` (embedding cache + Bedrock token bucket) |
| `admin-console`, `scheduler` | `python-dateutil`, `tzdata` |
| Other ingestion Lambdas | None (lightweight) |

**No Lambda layers** — simpler deployment, easier local development.

App-local code stays in the app's `src/` package: `src.skills`,
`src.search` (hybrid-search orchestration), `src.service`/`src.bedrock`
(Bedrock Web Search client), and `src.guard`/`src.sessions`. Layer membership and per-app packages are
declared in `backend/registry.json`; `agents/` is AgentCore runtime and is
excluded from the Lambda build.

### DynamoDB single table

Keys `pk`/`sk` (adjacency list) plus three sparse overloaded GSIs. No vectors,
chunks or postings in DynamoDB.

| Entity | pk | sk | GSI |
|---|---|---|---|
| Identity (sub→userId) | `SUB#<sub>` | `#IDENTITY` | — |
| User | `USER#<userId>` | `#PROFILE` | — |
| Settings | `USER#<userId>` | `#SETTINGS` | — |
| Notification prefs | `USER#<userId>` | `#NOTIF` | — |
| Quota counters | `USER#<userId>` | `#QUOTA` | — |
| Consent | `USER#<userId>` | `#CONSENT` | — |
| Knowledge base | `USER#<userId>` | `KB#<name>` | `byId`; `byUser` (`KB#<updatedAt>#<name>`) |
| Document | `KB#<kbId>` | `DOC#<lowerFileName>` | `byId`; `byStatus` (`DOCSTATUS#<status>`) |
| Tag | `DOC#<docId>` | `TAG#<lowerName>` | `byUser` (`TAG#<lowerName>#<docId>`) |
| Ingestion event | `DOC#<docId>` | `EVENT#<ts>#<seq>` | `byStatus` (`USER#<userId>#EVENT`) |
| Skill | `USER#<userId>` | `SKILL#<lowerName>` | `byId`; `byUser` |
| Custom tool server | `USER#<userId>` | `CSERVER#<slug>` | `byId` |
| Custom tool | `USER#<userId>` | `CTOOL#<slug>#<name>` | `byId` |
| Agent | `USER#<userId>` | `AGENT#<lowerName>` | `byId`; `byUser`; `byStatus` (`AGENTLIB#public`) |
| Workflow | `USER#<userId>` | `WORKFLOW#<lowerName>` | `byId`; `byUser` |
| Storage file | `USER#<userId>` | `STORAGE#<fileId>` | — |
| Vault secret | `USER#<userId>` | `VAULT#<name>` | `byId` (encrypted value; `name` is the reference slug) |
| Guardrail | `USER#<userId>` | `GUARDRAIL#<name>` | — (Bedrock guardrail; `name` is the app slug) |
| Session (code-interp) | `USER#<userId>` | `CONV#<conversationId>` | — |
| Conversation | `USER#<userId>` | `CHAT#<globalId>` | `byId` (`CHATAGENT#<agentId>`); `byUser` (`CHAT#<updatedAt>#<id>`) |
| Playground session | `USER#<userId>` | `PGSESSION#<sessionId>` | `byUser` (`PGSESSION#<updatedAt>#<id>`) |
| Conversation counter | `COUNTER#conversations` | `#SEQ` | — |
| Platform settings | `PLATFORM#SETTINGS` | `#FLAGS` | — (admin flags incl. the network kill switch) |
| Network rate window | `RATE#custom-tools#<userId>` | `W#<window>` | — (TTL; atomic per-window counter) |
| Rate window (HTTP API) | `RATE#<policy>:<window>#<userId>` | `W#<window>` | — (TTL; DynamoDB fallback when Redis is down) |
| Run feedback | `USER#<userId>` | `FEEDBACK#<runId>` | — |
| MCP connection | `USER#<userId>` | `MCPCONN#<connId>` | — |
| MCP OAuth state | `USER#<userId>` | `MCPSTATE#<state>` | — (TTL, single-use) |
| Eval run | `USER#<userId>` | `EVALRUN#<runId>` | `byUser` (`EVALRUN#<updatedAt>#<id>`) |
| Eval case result | `EVALRUN#<runId>` | `CASE#<caseId>` | — |
| Support ticket | `USER#<userId>` | `SUPPORT#<ticketId>` | `byStatus` (`SUPPORT#all`) |
| Support message | `SUPPORT#<ticketId>` | `MSG#<createdAt>#<seq>` | — |
| Security report | `USER#<userId>` | `SREPORT#<reportId>` | `byStatus` (`SREPORT#all`) |
| Notification | `USER#<userId>` | `NOTIF#<id>` | — (TTL 90d) |
| User memory (local fallback) | `USER#<userId>` | `MEM#<memId>` | — (prod uses AgentCore Memory) |
| AI Assistant conversation | `USER#<userId>` | `AICHAT#<id>` | `byUser` (`AICHAT#<updatedAt>#<id>`) |
| AI Assistant feedback | `USER#<userId>` | `AIFEEDBACK#<runId>` | — |
| AI Assistant trace index | `USER#<userId>` | `AITRACE#<traceId>` | `byUser`; TTL 90d |
| AI Assistant eval run | `USER#<userId>` | `AIEVAL#<runId>` | `byUser` |
| AI Assistant rate window | `RATE#ai-assistant:<kind>#<bucket>` | `W#<window>` | — (TTL; per-IP-hash or per-user counter; DynamoDB fallback) |
| AI Assistant settings | `PLATFORM#SETTINGS` | `#AI_ASSISTANT` | — (kill switch, models, limits) |

AI Assistant (the in-product assistant, `docs/design/ai-assistant-architecture.md`) owns the
`AI_ASSISTANT*`/`RATE#ai-assistant` prefixes so nothing it writes can surface in the agent
chat sidebar (`CHAT#`), the agent trace list (`TRACE#`) or the agent feedback
table (`FEEDBACK#`). Its transcripts and trace trees live in S3
(`conversations/…`, `traces/…`); only small metadata items are in DynamoDB. The
platform knowledge base it answers from is the reserved scope `USER#platform` /
`KB#platform-docs` with the `idx-platform` vector index — an ordinary KB, so
retrieval reuses `retrieval.*` unchanged.

- **GSI1 `byId`** resolves a KB/document/skill/agent/workflow by UUID.
- **GSI2 `byUser`** lists a user's KBs/skills/agents/workflows/tags by prefix.
- **GSI3 `byStatus`** serves the watchdog (`DOCSTATUS#processing`), the recent
  events feed (`USER#<userId>#EVENT`), the public agent library
  (`AGENTLIB#public`), the admin user list (`USERS#all`, projected from each
  profile so the admin console never Scans), the scheduler (`SCHEDULES#enabled`)
  and the admin support/security inboxes (`SUPPORT#all`, `SREPORT#all`).
- Table is on-demand (`PAY_PER_REQUEST`), TTL attribute `expiresAt`.
- The DynamoDB client, key builders and repositories live in the `data`
  package (`backend/packages/data/`, import `data.*`) and are bundled
  into every Lambda that uses them. The internal
  `userId` is a **short base32 id**
  (`u_` + 16 Crockford chars, e.g. `u_7k3f9qz2mpx8n4rq`) minted on first login and
  keys all user data (DynamoDB partitions, S3 prefixes, ownership). The Auth0
  `sub` is stored as an attribute and resolved to the `userId` through the
  `SUB#<sub>` identity item — never used in a key.

**Data-access rules — mandatory, do not deviate:**

- **One item per entity.** A user is a *partition* (`pk=USER#<userId>`), not a row;
  profile/settings/notifications/quota/each KB/each skill/each session are
  **separate items** distinguished by `sk`. Never model an aggregate as one JSON
  blob.
- **DynamoDB holds only small metadata.** Embeddings → **S3 Vectors**; keyword
  postings, parent text, manifests, staged artifacts and uploads → **S3**. Never
  put vectors, chunks, postings or large/binary data in an item.
- **Reads are `GetItem`/`Query` only.** Target a known `pk` (+ `sk` prefix) and
  use the three sparse GSIs. **Never `Scan` on the request path. Never N+1**
  (batch-get, don't loop gets). `sub→userId` is a strongly-consistent `GetItem`
  on `SUB#<sub>` (never a GSI, which is eventually consistent and would duplicate
  profiles on first login).
- **Writes:** atomic `ADD` counters on their own item (`#QUOTA`); TTL
  (`expiresAt`) for sessions/events; conditional writes for uniqueness (including
  the `SUB#<sub>` identity binding); idempotent delete-then-write per document.
- These are what deliver the speed: one round trip per concern, no 400 KB item
  ceiling, no whole-blob write contention, cheap small reads, and the bulky data
  in the cheap store. See design Part 3 (locked decisions 7–10).

### S3 layout

```
raw/<userId>/<kbId>/<docId>/<fileName>            original upload; ONLY prefix that triggers ingestion
derived/<userId>/<kbId>/<docId>/text.md           extracted text
derived/<userId>/<kbId>/<docId>/images/<page>-<i>.<ext>
derived/<userId>/<kbId>/<docId>/chunks.json       staged parents + children
derived/<userId>/<kbId>/<docId>/embeddings.json   staged vectors
index/<userId>/parents/<parentId>.json            parent + children text (hydration)
index/<userId>/terms/<token>.json                 postings: {df, postings:[{chunkId,docId,kbId,parentId,tf,dl}]}
index/<userId>/catalog/<c0>.json                  token strings per first char (prefix expansion)
index/<userId>/docs/<docId>/manifest.json         chunkIds, parentIds, tokens (delete/rebuild)
index/<userId>/stats.json                         chunkCount, totalTokens, avgdl
index/<userId>/vectors.json                       local vector store (VECTOR_STORE=local)
mcp/<userId>/<connId>/tools.json                  cached remote MCP tool schemas
conversations/<userId>/<conversationId>.json      chat/builder transcript (all turns)
custom/<userId>/<slug>/<toolName>.py              user-defined MCP tool source (Playground)
playground/<userId>/<sessionId>.json               Playground build-chat transcript (messages + proposals)
evals/<userId>/<runId>/<caseId>.json               eval case artifact (contexts, answer, judge reasoning)
storage/<userId>/<fileId>/<fileName>              standalone user files (not ingested)
```

- Deterministic IDs: `chunkId=<docId>#<ord>`, `parentId=<docId>#<parentOrd>`.
- The EventBridge rule filters `detail.object.key` prefix `raw/`, so derived and
  index writes never re-trigger ingestion.

### Document ingestion

Uploads flow: browser PUTs to S3 via a presigned URL, then calls
`POST /v1/knowledge-bases/{id}/documents/{docId}/complete`.

- **Production**: S3 `ObjectCreated` (raw/) → EventBridge → SQS
  (`ingestion-docs` + DLQ) → `ingestion-dispatcher` (batch 5, partial batch
  failures) → **Step Functions Standard** (`ingest-{docId}-{eventToken}`) →
  `ingestion-extract` → `ingestion-embed` → `ingestion-index` (any stage failure
  → `ingestion-mark-failed`). Each stage is its own Lambda. A Graph RAG
  knowledge base runs one more optional stage after Index — see "Graph RAG".
- **3 stages** (+1 optional): `ingestion-extract` downloads + parses + **chunks**
  (writes `derived/` + `chunks.json`); `ingestion-embed` reads `chunks.json`,
  calls Titan on Bedrock (or Ollama locally), writes `embeddings.json`;
  `ingestion-index` writes vectors (S3 Vectors / local), parent objects, term
  postings, catalog, stats and the manifest, then sets `documents.status=ready`.
  For a **Graph RAG** knowledge base, `ingestion-graph-extract` then LLM-extracts
  the document's entities/relationships into the graph (state machine `Choice`,
  best-effort).
- The pipeline lives in the `ingestion` package
  (`backend/packages/ingestion/`, import `ingestion.*`); each
  `ingestion-*` Lambda is a thin handler that calls one stage action. Embedding
  config/clients live in `retrieval.embedding`. Heavy extractor deps
  (`pymupdf`, `python-docx`, `openpyxl`) ship in the `extra-tools` layer.
- Embeddings: selected by `EMBED_MODE` — **`bedrock`** (the default everywhere;
  Amazon **Titan Text Embeddings V2** for text and **Titan Multimodal
  Embeddings G1** for images). `local` (Ollama `mxbai-embed-large`) is an offline
  code path exercised only by the integration tests; the local Floci stack is
  bedrock-only. Image embeddings are **opt-in**
  (`EMBED_IMAGES=false` by default) because they are computed but not searched
  and Titan Multimodal is rate-limited to 20 RPM. Embedding calls are admitted
  through `core.ratelimit_bedrock` (global per-model token bucket, Redis-backed
  when available) before hitting Bedrock.
- Ingestion config (embedding model + chunk size/overlap + **retrieval mode**) is
  **per knowledge base**, set at creation (`knowledge_bases` columns; the UI
  calls it Hybrid RAG vs Graph RAG); the page-level "Workspace
  defaults" card only pre-fills the create dialog.
- `ingestion_events` (DynamoDB) is the append-only timeline the UI reads
  (`GET /v1/knowledge-bases/events`). The index stage updates `documents.status`
  (`processing`/`ready`/`failed`) and `knowledge_bases.status` follows via a
  `processingCount` counter.
- **Idempotent:** the index stage is delete-then-write per document
  (manifest-driven), so a retry or re-upload re-indexes cleanly.
- **Failure:** mark `failed`, emit a `failed` event, ack poison messages to the
  DLQ.
- A scheduled `ingestion-watchdog` (EventBridge `rate(10 minutes)`) fails any
  document left in `processing` past `STALL_THRESHOLD_MINUTES` (default 75),
  using GSI3. The threshold exceeds the state machine `TimeoutSeconds` (3600s).
- No CloudWatch alarms are provisioned. X-Ray (`enable_xray`, default true)
  traces the ingestion workers + state machine. Lambda log retention is 7 days.

### Retrieval & MCP tools

- **Hybrid search is always on** and runs **inside `knowledge-mcp`** (there is no
  separate retrieval Lambda):
  - **Semantic leg**: one S3 Vectors `QueryVectors` on the caller's per-user
    index (`idx-<userId>`), `topK=100`, filtered by `kbId` + `status=ready`.
  - **Lexical leg**: tokenize the query, prefix-expand via the catalog shard,
    `GetObject` each term, score BM25 in-Lambda (`k1=1.2, b=0.75`; `df` from the
    term object, `dl` from the posting, `avgdl` from `stats.json`).
  - Both legs run in parallel and fuse with Reciprocal Rank Fusion (`RRF_K=60`).
  - The semantic store is selected by `VECTOR_STORE=s3vectors|local` (a
    `dynamodb` value is reserved but not implemented).
- **Small-to-big retrieval**: only the small child chunks are embedded and
  searched. Each child points at a parent — a PDF source page (a huge page
  becomes several parents sharing the page number), or a fixed-size window for
  non-paginated formats. Hydration is **one `GetObject` per unique parent**; the
  parent object carries its children's text, so results return the parent's full
  `content`, the precise `matchedContent` child and a term-window `snippet`.
  Parents are deduplicated per document/page.
- Default child size is **512 tokens** with 64 overlap (config default in
  `packages/retrieval/.../embedding/config.py`), so children fit every embedder window.
- **Rerank is one shared implementation** (`retrieval/rerank.py`), used by both
  `knowledge-mcp` and AI Assistant so the two cannot rank differently. In
  `knowledge-mcp` it is **opt-in** (`rerank: true`) and never runs unless
  requested; AI Assistant reranks **by default** (`AI_ASSISTANT_RERANK=0` to turn
  it off), because there the fused order is what the answer and its citations are
  built from. `RERANK_MODE=bedrock` (the default) calls **Bedrock Rerank**
  (`amazon.rerank-v1:0` in `us-west-2` — it is not offered in ap-south-1, so the
  call is cross-region); `RERANK_MODE=local` calls a HuggingFace TEI cross-encoder
  (`reranker` container, `POST /rerank`, `--profile local-rerank` in the local
  stack); `none` skips it. If the reranker is unreachable the RRF order is
  returned instead of failing.
  - The inline-document enum is **`INLINE`**, not `INLINE_DOCUMENT`. The wrong
    value fails validation on every call, and because a reranker failure must
    degrade rather than raise, the only symptom is that ranking is never applied —
    `tests/test_rerank_bedrock.py` and the integration `test_rerank.py` pin it.
- **Identity is passed in the event** (`userId`, the internal UUID) for direct
  invokes, or resolved from the JWT `sub` for HTTP (via the `SUB#<sub>` item).
- **Each MCP server is its own Lambda** (`awslabs.mcp-lambda-handler`,
  stateless) exposing its tools over its own `POST /mcp…` route behind the Auth0
  JWT authorizer, plus the direct Lambda invoke transport. `knowledge-mcp` owns
  the knowledge tools (`POST /mcp`), `code-interpreter` owns `code-interpreter`
  (`POST /mcp/code-interpreter`), `http-fetch` owns `http-fetch`
  (`POST /mcp/http-fetch`), and `storage` owns `list-storage-files`,
  `read-storage-file`, `write-storage-file` and `delete-storage-file`
  (`POST /mcp/storage`).
  `web-search` is **not** a Lambda: it is the AgentCore Gateway's built-in
  `web-search` connector (see "Web search tool").
- Knowledge base names follow **S3-bucket-style rules** (lowercase letters,
  digits and hyphens; 3–63 chars; must start/end alphanumeric) and are unique
  per user (`uq_knowledge_bases_user_name`); the create handler returns `409` on
  a duplicate. Per-user limits: **30 knowledge bases, 50 files each, 100 MB
  storage** (`packages/data/.../repositories/quotas.py`).

### Graph RAG (Hybrid vs Graph retrieval)

Retrieval is **selectable per knowledge base**, and the two are **separate
paths**: the create dialog offers **Hybrid RAG** (vector + BM25 fusion) or
**Graph RAG** (a knowledge graph of the entities/relationships the documents
state, searched graph-first). A Graph KB pays a one-off extraction cost at
ingest; a hybrid search path is byte-identical to before, because graph
retrieval only ever reads the Graph-mode KBs in scope. **Graph is not fused with
hybrid** — it is its own retriever, and the hybrid legs answer only as its
fallback (see "Graph-first retrieval").

- **What the graph models.** Entities are typed nodes (`Person`, `Organization`,
  `Location`, `Product`, `Technology`, `Concept`, `Method`, `Metric`, `Date`,
  `Document`, `Other`) with a `name`, a one-line `description` and the
  `chunkIds`/`parentIds` where they were seen (**`MENTIONED_IN` is implicit** —
  no edges wasted on it). Relationships are **one generic edge per triple**
  carrying a typed `type` predicate (`WORKS_AT`, `PARTNERS_WITH`, `PRODUCES`,
  `DEPENDS_ON`, …), the **LightRAG/FalkorDB shape** rather than one graph
  relationship per predicate. This is the vocabulary GraphRAG systems model: the
  *relationships between the things* a corpus names, so a fact split across
  pages (Alice → Acme, Acme → Beta) is reachable as one connected unit instead
  of only by lexical/vector overlap.
- **Storage — no external graph database.** The graph is plain S3 JSON under
  `index/<userId>/graph/`: `nodes/<nodeId>.json`, `adj/<nodeId>.json` (both
  directions + relationship facts), `enames/<token>.json` (entity-name inverted
  index), `ecat/<c0>.json` (token catalog for prefix expansion),
  `docs/<docId>.json` (what one document contributed, for idempotent delete) and
  `stats.json`. Node ids are deterministic and **type-qualified**
  (`e_<sha1(type:name)[:16]>`, so "Jordan" (Person) ≠ "Jordan" (Location)); edge
  ids are `r_<sha1(from|REL|to)[:20]>`. Writes are read-modify-write with a
  conditional `If-Match` PUT. Entity **vectors** live in the same per-user S3
  Vectors index as the chunks but carry `kind="entity"` (and `status="entity"`),
  so chunk search — which filters `status="ready"` — can never surface them.
  Code: `backend/packages/retrieval/graph.py`.
- **Ingest stage (gated).** `ingestion-graph-extract`
  (`backend/packages/ingestion/graph.py`, `graph_extract_action`) reads the
  staged `chunks.json`, batches chunks, and makes **one Bedrock Converse call per
  batch** with a JSON Schema (structured outputs; prompt-only JSON on fallback)
  to extract entities + relationships. It then embeds each entity
  (`"<name> (<type>): <description>"`) and merges the document's contribution
  into the graph (**delete-then-write**, so a re-index/retry is clean). It runs
  **after Index** — `delete_document_index` now also clears a document's graph
  contribution, so the graph stage must not run before it — and it is **the last
  stage and best-effort**: the state machine's `GraphMode` `Choice` skips it for
  hybrid KBs, a per-batch model failure is counted (`failedBatches`) not raised,
  and any error records a `graph` event and leaves the document's hybrid index
  intact. Env: `GRAPH_EXTRACT_MODEL`, `GRAPH_EXTRACT_BATCH_CHUNKS`,
  `GRAPH_EXTRACT_MAX_CHUNKS`, `GRAPH_EXTRACT_MAX_TOKENS` (16000 — reasoning is
  disabled for this call, and a batch that still truncates is split and retried).
- **Graph-first retrieval** (`knowledge-mcp/src/search/graph.py` +
  `src/search/service.py`). A Graph-mode KB is answered by the graph, **not** by
  hybrid: `service.search` runs `search_graph` and **skips**
  `search_candidates` entirely, so no embedding/BM25 leg is paid for. Seeds are
  found two ways — a vector search over entity embeddings (paraphrase-tolerant)
  and a lexical lookup of the query's tokens in the entity-name index (precise) —
  then a bounded BFS traverses the graph (hop/score decay, node/edge/fan-out
  caps). Every visited node resolves to the parent chunks it was seen in
  (hydrated exactly as before), candidates carry
  `rrfScore = GRAPH_WEIGHT × decayed seed score` and `source: "graph"` (hybrid
  candidates carry `source: "hybrid"`), and the walked relationships
  (`subject/predicate/object`) ride along on the payload as `relationships` so
  the client can show *why* a passage is relevant.
- **Mixed selections.** A request that spans Graph and Hybrid KBs runs **each KB
  its own way** and **interleaves** the two ranked lists (round-robin, each list
  keeping its own order) — the scores live on different scales, so concatenating
  or score-sorting one list would bury the other. Nothing is fused across
  strategies.
- **Hybrid fallback.** When the graph has nothing (`GRAPH_RETRIEVAL_ENABLED` off,
  no seed entity, or no node resolves to a passage) the hybrid legs answer the
  query and the payload says so: `meta.graph.fallback = true` with a `reason`
  (`graph disabled` | `no matching entities` | `no linked passages`).
  `graph: false` on the call forces the hybrid path even on a Graph KB
  (`reason: "graph not requested"`); the runtime omits the flag (letting the KB
  mode decide) unless a run explicitly forces graph on, so an agent can never
  silently downgrade a graph KB. The `graph` flag is part of the exact- and
  semantic-cache keys. Env:
  `GRAPH_RETRIEVAL_ENABLED`, `GRAPH_HOPS`, `GRAPH_SEED_TOP_K`,
  `GRAPH_SEED_TOP_N`, `GRAPH_MAX_NODES`, `GRAPH_MAX_EDGES`, `GRAPH_MAX_FANOUT`,
  `GRAPH_DECAY`, `GRAPH_WEIGHT`, `GRAPH_MAX_RELATIONSHIPS`, `GRAPH_MAX_PARENTS`.
- **Surfaces.** A KB stores `retrievalMode` (`hybrid` | `graph`, fixed at
  creation) and returns it on list/detail; the ingestion Activity panel shows a
  **Graph** stage (entities · relationships) only for documents that ran one. The
  mode is the whole switch: the agent builder's knowledge card labels a Graph KB
  (`graph`) and explains that it is searched through its graph, and the chat's
  **Run settings** dialog names the selected Graph KBs — there is **no per-agent
  or per-run toggle** anymore (`config.knowledgeGraphRag` /
  `RunResourceOverrides.knowledgeGraphRag` are legacy: a `true` forces graph on,
  an absent/false value follows the KB). The run timeline shows the graph
  provenance from `tool.result.graph` — strategy, seed/node/passage counts, and
  the walked `subject → predicate → object` paths (capped at 12) — so a graph
  answer never looks like a plain hybrid hit. Frontend types live in
  `frontend/src/lib/knowledgeBases.ts` (`RETRIEVAL_MODES`),
  `frontend/src/lib/agents.ts`, `frontend/src/lib/agentRun.ts`
  (`AgentToolGraph`) and `frontend/src/lib/runState.ts`.
- **Local.** `ingestion-graph-extract` is provisioned by Floci like the other
  workers (real Bedrock Converse + Titan via the forwarded credentials); the
  local vector store is used for entity vectors and `RERANK_MODE=none`.
  Integration coverage: `backend/services/integration-tests/test_graph_rag.py`
  (store, traversal, extraction, the gated stage, and graph-first search with the
  hybrid fallback and the explicit `graph: false` opt-out).

### Caching (embeddings + knowledge search)

All three caches are **Redis-first on the normal request path**: the same Redis
instance (`core.redis_client`) backs the exact cache, the semantic cache and the
limiter, so one dependency covers all of them. Every backend is chosen by an
`auto` value that means "Redis when it answers, the managed AWS store
otherwise", and every cache operation swallows errors — a cache can never break
a request.

- The exact cache lives in **`core.cache`** (`backend/packages/core/cache.py`).
  Backend `CACHE_BACKEND` (default **`auto`**):
  - `auto` — **Redis** when it answers, the DynamoDB TTL item otherwise. A Redis
    miss is a miss; the DynamoDB store is consulted only when Redis is
    unavailable (so there is no per-key DynamoDB read on the hot path).
  - `redis` / `dynamodb` / `none` pin one backend (or disable it).
  Items are `pk=CACHE#<prefix><kind>`, `sk=<sha256>`, TTL `expiresAt` in
  DynamoDB; in Redis they are a plain `SET … EX` (batched with `MGET`/pipelines).
  Every call is a no-op when unavailable. Keys are
  `g1a:<kind>:<sha256(parts)>`; per-kind TTLs come from
  `CACHE_<KIND>_TTL_SECONDS` (`CACHE_SEARCH_TTL_SECONDS` 300,
  `CACHE_EMBEDDING_TTL_SECONDS` 2592000).
- It is used on the **normal request path only** — never in the Labs:
  - `retrieval.embedding.embeddings.embed_texts` caches vectors keyed by
    `(embed_mode, model, text)`; embeddings are deterministic, cached vectors are
    read/written in batches, and only misses hit Bedrock Titan / Ollama.
  - `knowledge-mcp` caches the whole search payload keyed by
    `(userId, query, kbNames, tags, rerank, topK, maxPerDocument)` so a repeated
    question skips embed + search + rerank (per-user scope; short TTL).
  - **Semantic cache** (`core.semantic_cache`): a near-duplicate query reuses the
    cached search payload. Backend `SEMANTIC_CACHE_BACKEND` (default **`auto`**):
    - `auto` — **Redis** when it answers, the platform **S3 Vectors** store
      otherwise; `redis` / `s3vectors` / `none` pin one.
    - **Redis path** (`core.semantic_cache_redis`): one **RediSearch** index per
      user per embedding dimension (`FT.CREATE`/`FT.SEARCH`, a `FLOAT32` vector
      field with `DISTANCE_METRIC COSINE` plus a `kbTag` TAG) holding the cached
      queries' embeddings — an in-memory ANN, far faster than the S3 Vectors
      round trip. It uses the raw `FT.*` commands, **not** `redisvl` (keeps numpy
      and its tree out of the Lambda zip). `kbTag` is a hash of the requirement
      set, so the TAG query never needs escaping. The returned score is cosine
      **distance**, so similarity = `1 − distance` and the same threshold
      applies.
    - **S3 Vectors path**: one index per user (the same store as the knowledge
      index); entries carry `kind="semcache"` so they never surface in knowledge
      search, and the payload lives in a cache TTL item referenced by the vector
      key. Stale vectors are ignored via `expiresAt`.
    - A hit requires similarity ≥ `SEMANTIC_CACHE_THRESHOLD` (0.95 — near
      identical only, measured: identical ≈1.0, close paraphrase ≈0.76) and the
      same knowledge-base set. Flow in `knowledge-mcp._search`: exact cache →
      embed → semantic lookup → real search → store exact + semantic.
      Env: `SEMANTIC_CACHE_ENABLED`, `SEMANTIC_CACHE_BACKEND`,
      `SEMANTIC_CACHE_THRESHOLD`, `SEMANTIC_CACHE_TTL_SECONDS` (600),
      `SEMANTIC_CACHE_MAX_BYTES` (200000).
    - **AI Assistant reuses it** (`src/retrieval.py`) under one shared
      `platform` namespace — the corpus is identical for every caller, so a
      question answered for one visitor warms the cache for all of them,
      guests included. The requirement signature is
      `{audience, allowAdmin, topK, rerank}` so an admin's passage list (which
      includes admin docs) can never be served to a non-admin. A hit skips the
      S3 Vectors query, the BM25 reads, parent hydration and the cross-region
      rerank; it does **not** skip the query embedding (the ANN needs the
      vector) or the answer generation. Its diagnostic stage is
      `semantic-cache-hit` and `metrics.retrieval` counts it as a cache hit.
      Its Lambda is configured Redis-first (`CACHE_BACKEND=auto`,
      `SEMANTIC_CACHE_BACKEND=auto`), with DynamoDB / S3 Vectors only as the
      fallback.
- **Cache hits are visible.** `knowledge-mcp` stamps `meta.cache`
  (`{hit, kind, backend, similarity?}`) on every search result — `kind` is
  `exact` / `semantic` / `none` and `backend` is the store that answered
  (`redis` / `dynamodb` / `s3vectors`). The agent runtime lifts it onto the
  `tool.result` frame (`cache`) so the run timeline shows a **cache badge on the
  tool call** (e.g. "redis", with a match % for a semantic hit), and emits a
  CloudWatch EMF metric (`get1agent/cache`, `CacheHit`) so hit rate is visible
  without reading a transcript.
- **Single-flight** (`core.singleflight`, reuses the configured cache backend —
  a Redis `SET NX EX` lock in production, a DynamoDB conditional `PutItem`
  otherwise — and fails open): the knowledge search path is wrapped in a lock so
  N concurrent identical requests compute once and the rest wait for the cached
  result. This
  is cost deduplication — **not** rate limiting (see "Rate limiting (Redis GCRA
  + DynamoDB fallback)" below). Env: `SINGLE_FLIGHT_ENABLED` (default true),
  `SINGLE_FLIGHT_LOCK_SECONDS` (20), `SINGLE_FLIGHT_WAIT_SECONDS` (6).
- **API Gateway throttling** (coarse, common to all clients): the HTTP API has a
  stage-level default (`stage_throttle_burst_limit` / `stage_throttle_rate_limit`,
  defaults 100 / 50) plus per-route overrides on the heavy MCP routes and
  `/v1/agent-run/session` (`throttle_burst_limit` / `throttle_rate_limit` in
  `lambda_routes`). This is volumetric protection **before** Lambda; per-user
  fairness is `core.ratelimit` (Redis GCRA, DynamoDB fallback) — see "Rate
  limiting (Redis GCRA + DynamoDB fallback)".
- **Not cached:** the Playground, Evaluations/judges, and anything with tool
  calls or side effects — Labs must show fresh, uncached output.

### Rate limiting (Redis GCRA + DynamoDB fallback)

Per-identity request limiting lives in **`core.ratelimit`** — a package whose
parts are one concern each: `policy.py` (the shapes and the route map), `gcra.py`
(the Redis primitive), `fixed.py` (the DynamoDB fallback) and `__init__.py` (the
public API: `check`, `check_windows`, `allow`, `current`, `describe`). It is one
implementation for the three surfaces that need it — the HTTP API, AI Assistant
and the custom-tool sandbox — so an identity can never be judged differently by
each.

- **Primitive: GCRA** (a leaky-bucket-with-tolerance, i.e. one timestamp per
  identity + window) running as an atomic **Lua** script in **Redis**. One
  round-trip consumes every window of a policy at once, so a refusal is exact: a
  caller stopped by the day cap is not also charged against the hour cap. Reads
  (`describe` / `current`) use a second Lua script (`PEEK`) that never consumes a
  slot. Key layout: `g1a:rl:{<identity>}:<policy>:<window>`.
- **Backend `RATELIMIT_BACKEND`** (default **`auto`**): Redis when it answers, the
  DynamoDB fixed-window counter (`fixed.py`) otherwise — a dead cache degrades the
  limiter, it can never become an open door. `redis` fails **open** when
  unreachable (a single-backend deployment must not block traffic on an optional
  dependency), `dynamodb` is the original behaviour, `none` disables it. Every
  call returns a decision rather than raising; the limiter can never take a
  request down with it.
- **The Bedrock token bucket shares the same backend.** `core.ratelimit_bedrock`
  (which admits every model/embedding call) is Redis-first too
  (`BEDROCK_RATELIMIT_BACKEND`, defaulting to `RATELIMIT_BACKEND`): it consumes a
  **1-second** Redis GCRA window (`g1a:rl:{model:<id>}:bedrock:second`) so a
  throttle reports a sub-second `wait`, and falls back to the DynamoDB
  per-model counter. Per-model RPMs come from `BEDROCK_RATELIMIT_<MODEL>_RPM` /
  `BEDROCK_RATELIMIT_<MODEL>_PER_WINDOW`.
- **Redis URL** is a **SSM Parameter Store SecureString** (`REDIS_URL_SSM_PARAM`),
  fetched once per container and cached. The client (`core.redis_client`) is lazy,
  uses sub-second timeouts, a couple of pooled connections and a circuit breaker,
  and returns `None` on any failure so a Redis problem adds no request latency
  (`health()` reports it).
- **Policies** (`policy.py:DEFAULTS`) are per surface, not one flat number: each
  is an ordered list of windows (shortest first). E.g. `agent.session` 10/min +
  120/hour, `evals.run` 10/hour + 50/day, `knowledge.write` 300/hour + 2000/day,
  `api.default` 600/min + 10 000/hour. `ROUTE_RULES` maps `(method, path)` to a
  policy; **only mutating verbs are limited** (`SAFE_METHODS` = GET/HEAD/OPTIONS),
  because the limiter bounds work that *spends* (a model call, an upload, a
  sandbox run) and leaving reads out keeps the Redis op count low on a small
  instance. `v1/traces` and `v1/ai-assistant` are exempt. Any policy is
  overridable at runtime with the `RATELIMIT_POLICY` JSON object
  (`{"evals.run": [[10, 3600]], "api.default": []}` — an empty list means no
  cap); `RATELIMIT_<KIND>_PER_WINDOW` sets one window's limit.
- **The HTTP API** enforces it in the `user-api` `lambda_handler` middleware
  (`_enforce_ratelimit`): the identity is the internal `userId`, the policy comes
  from the route, and every limited response carries
  `X-RateLimit-Limit/Remaining/Reset` + `Retry-After`; a denial is a `429` with a
  JSON body naming the window. `GET /v1/user/ratelimit` returns the caller's
  snapshot (`ratelimit.describe`, read-only) for the **Usage** page's Rate limits
  card (backend in force + per-policy window progress).
- **AI Assistant** shares the limiter under policy `ai-assistant` (windows
  `ai-assistant-burst` 3 min / `-hour` / `-day`) — see its own section.
- **The API Gateway stage/route throttle stays the volumetric shield in front of
  Lambda** (see "API Gateway throttling" above); Redis enforcement is the
  per-identity layer **inside** Lambda, where the JWT's `userId` is known. A
  gateway-level limiter was rejected: an authorizer cannot return a `429` or rate
  headers, and it cannot cover the agent-run MicroVM path (below). That path
  bypasses API Gateway after the control-plane call, so it is bounded by the
  `agent.session` policy on `POST /v1/agent-run/session` and by AgentCore's own
  run budget.
- **Local:** `RATELIMIT_BACKEND=dynamodb` needs nothing extra; `auto`/`redis` use
  the `redis` compose service (see "Local development").

### Code interpreter tool

- `code-interpreter` (`backend/services/mcp/code-interpreter/`) is its own MCP server
  Lambda (`POST /mcp/code-interpreter`) owning the `code-interpreter` tool. It
  runs LLM-generated Python in **Bedrock AgentCore Code Interpreter** sandboxes
  (the restrictive system resource `aws.codeinterpreter.v1`, available in
  `ap-south-1`) — **no public internet, and heavy ML is blocked**, because this
  tool is for calculations. It is **outside the VPC** (AgentCore + DynamoDB are
  public endpoints). The MCP Builder's `custom-tools` sandbox instead runs on a
  **custom `aws_bedrockagentcore_code_interpreter` in PUBLIC network mode**
  (`get1agent-prod-mcp-tools`), so user-built tools can call web APIs.
- **Guard**: before any AWS call the guard runs a static AST pass that blocks
  exactly one family — heavy ML frameworks (`torch`, `tensorflow`,
  `transformers`, `sklearn`, …) — plus any names in `BLOCKED_MODULES`
  (`ALLOWED_MODULES` exempts). Everything else is permitted: process spawning
  (`subprocess`), `ctypes`, dynamic code (`eval`/`exec`/`importlib`), arbitrary
  third-party packages and package installation; the microVM remains the real
  isolation boundary. Every execution is also prefixed with an idempotent
  `sys.addaudithook` prelude. Network is the only other gate: when a sandbox is
  offline the HTTP(S) stack (`socket`/`ssl`/`urllib`/`requests`/…) is withheld;
  when it is granted `allow_network` (`CUSTOM_TOOLS_ALLOW_NETWORK`) the stack is
  reachable and the runtime hook counts outbound connections
  (`CUSTOM_TOOLS_MAX_CONNECTIONS`, 25/run) and refuses private/loopback/
  link-local/reserved/cloud-metadata addresses.
- The guard, AgentCore session/exec client and local-subprocess fallback live in
  the shared **`core.sandbox`** package (`packages/core/sandbox/`), used by both
  `code-interpreter` and `custom-tools` (`core.sandbox.run_code`).
- **Sessions**: one AgentCore session per `(userId, conversationId)` stored in
  the **main `get1agent` DynamoDB table** (`USER#<userId>` / `CONV#<thread>`) with a
  TTL (`expiresAt`) and capped at `CODE_INTERPRETER_MAX_SESSIONS_PER_USER` (1)
  with LRU eviction. A deterministic `clientToken` (`uuid5`) plus a conditional
  write dedupes concurrent invocations.
- **Timeouts**: `CODE_INTERPRETER_EXEC_TIMEOUT_SECONDS` (120) is enforced while
  streaming; on overrun the session is stopped. The code-interpreter Lambda
  timeout is 240s; `knowledge-mcp` (and `admin-console`) timeouts are 300s so the
  synchronous call chain fits. API Gateway caps HTTP integrations at 30s, so long
  runs must use direct invoke.
- **Local**: `CODE_INTERPRETER_MODE=local` runs the same guard + prelude in an
  isolated subprocess with `resource` limits (Floci does not emulate AgentCore).
  The Playground's `custom-tools` uses the same path via `CUSTOM_TOOLS_MODE=local`.

### Web search tool

- Web search is **Amazon Bedrock AgentCore Web Search** — a fully managed,
  MCP-compliant **built-in connector** attached to the AgentCore Gateway. There
  is **no web search Lambda** and **no model access** to request: the gateway
  snapshots the connector's schema and exposes it as `web-search___WebSearch`
  (`connectorId: "web-search"`, `target_configuration.mcp.connector`).
- The gateway invokes the connector with **its own role**
  (`bedrock-agentcore:InvokeWebSearch` on
  `arn:aws:bedrock-agentcore:<region>:aws:tool/web-search.v1`); callers only need
  `bedrock-agentcore:InvokeGateway`. The tool takes `query` (≤200 chars) and
  `maxResults` (1–25), plus an optional `filters` domain denylist.
- The agent runtime registers a single **`web-search`** Strands tool from
  `WEB_SEARCH_GATEWAY_TOOL` (default `web-search___WebSearch`), maps
  `maxResults`/`excludeDomains` onto the connector input and calls it through the
  gateway (`MCP_TRANSPORT=gateway`). Source numbering and the chat source
  carousel are unchanged (`results[]` → `_extract_sources`).
- **No fallback:** the connector is only reachable through the gateway. With the
  local `aggregator` transport (AgentCore Gateway is not emulated in Floci) the
  `web-search` tool is simply not offered.

### HTTP fetch tool

- `http-fetch` (`backend/services/mcp/http-fetch/`) is its own MCP server Lambda
  (`POST /mcp/http-fetch`, group `mcp-tools`) owning exactly one tool,
  **`http-fetch`**: call a public `http(s)` URL/API endpoint in **trusted code**
  (never the user sandbox) and **return the response inline** — JSON parsed, text
  decoded, binary base64-encoded — capped at `maxBytes` (2 MB default, 10 MB
  max) and `maxChars` (200 000 default). It has **no storage capability**; bytes
  are never persisted (that is the separate `storage` server). Supports
  GET/POST/PUT/PATCH/DELETE/HEAD with optional headers and body.
- **SSRF guard** (`src/fetcher.py`): only `http`/`https`, no embedded
  credentials; the hostname is resolved and **every** address checked against a
  loopback/private/link-local/reserved/metadata denylist; the connection is
  **pinned to the validated IP** while keeping the `Host` header + TLS SNI (so a
  DNS rebind cannot redirect it); redirects are followed manually and
  re-validated; size/time capped. Optional `HTTP_FETCH_ALLOWED_DOMAINS`
  (comma-separated suffix allowlist) hardens prod. No local emulation branch —
  Floci containers reach the public internet directly.

### Storage MCP server

- `storage` (`backend/services/mcp/storage/`) is its own MCP server Lambda
  (`POST /mcp/storage`, group `mcp-tools`) and owns the caller's standalone
  storage files. Four tools: **`list-storage-files`** (id, name, content type,
  size, status, timestamps), **`read-storage-file`**
  (`{fileId, format? (auto|text|json|base64), maxChars?}` — default 20 000, max
  200 000 chars), **`write-storage-file`** (`{fileName, content, contentType?,
  encoding? (text|base64)}` — creates a new file and returns its metadata + a
  presigned `downloadUrl`), and **`delete-storage-file`** (`{fileId}` — deletes
  the S3 object and its item).
- One DynamoDB item per file (`USER#<userId>` / `STORAGE#<fileId>`) and the
  bytes at `storage/<userId>/<fileId>/<fileName>`; writes obey the same limits
  as uploads (**10 files, 30 MB per file, 100 MB total**). Identity resolves the
  JWT `sub` → internal `userId` for HTTP, and direct invokes carry `userId`, so a
  user can never see another's files. This is how the agent runtime reads/writes
  the user's uploaded/stored S3 files.
- **Agent flow** — each tool does one job: **`http-fetch`** gets a URL's JSON,
  **`code-interpreter`** calculates over it (no internet there), and
  **`storage`** persists the result. The MCP Builder's own tools run with public
  internet in their sandbox (below), so a self-contained tool may call an API
  directly and return the conversion/result itself.

### Custom tools (MCP Builder)

- Users build their own Python MCP tools in the **MCP Builder** (formerly the
  "Playground": `frontend/src/pages/ExperimentsPage.tsx`, route `/mcp-builder`,
  sidebar section `build`) and use them
  in agents. The page is a **chat-to-code workspace**, not a form: a **build
  chat** on the left (one active server + tool, switched from a compact popover
  — there is no multi-server sidebar) and a **CodeMirror 6 code panel** on the
  right. The server name, tool name and description are editable fields across
  the top; **Save tool** is the page's single primary action and **Test** sits
  beside it (always available). The panel has only **Code** and **Schema** tabs;
  **Test** opens a dialog that builds an argument form from the input schema
  (text/number/boolean/enum/JSON fields with a Reset), runs the tool and shows
  the result there. Chatting calls the generator; each reply renders a change
  card (`+N/-M`) that opens a **VS Code-style unified diff**
  (`@codemirror/merge` `unifiedMergeView`) between the accepted code and the
  proposal, reviewed with a **single global Accept / Reject** pair (no per-chunk
  controls). Each change card also has a **Restore checkpoint** action (VS
  Code-style) that reverts the editor to the code captured before that change.
  An **undo/redo** history over accepted code sits in the editor header. The
  composer is disabled while a proposal is awaiting review. Chat history
  persists in a **Playground session** (below); there is **no per-user
  deployment** of the tool itself.
- The tool is served by the **`custom-tools`** MCP-server Lambda
  (`backend/services/mcp/custom-tools/`, `POST /mcp/custom-tools`, group
  `mcp-tools`), which loads each user's tools from DynamoDB on every request and
  namespaces them `<serverSlug>/<toolName>` — the same per-request pattern as the
  remote aggregator.
- **Storage**: one `CSERVER#<slug>` item per server and one
  `CTOOL#<slug>#<name>` item per tool (schemas + description in DynamoDB); the
  `.py` source lives in S3 at `custom/<userId>/<slug>/<name>.py` (not `raw/`, so
  it never triggers ingestion). CRUD lives in **`user-api`** via
  `data/repositories/custom_tools.py`; routes `GET/POST /v1/custom-tools`,
  `POST /v1/custom-tools/generate`, `POST /v1/custom-tools/test`,
  `GET/PUT/DELETE /v1/custom-tools/{id}`,
  `POST /v1/custom-tools/{id}/tools`,
  `GET/PUT/DELETE /v1/custom-tools/{id}/tools/{toolId}`. Limits: **20 servers,
  20 tools/server, 64 KB source/tool**.
- **Playground sessions** (`data/repositories/playground.py`, prefix
  `PGSESSION#`) persist the build chat: one small item
  (`USER#<userId>` / `PGSESSION#<sessionId>`, `byUser` GSI2 for the recent-builds
  list) holds the metadata and the message transcript is one S3 object
  (`playground/<userId>/<sessionId>.json`, read-modify-write once per turn).
  Routes: `GET/POST /v1/custom-tools/sessions`,
  `GET/PATCH/DELETE /v1/custom-tools/sessions/{id}`,
  `POST /v1/custom-tools/sessions/{id}/turn` (starts one generator turn: appends
  the user + a `status: "generating"` placeholder assistant message, then runs
  generation in a **background invocation of user-api itself** so it outlives
  API Gateway's 30s integration cap, and returns immediately; the SPA polls
  `GET .../sessions/{id}` until the placeholder resolves. Each resolved
  assistant message carries its `generated` proposal and the `baseCode` it was
  generated from so the diff can be re-displayed). Limits: **100 sessions/user,
  200 messages/session**; the title is seeded from the first prompt.
- **Contract**: a tool's `.py` defines `run(args)` taking one dict and returning a
  JSON-serializable value; `inputSchema`/`outputSchema` are JSON Schema
  (validated by a dependency-free validator in `src/schema.py`). A harness
  (`src/harness.py`) invokes `run` and prints a line-delimited marker so the
  result is recovered from the sandbox output.
- **Execution** uses the shared `core.sandbox` (AgentCore in prod; guarded local
  subprocess with `CUSTOM_TOOLS_MODE=local` under Floci). In prod it runs on the
  **custom PUBLIC Code Interpreter** (`CUSTOM_TOOLS_IDENTIFIER`), so user tools
  can reach the public internet; the sandbox guard caps outbound connections
  (`CUSTOM_TOOLS_MAX_CONNECTIONS`, 25/run), refuses private/loopback/metadata
  destinations, and blocks heavy ML frameworks (process spawning and dynamic
  code are permitted). The test route direct-invokes `custom-tools` (IAM-trusted,
  no API-Gateway 30s cap); the SPA never executes user code.
- **Guardrails & limits** (surfaced in the generator prompt so the model tells
  the user and offers a compliant alternative): public HTTP(S) only; **≤ 25
  outbound connections per run**; **~90 s per real tool call**
  (`CUSTOM_TOOLS_EXEC_TIMEOUT_SECONDS`) and **180 s while testing**
  (`CUSTOM_TOOLS_TEST_EXEC_TIMEOUT_SECONDS`); a per-user **rate limit of 60
  network-enabled runs/hour** (`CUSTOM_TOOLS_RUNS_PER_HOUR`, enforced through
  `core.ratelimit` — Redis GCRA when configured, the DynamoDB counter
  otherwise); heavy ML frameworks are blocked by the guard
  (process spawning and dynamic code are permitted). The custom-tools Lambda
  timeout is 300 s to fit the test budget.
- **Admin kill switch + usage.** `networkToolsEnabled` on the platform settings
  item (`PLATFORM#SETTINGS` / `#FLAGS`, `data/repositories/platform.py`) is read
  by `core.network.enabled()` and can be flipped at runtime from the admin
  Platform page (`GET/POST /v1/admin/platform/network`). When off, custom tools
  run with `allow_network=False` (pure tools still work) and `http-fetch`
  returns `network_disabled`. Every network-enabled run is counted on the user's
  quota item (`networkRuns` / `lastNetworkRunAt`) and, together with the
  current-hour window (`core.ratelimit.current`) and the limits in force, is
  served at **`GET /v1/user/network`** and shown on the **Usage** page.
- **AI generation**: `POST /v1/custom-tools/generate` (and the turn worker above)
  makes one **Amazon Bedrock (Converse)** call (`CUSTOM_TOOLS_GENERATOR_MODEL`,
  default `zai.glm-4.7-flash`) returning `{name, description, code,
  inputSchema, outputSchema}`; the Playground re-sends the current code and last
  test error to iteratively refine it. The system prompt states the network
  capability and the limits above so the model refuses/gwarns instead of emitting
  code that will fail. The synchronous `/generate` route is
  capped at `CUSTOM_TOOLS_GENERATE_TIMEOUT_SECONDS` (25, under the gateway's
  30s); the turn worker uses `CUSTOM_TOOLS_GENERATE_ASYNC_TIMEOUT_SECONDS` (240,
  under user-api's 300s Lambda timeout). `CUSTOM_TOOLS_GENERATE_MAX_TOKENS`
  (32000) must stay large: the model spends up to ~18k hidden reasoning tokens
  **before** the JSON, and a smaller budget is consumed entirely by reasoning
  (`finish_reason=length`, no tool). `CUSTOM_TOOLS_FUNCTION`,
  `CUSTOM_TOOLS_GENERATOR_MODEL` (a Bedrock model) and these knobs live on **user-api**
  (which owns the routes).
- **Agents**: a custom server attaches as an agent `servers[]` entry with
  `source: "custom"` and `id: <slug>`; `agentflow.tools.build_tools` calls
  `CUSTOM_TOOLS_MCP_FUNCTION` and filters by the selected `<slug>/<tool>` names.
  Custom servers are also offered to skills (`_available_mcp_servers`).

### Agent skills

- `agent-skills` CRUD is part of **`user-api`** — a user's reusable skills in the
  **strands format**: YAML frontmatter (`name`, `description`, `allowed-tools`)
  plus a markdown body. Routes: `GET/POST /v1/agent-skills`,
  `GET /v1/agent-skills/mcp-servers`, `POST /v1/agent-skills/parse`,
  `GET /v1/agent-skills/catalog`, `GET /v1/agent-skills/registry`,
  `POST /v1/agent-skills/resolve-repo`, `POST /v1/agent-skills/import`,
  `POST /v1/agent-skills/import/preview`, `GET/PUT/DELETE /v1/agent-skills/{id}`.
- Frontmatter fields are stored in **separate DynamoDB attributes** (`name`,
  `description`, `allowedTools`, `content`) so an agent can list cheap metadata
  and only fetch the full body when a skill applies. No S3 object. Limits:
  **50 skills/user, 100 KB per skill**; names are lowercase-hyphen (1–64) and
  unique per user (the item key `SKILL#<name>`).
- The parse/render/validation logic lives in the user-api app's `src/skills/`
  (no PyYAML). `POST /parse` is what the editor calls when a user uploads a `.md`.
- **allowed-tools** lists whole **MCP servers**, not individual tools. Built-in
  servers `code-interpreter`, `web-search`, `http-fetch` and `storage` are always
  offered; **`browser` is capability-gated** — user-api advertises it only when a
  browser is provisioned *and* `BROWSER_ALLOWED_DOMAINS` is non-empty, so the
  builders (and skills) never offer a tool that would refuse every call.
  Knowledge-base tools are internal and never shown. The user's connected,
  enabled remote servers are offered by server id (slug). Individual tools are
  enabled/disabled on the MCP page, so skills never reference tool names.
- **Skills marketplace & registry** (`src/skills/`):
  - `catalog.json` is the curated **One Agent Marketplace** seed (owner `1agent`),
    served by `GET /v1/agent-skills/catalog`.
  - `GET /v1/agent-skills/registry` proxies the public **claude-plugins.dev** API
    (`SKILLS_REGISTRY_URL` override, in-container cache). `kind=prompt|tool`
    classifies on demand by fetching each `SKILL.md` body (`classify.py`) and
    keeps only matches.
  - `resolve-repo` resolves `owner/repo` (GitHub, optional `GITHUB_TOKEN`) to the
    `SKILL.md` files it contains — like `npx skills add owner/repo`.
  - `import/preview` fetches + parses a raw `SKILL.md` (no write); `import`
    creates it with `source: "registry"` and the **user-chosen** `allowedTools`.
    Fetching is HTTPS-only with a host allowlist (`fetch.py`). Imported skills
    are third-party instructions — the editor shows a prompt-injection warning.

### Agents (Agent builder)

- `agents` CRUD is part of **`user-api`**. An agent is one item
  (`USER#<userId>` / `AGENT#<lowerName>`) whose `config` map holds the system
  prompt, model, reasoning, **answer mode**, output format, the referenced
  KB/skill/MCP ids, an optional schedule and the node/edge **graph**.
  KBs/skills/servers are stored by id, never embedded. Limits: **50 agents/user**,
  256 KB config; names are lowercase-hyphen (1–64) and unique per user.
- Routes: `GET/POST /v1/agents`, `GET/PUT/DELETE /v1/agents/{id}`,
  `POST /v1/agents/{id}/verify`, `POST /v1/agents/{id}/publish`,
  `POST /v1/agents/{id}/unpublish`, `GET /v1/agents/library`,
  `POST /v1/agents/library/{id}/install`.
- **`verify` = config dry-run.** The `/verify` endpoint checks the prompt/graph
  and that every referenced KB/skill/MCP server exists and is usable, then stamps
  `verifiedAt` (and `status=verified`, or keeps `published`). It makes **no model
  call**. The builder has no separate Verify action; it calls `/verify` after a
  successful save (best-effort) so the stored status reflects the saved config,
  and publishing stays ungated.
- **Publish to library** flips `visibility=public` and
  projects the agent onto GSI3 under `AGENTLIB#public` (`<publishedAt>#<agentId>`)
  so the library lists globally without a Scan. `install` clones a published
  agent into the caller's workspace with `source="library"` + `forkedFrom`, and
  strips owner-scoped references (KBs/skills/remote servers) since those are not
  shareable.
- **Schedules run** — the builder's schedule node writes `config.schedule`
  (`enabled`, `cron`, `timezone`). Saving an agent (or workflow) mirrors an
  enabled schedule into the scheduler registry (`data/repositories/schedules.py`,
  `USER#<userId>` / `SCHEDULE#<kind>#<targetId>`, projected onto the sparse GSI3
  `SCHEDULES#enabled` under `<nextRunAt>#<userId>`). The **`scheduler`** Lambda
  (EventBridge `rate(1 minute)`) queries the due range, creates a conversation,
  runs the target as the platform service (`core.agent_runner`, the same
  service-auth + control-plane path the evaluations worker uses), and stamps
  `lastRunAt` / advances `nextRunAt`. Cron is parsed timezone-aware in
  `core.schedule` (no third-party dep). See the "Scheduling" section.
- **Knowledge rerank** — the knowledge node's dialog has a "Rerank results"
  toggle that writes `config.knowledgeRerank` (and the node's `data.rerank`); the
  runtime passes it as `rerank: true` when it calls the knowledge search tool
  (`agentflow/tools.py`), and `user-api` validates/persists the flag.
- Frontend: `frontend/src/pages/AgentBuilderPage.tsx` is a **React Flow**
  (`@xyflow/react`) canvas with no side panel. The agent sits in the middle with
  **input** on top, **output** on the bottom, **schedule** on the left, and
  **knowledge**, **MCP servers & tools** and **skills** stacked down the right.
  Each is a compact n8n-style node — a colour strip, an icon tile, a title and a
  one-line summary subtitle (no header tag, no inline controls). The **whole
  card is click-to-open**: clicking anywhere on it opens a detail dialog holding
  all options (agent prompt/model/reasoning/**answer mode**, the full KB/skill
  lists, per-MCP tool selection, custom cron and output instructions). The **run
  question is never saved**: the **input card** holds only an optional
  **starter-questions** list (`config.defaultQuestions`, max 8) that the chat
  screen surfaces as one-tap prompts, plus attached files. Cards
  are **permanent and fixed** — equal size, no palette, no delete, and not
  draggable or re-connectable; every link is a static dotted curve that, during
  a run, **flows** (marching dots) on the edges actually carrying data and
  settles to a **solid** line once the step completes. The **input** card stays
  highlighted while the question is handled, the **knowledge / MCP servers /
  skills** cards glow when their tools run, and the **schedule** (a trigger, not
  a data path) never glows or flows. A right-hand
  **Agent** panel with **Response / History / Errors** tabs is the **run log**:
  its **Live** tab starts with a **run composer** where the question is typed per
  run — the Run/Stop action lives there, not in the header — and then shows the
  run timeline (tool steps; the final answer opens in chat). Edits autosave to
  localStorage; Save writes the config to DynamoDB.
  Selecting a skill auto-adds the MCP servers it declares. The library UI is
  `AgentStorePage.tsx`.

### Workflows (multi-agent)

- `workflows` CRUD is part of **`user-api`**. A workflow is one item
  (`USER#<userId>` / `WORKFLOW#<lowerName>`) whose `config` map holds the `mode`
  (`graph` | `swarm`), the input/output settings and the node/edge graph. Agent
  nodes reference saved agents by id (never embed them). Routes:
  `GET/POST /v1/workflows`, `GET/PUT/DELETE /v1/workflows/{id}`,
  `POST /v1/workflows/{id}/verify`, `GET /v1/workflows/{id}/runs`. Limits:
  **50 workflows/user, 10 agents, 100 nodes, 300 edges**, 256 KB config;
  names are lowercase-hyphen (1–64) and unique per user. Workflows are
  **private for now** (no publish/library).
- **The query card is the host agent** (labelled "Query" in the UI, tagged
  Host). It is never one of the saved agents: it owns the workflow's system
  prompt and its own model, and it is the coordinator in
  **both** modes. The run question is **not saved** — it is typed per run in the
  right panel's Run tab. A new workflow starts with just the Query and Output
  cards (left of the canvas); agents are dragged in to the right, and a
  **schedule** node can be attached to the Query's left (registered with the
  scheduler on save, like agents). *Graph* is deterministic: the host
  dispatches (its brief becomes the entry agents' input), agents run along the
  wired agent→agent edges (independent ones in parallel), then a second host pass
  synthesizes their outputs into the final answer (Strands `Graph`). *Swarm* is
  dynamic: the host is the swarm entry point and hands off to teammates with the
  injected `handoff_to_agent` tool (Strands `Swarm`). The runtime wraps both
  frameworks and normalizes their `multiagent_*` events — **no A2A**.
- **Per-node overrides.** An agent node may override `model`, `prompt`,
  `reasoning`, `servers` and `skillIds` for that workflow only (stored in
  `node.data.overrides`, merged over the agent's config at run time); everything
  else (including knowledge bases) is inherited, so edits to the agent propagate.
- **Builder UI** (`frontend/src/pages/WorkflowBuilderPage.tsx`) is React Flow
  with a **left agent palette** (drag an agent onto the canvas, or click to add),
  a **centre canvas** with permanent Input/Output nodes plus draggable,
  connectable agent cards, and a **right panel** with two tabs: **Inspect**
  (click the host card for its prompt/model, or an agent card for its
  model/prompt/knowledge/MCP servers/skills with per-node overrides) and **Run**
  (**a run composer where the question is typed per run** — the Run/Stop action
  lives here, not in the header — above the live `WorkflowRunTimeline`;
  per-node status, tool calls and timing; agent text is **never** rendered, and
  neither is the final answer). Nodes are named by agent,
  not id (only genuinely duplicated names get a ` #n` suffix); in **swarm** mode
  an inbound transition reads "Handoff from X", in **graph** mode it reads
  "From X" (a batch transition, not a handoff). The graph synthesizer host is
  never a step — it is excluded, so there is no second "Host" card and no answer
  trapped in a dropdown. Once the answer is ready a **View final answer** action
  opens the persisted conversation in the chat screen (the runtime creates one
  per builder run), which is where the answer renders. Edits autosave to
  localStorage; Save writes the config. `WorkflowStorePage` lists workflows.
- **Chat runs both modes.** Workflows appear in the chat target picker (grouped
  under "Workflows") and run from the same screen; graph uses the saved edge
  order, swarm uses the Host. Chat/builder conversations carry a `targetType`
  (`agent` | `workflow`) so the sidebar and transcript replay know which runtime
  produced a turn.
- The runtime lives in **`backend/agents/workflow/`** (sibling to `agentflow`):
  `store.py` loads the workflow and resolves node agents, `build.py` builds one
  Strands `Agent` per node and assembles the `Graph`/`Swarm`, `events.py`
  normalizes the multi-agent events, `run.py` streams them and persists the turn
  (reusing `agentflow`'s model/tool/prompt/session/conversation/observability
  helpers — one shared citation counter spans every node). **Only the
  final-answer host streams its text** to the client (so the answer types out in
  chat); an intermediate agent's text is consumed by the host and never streamed
  — its tool calls still stream as live progress. Each **member** agent follows
  its own **answer mode** and is framed as an intermediate step (it must not
  address the end user). `main.py` dispatches on `workflowId`.

### Scheduling (agents + workflows)

- A schedule is `{enabled, cron, timezone, question}` on an agent/workflow
  `config` (the builder's schedule card / node). `question` is **what each run
  asks** — the run question is never persisted, so a schedule carries its own;
  user-api validates it (≤2000 chars) and mirrors it into the registry `payload`
  (`{"query": …}`). Without one the scheduler falls back to
  `"Run the scheduled task for <name>."`. Saving mirrors an enabled schedule into
  the registry `data/repositories/schedules.py`
  (`USER#<userId>` / `SCHEDULE#<kind>#<targetId>`; disabled or empty deletes the
  row) and projects it onto the **sparse GSI3** `SCHEDULES#enabled` with sort key
  `<nextRunAt>#<userId>`. The Schedules page (`/scheduled-jobs`) already lists
  both kinds from `GET /v1/agents` + `/v1/workflows`.
- **`core.schedule`** parses 5-field cron (`*`, lists, ranges, steps) and computes
  the next run **timezone-aware** (DST-safe) via `zoneinfo` — no third-party dep.
- **`backend/services/scheduler`** (its own Lambda, group `scheduler`) runs on
  EventBridge `rate(1 minute)`: it queries due schedules
  (`gsi3sk <= now`, one query, never a Scan), creates a conversation
  (`kind="run"`, so the run is a readable transcript in chat), runs the target as
  the platform service via **`core.agent_runner`** (Auth0 client-credentials +
  direct-invoke of the agent-run control plane → MicroVM → AgentCore, the same
  path the evaluations `agent` task uses), then records `lastRunAt`/`lastStatus`
  and advances `nextRunAt`; it also stamps the entity's `lastRunAt`. One schedule
  failing never blocks the others, and scheduled runs never set `humanInLoop`.
- Env: `AGENT_RUN_FUNCTION`, `AGENT_SERVICE_CLIENT_ID` /
  `AGENT_SERVICE_CLIENT_SECRET`, `AUTH_AUDIENCE`, `AUTH_TOKEN_URL`. Infra:
  `module "scheduler"` + the `get1agent-prod-scheduler` EventBridge rule in
  `infra/terraform/envs/prod/backend.tf`; Floci creates the function (rule off
  unless `ENABLE_LOCAL_SCHEDULER=true`, since AgentCore isn't emulated locally).
- A scheduled run is one synchronous Lambda invocation (15-minute cap); a run
  longer than that keeps going in AgentCore but its Lambda wait is cut short.

### AI Assistant (in-product assistant) — a separate runtime

AI Assistant is the assistant behind the button in the bottom-right of every page. It is a
**separate subsystem**, not part of the agent runtime: its own service, image,
lockfile, data prefixes and admin page. Design:
[`docs/design/ai-assistant-architecture.md`](docs/design/ai-assistant-architecture.md); product plan
[`docs/design/ai-assistant.md`](docs/design/ai-assistant.md); interactive
diagrams at `/architecture?tab=ai-assistant`. **Do not fold AI Assistant into the agent or knowledge
docs** — it has its own space on purpose.

- **Deliberately not Strands.** AI Assistant runs on **LangChain Deep Agents** (LangGraph
  under the hood) so the platform demonstrates a second framework. The isolation
  is the point: `backend/ai-assistant/` is its own image with its own `uv.lock`, and the
  integration surface is only the SSE frame contract, the DynamoDB keys and the
  shared `retrieval` package. LangChain is imported **inside functions**, never at
  module scope, so one shared package serves both the container and a slim Lambda.
- **One Lambda, two API Gateway routes.**
  - **Signed-in** — `POST /v1/ai-assistant/ask` (Auth0 JWT at the gateway). The
    handler reads the gateway's **verified claims** from
    `requestContext.authorizer.jwt.claims`, resolves `sub` → `userId` and runs the
    turn. There is no session token to mint or verify and no second component to
    keep in sync; a `userId` in the body is ignored.
  - **Guest** — `POST /v1/ai-assistant/guest` (NONE auth, throttled 4/2). With no
    claims, the handler hashes the caller's IP (`sha256(salt + ip)`) into a
    rate-limit bucket. Same engine with `is_guest=True`, **nothing persisted** —
    which is what makes the guest path stateless.
  - **The response is buffered.** API Gateway HTTP APIs cannot stream and cap an
    integration at 30 s, so the Lambda assembles the run and returns it as one SSE
    body; the widget parses it frame by frame. The Lambda's timeout matches the
    gateway ceiling exactly, and `AI_ASSISTANT_TURN_BUDGET_SECONDS` (24) turns a
    near-miss into a renderable `run.error` frame rather than a 504 with no frames.
  - The zip **bundles** the agent framework (it is the product) and drops what the
    runtime provides (`boto3`/`botocore`/`s3transfer`/`jmespath`, plus
    `fastapi`/`uvicorn`/`starlette`): ~21 MB zipped / 81 MB unzipped.
    `tests/test_lambda_imports.py` pins that `handler` and the guest modules never
    import the framework at module scope, so a guest turn keeps a short cold start.
- **Identity is never taken from the request.** The only trusted identity is the
  gateway's verified claims; `src/identity.py` derives a guest bucket from a hashed
  IP and nothing else. A `userId` in a request body is ignored on both routes
  (`tests/test_handler_routes.py` pins this).
- **Intent classification is its own component with its own model**
  (`ai-assistant/classifier.py`, default `zai.glm-4.7-flash`): a rules stage that costs
  nothing, then one strict-JSON call. It **fails open** to `platform`, so a
  classifier outage can never block a real user, and an off-topic reply ships
  tappable example questions instead of a dead end.
- **Retrieval reuses the platform's own stack** under a reserved `platform`
  scope: `USER#platform` / `KB#platform-docs` (id `kb_platform_docs_0001`) with
  the `idx-platform` S3 Vectors index. AI Assistant implements RRF fusion over
  `retrieval.s3_vectors` + `retrieval.term_index` and hydrates parents, so the
  exact cache, semantic cache and BM25 behave as they do for a user's KB.
  - **Reranking is on by default** (`AI_ASSISTANT_RERANK=0` disables it), using the
    shared `retrieval.rerank`. After fusion it hydrates up to
    `AI_ASSISTANT_RERANK_CANDIDATES` (24) parents so the reranker has real recall to
    work with, then reorders and renumbers — because RRF scores agreement between
    two legs, not relevance, and the ordering is what the answer and its `[n]`
    citations are built from. `rerank.applied` and the per-passage `rerankScore`
    ride on the diagnostic, so a trace shows whether ranking was actually applied.
    A reranker failure returns the RRF order (availability over precision).
- **The corpus is generated from the repository** and ingested through the normal
  pipeline — `backend/ai-assistant/tools/` reads `frontend/src/content/docs.ts`, the real
  route table (nested routes included), the sidebar registries and the **enforced
  limit constants**, then writes 48 documents to `backend/ai-assistant/knowledge/`. `make
  ai-assistant-knowledge` regenerates; `make ai-assistant-knowledge-verify` fails CI when the
  committed corpus is stale. It also emits `backend/ai-assistant/src/features.json` (the
  deep-link allow-list) and `frontend/src/content/aiAssistantStarters.ts` (the widget's
  example questions), so those three can never drift from their sources.
- **Limits are stated from code, not prose.** The limits document is generated
  from `quotas.py` and the `user-api` constants, and points at `/usage` for
  per-user overrides — `docs.ts` and this file still carry older figures, so AI Assistant
  deliberately does not trust them.
- **Agent shape.** A turn is a plan frame, then a tool-using loop
  (`search_platform_docs`, `find_page`, `escalate_to_support`) with a read-only
  filesystem (`StateBackend` + a read permission), **no subagents**, and a
  `TurnCap` middleware bounding model calls per turn. Greetings and refusals use a
  single direct model call instead of the graph, via `ai-assistant/llm.py` (raw Bedrock
  streaming), which is also what keeps the guest zip small.
- **Frames** (`ai-assistant/frames.py`) are the platform's existing agent-run contract plus
  one new `ai-assistant.intent` frame, so `lib/runState.ts`, `RunTimeline` and `ChatAnswer`
  render an AI Assistant answer with no AI Assistant-specific renderer.
- **Persistence** is AI Assistant-prefixed (`AICHAT#`, `AIFEEDBACK#`, `AITRACE#`,
  `AIEVAL#`) so nothing it writes can surface in the agent chat sidebar, the agent
  trace list or the agent feedback table. Transcripts and trace trees are S3
  objects; only small metadata items are in DynamoDB. Guests are never persisted.
- **Rate limiting is layered**, cheapest first: API Gateway route throttles
  (`/v1/ai-assistant/guest` burst 4/rate 2, `/v1/ai-assistant/ask` 20/10), then the
  shared per-caller limiter (`core.ratelimit` — Redis GCRA when configured, the
  DynamoDB counter otherwise) under policy `ai-assistant` with kinds
  `ai-assistant-burst` (3 min) / `ai-assistant-hour` / `ai-assistant-day`, then the
  in-agent turn cap and the 24 s soft turn budget. All three windows are consumed
  in one atomic step, so a caller stopped by the day cap is not also charged
  against the hour cap. Every model call also passes
  `core.ratelimit_bedrock`. The burst window is the one a real visitor meets, and
  it is deliberately short so a refusal reads "try again in a couple of minutes":
  a guest gets **10 per 3 minutes** (defaults `guestPerBurst`), then 60/hour and
  100/day; signed-in callers are 120/hour and 1000/day with no burst cap by
  default (`userPerBurst` 0 disables a window). These live in
  `ai_assistant_settings` and are editable at `/admin/ai-assistant`.
- **Admin page** `/admin/ai-assistant` (routes `GET|POST /v1/admin/ai-assistant`, plus owner-scoped
  `/feedback`, `/traces`, `/conversations`, `/evaluations` and
  `GET|POST /knowledge` + `POST /knowledge/reingest` in
  `backend/services/admin/admin-console/src/ai_assistant.py`): the kill switch, the four
  model pickers with their measured latency, the limits, feedback, traces and the
  corpus status. Settings live on `PLATFORM#SETTINGS` / `#AI_ASSISTANT`, cached 30 s, so a
  change applies without a redeploy.
  - **Re-ingest** starts the **same ingestion state machine** the S3 → EventBridge →
    SQS dispatcher starts, with the same input shape (`userId`/`knowledgeBaseId`/
    `documentId`/`fileName`/`s3Key`/`contentHash`), so the button and a real
    re-upload run identical code. The console gets `states:StartExecution` via the
    module's `step_functions_arns` and reads the ARN from
    `INGESTION_STATE_MACHINE_ARN`; unset means a clear `503` rather than a crash.
    Execution names carry a fresh token per click, because a STANDARD state machine
    **ignores a repeated name for 90 days** — reusing one would silently no-op.
    `{documentId}` targets a single document; omitting it re-ingests the corpus.
- **Evaluations** are a committed set of 81 cases
  (`backend/ai-assistant/tools/eval/ai-assistant-eval.jsonl`) across six kinds — answerable, find,
  refuse, boundary, unknown, multiturn — each naming the page a correct answer must
  cite, and validated against the real route table at generation time.
- **Metrics** use CloudWatch EMF under `get1agent/ai-assistant` (`ai-assistant/metrics.py`), and cost
  is attributed through `core.usage` so AI Assistant's numbers match billing.
- **Infra**: one `module "ai_assistant"` in
  `infra/terraform/envs/prod/backend.tf` (the Lambda zip, 1024 MB, 30 s timeout
  matched to the gateway ceiling) plus its two routes in `api_gateway.tf`;
  `ai-assistant` registered in `backend/registry.json` under the `ai-assistant`
  group. There is **no Function URL, no session secret, no control plane and no
  MicroVM/ECR module**. Build the zip with `make -C backend/ai-assistant package`.
- **Local**: AI Assistant runs **in the Floci stack** as the `ai-assistant` compose
  service — `make floci`/`floci-up` starts it, `make floci-reload` rebuilds it
  after code changes, `make ai-assistant-logs` follows it, `make floci-down` stops
  it — serving `backend/ai-assistant/main.py` on `:8091`. That is a small ASGI
  server that **calls the same `handler.lambda_handler`** production runs, by
  synthesising the API Gateway payload-format-2.0 event the handler already
  expects. It is the local stand-in for API Gateway, so it also owns the
  authorizer: it verifies the browser's Auth0 token itself (`src/local_auth.py`,
  stdlib-only RS256 + JWKS) and rejects an unverifiable one with a `401` — the
  check moves, it is never removed, and a `userId` in the body is still ignored.
  Guests need no setup. It is containerised (`Dockerfile.dev`, Linux, from the
  committed `uv.lock`) because the Lambda zip is built from the host's wheels and
  a Mac's are macOS binaries that a Linux Lambda container cannot import; its port
  is published on loopback only. `fastapi`/`uvicorn` are a **dev dependency
  group**, excluded from the Lambda zip by the Makefile's `RUNTIME_EXCLUDE`.
  `frontend/.env.local` sets `VITE_AI_ASSISTANT_URL=http://localhost:8091` and the
  server allows the `:5173` origin, so the widget can talk to it directly. Locally
  `RERANK_MODE=none` (the account throttles the cross-region Bedrock reranker,
  which cost 6–26s of retries per turn for the RRF order it fell back to anyway);
  `make floci-rerank` + `RERANK_MODE=local` runs the real cross-encoder instead.
  `main.py` also **pre-warms the agent framework in a background thread** at
  start-up and the service raises the turn budget to 120s: a cold first turn
  imports ~6s of framework, which against the deployed 24s budget (sized for API
  Gateway's 30s cap) answered *and* appended a `run.error` — the first thing a
  developer saw.
- **Tests are in CI.** `make test-ai-assistant` is a **named job** in
  `backend-tests.yml`, not part of `make test-unit` (that loop only walks
  `backend/services/*`, which is exactly how this suite went un-run).

### Agent runtime (AgentCore + Strands)

- The runtime lives in **`backend/agents/`** — an **AgentCore Runtime container**
  (ARM64, port 8080, `POST /invocations` SSE + `GET /ping`) built on
  `BedrockAgentCoreApp`; the single-agent path is the **`agentflow/`** package and
  the multi-agent path is the **`workflow/`** package (`main.py` dispatches on the
  payload: `workflowId` → workflow, else agent). It is **not** a Lambda zip;
  `agents/` is excluded from the Lambda build.
- Invocation: a **Lambda Function is capped at 15 minutes**, so the streaming
  proxy runs in a **Lambda MicroVM** (`backend/services/agent-run/microvm/`,
  Node HTTP server, up to 8 hours, dedicated HTTPS endpoint). The browser cannot
  mint the MicroVM ingress `X-aws-proxy-auth` token, so a thin **control-plane
  Lambda** (`backend/services/agent-run/index.mjs`) is invoked through **API
  Gateway** (`POST /v1/agent-run/session`, Auth0 JWT enforced **at the gateway**)
  and only launches a MicroVM from the agent-run image + mints its auth token
  (`lambda-microvms:RunMicrovm` / `CreateMicrovmAuthToken`), returning
  `{endpoint, token}`; the SPA then `POST`s to the MicroVM's `/invocations` and
  reads the SSE stream. The MicroVM verifies the Auth0 token too, then forwards
  the `Authorization` header and body to AgentCore and pipes SSE back. The runtime is configured with a
  **custom JWT authorizer** (Auth0 discovery URL + audience), so AgentCore
  validates the token; the entrypoint only decodes the verified `sub` → internal
  `userId` (`SUB#<sub>`), then loads `USER#<userId>` / `AGENT#<name>` and checks
  ownership. The AgentCore session is hard-capped by `max_lifetime` (25 min);
  the MicroVM aborts the run at the same limit. Local dev streams directly from
  the local agent app (`VITE_AGENT_RUN_MICROVM=false`).
- Models: **Amazon Bedrock** by default — the runtime builds a Strands
  `BedrockModel` (`agentflow/models.py`, SigV4, region `BEDROCK_REGION`) — or a
  user's **Vault provider** when the agent sets `config.providerSecretId` (the
  runtime decrypts it and calls the user's base URL/key via Strands `OpenAIModel`
  — see the Vault section). The builder dropdown offers the curated models kept in
  sync across `agentflow/models.py` (`SUPPORTED_MODELS`),
  `user-api/handler.py` (`SUPPORTED_AGENT_MODELS`) and `frontend/src/lib/agents.ts`
  (`AGENT_MODELS`): `zai.glm-4.7-flash`, `nvidia.nemotron-nano-3-30b`,
  `deepseek.v3.2`, `qwen.qwen3-next-80b-a3b`, and
  `global.amazon.nova-2-lite-v1:0` (1M-context, multimodal). Every model call is
  admitted through `core.ratelimit_bedrock` (global per-model token bucket).
- **Automatic model routing (`auto`).** Any agent, workflow host, or workflow
  node may set its model to **`auto`** instead of a concrete id. The runtime then
  chooses the model for the run **before executing the question** and uses that
  model for the whole run (`agentflow/routing.py`, `workflow/run.py`). The choice
  uses the Strands SDK's model-routing primitives
  (`strands.models.ClassifierStrategy`): a small/fast Bedrock model
  (`AGENT_ROUTER_MODEL`, default `zai.glm-4.7-flash`) reads the latest request
  plus a **capability profile** for every platform model (cost/latency/context/
  strengths in `routing.MODEL_PROFILES`) and selects the least capable candidate
  that can still deliver a complete answer — routine requests stay on the cheap
  models, coding/reasoning escalates to `deepseek.v3.2`, very long/multimodal
  requests go to `global.amazon.nova-2-lite-v1:0`. The decision is resolved up
  front (not by handing a live `ModelRouter` to the agent) so the chosen id is
  streamed (`run.started.auto.selected`), the right context window drives the
  meter/summarizer, and the correct price is charged. A workflow makes **one**
  decision per run, applied to the host and every `auto` member. Routing is
  best-effort and **fails open** to `DEFAULT_MODEL`, and it never applies to a
  Vault-provider run (provider models are free-form). Knobs:
  `AGENT_MODEL_ROUTING` (default on), `AGENT_ROUTER_MODEL`,
  `AGENT_ROUTER_TIMEOUT_SECONDS` (20) and `AGENT_ROUTER_POLICY`. `auto` is
  accepted by `user-api` only on the platform branch (`PLATFORM_AGENT_MODELS`)
  and rejected alongside `providerSecretId`. The model pickers (agent builder,
  workflow host + node override, chat composer) offer **Auto**, and the runtime
  streams the model it chose (`run.started.auto.selected`) so the resolved model
  is shown on the persisted turn. No extra infrastructure: the classifier is a
  normal Bedrock call.
- The runtime reads the **canonical `config`** (flat `prompt/model/reasoning/
  answerMode/input/output/knowledgeBaseIds/knowledgeRerank/skillIds/servers/memory`
  + `graph` for the UI)
  and builds tools from the MCP servers (built-ins via `core.mcp_client`, remote
  via the aggregator, the user's Playground tools via `CUSTOM_TOOLS_MCP_FUNCTION`),
  the knowledge server's **real tools under their exact
  names** (`get-user-knowledge-bases` + `search-user-knowledge-bases`, scoped to
  the agent's attached KBs), and
  attaches the agent's skills through Strands' **`AgentSkills`** vended plugin
  (`agentflow/skills.py`) — **progressive disclosure**: only each skill's name +
  description is injected into the system prompt, and the agent decides whether
  to call the `skills` tool to load a skill's full instructions when it applies.
  Activated-skill state rides on the agent state/session. `_make_tool` preserves
  hyphens in tool names (only characters the model API rejects are sanitized).
  A `skills` frame (available skills) is streamed so the run card can show them.
- **Answer mode** is a per-agent setting (`summarize | normal | detailed`,
  default **`summarize`**, chosen in the builder next to model/reasoning) and can
  be overridden per run from the chat composer. `build_system_prompt` appends a
  matching instruction: Summarize = shortest complete answer, Normal = key points
  with brief context, Detailed = section-wise detail. Legacy `medium`/`deep`
  values map to `normal`/`detailed`. **Reasoning effort** (default **`low`**) is
  a per-run/per-agent **prompt-level hint** (the gateway exposes no
  reasoning-token budget). Workflow members follow their own agent's mode; in
  chat, the workflow target's answer-mode/reasoning pickers apply to the
  **host** (coordinator + final answerer), never to the members.
- **Human-in-the-loop (chat only).** The chat composer has an **Auto-approve**
  toggle (default **off**). When off, the run payload sets `humanInLoop: true`
  and the runtime adds an **`ask_user`** tool (`agentflow/hitl.py`); when the agent
  calls it the tool raises a Strands **interrupt**, which pauses the run and
  streams a `question` frame (`questionId/question/options/allowCustom`) instead
  of `run.completed`. The chat renders a Copilot-style card (option buttons +
  custom input) and, on submit, resumes the **same** run by invoking again with
  `interruptResponses` (+ `pendingQuestion`, replayed into the transcript) — the
  Strands session preserves the interrupt state, so the paused tool replays with
  the answer and the agent continues. When Auto-approve is **on** the payload
  sets `humanInLoop: false`: no tool, and `build_system_prompt` tells the agent to
  assume the best option and state it. The `ask_user` call is never shown as a
  tool row. A paused run **is** persisted with `status: awaiting_input` (so the
  question survives a reload) and the resume sends `resumeRunId` so its completed
  turn **replaces** that turn (`append_turn(replace_run_id=...)`) — no duplicate.
  Multi-agent workflows get the same tool on the **host** (swarm entry /
  graph synthesizer); `workflow/events.py` maps `multiagent_node_interrupt` to the
  same `question` frame. The builder, workflow builder and automation never set
  `humanInLoop`, so their flows stay continuous.
- **Attachments.** The agent's input card attaches Storage files by id
  (`config.input.fileIds`). Files are **never** saved as content on the agent and
  never sent to the model directly: at invocation the runtime looks each id up in
  DynamoDB, downloads the object from S3, extracts its text
  (`ingestion.extractors`) and folds that text into the execution input. Bytes
  never leave the runtime. The `attachments` frame tells the client which files
  were used. The agent container installs `pymupdf`/`python-docx`/`openpyxl`
  (the same set bundled into the `ingestion-extract` app). A run payload may override
  `knowledgeBaseIds`/`skillIds`/`servers`/`fileIds` per run; an empty list means
  "none selected".
- **Sessions** persist in S3 (`S3SessionManager`, prefix
  `agent-sessions/<userId>/<agentId>/`). **User memory** is a single
  **user-scoped** Strands `MemoryManager` shared by every agent and workflow of
  the user (see "AgentCore Memory + Policy"): the same store is attached to the
  single-agent run and to every workflow member/host, so a fact told in one
  place is recalled everywhere. Memory is on by default and toggled on the
  **Memory** page (workspace setting `memoryEnabled`). The runtime appends a
  `forget_memory` tool so the user can erase a memory by asking the agent, and
  flushes the manager after each run so extraction writes persist. It also adds an
  `add_memory` tool, because the managed store has no `add`: a "remember this"
  would otherwise wait on **asynchronous** extraction and could not be confirmed
  inside the conversation. `core/memory.py:save_record` **skips a restatement** of
  a stored memory (an exact match after normalisation, or a semantic hit at or
  above `DUPLICATE_SCORE`) — the tool write and extraction can both derive the
  same fact, and `clientToken` only deduplicates a byte-identical replay, so
  without this one fact accumulates copies and crowds the injection window.
  Measured live: identical ≈1.0, a close paraphrase ≈0.76, a same-shaped *different*
  fact ≈0.56, unrelated ≈0.35, so the default stays high (near-identical only) and
  `MEMORY_DUPLICATE_SCORE` tunes it without a deploy.
- **Context management.** Every run restores the conversation's message history
  from the session and passes the **full text history** (user/assistant turns,
  capped to the last `AGENT_PLANNER_HISTORY_TURNS` = 6 turns) to the planner so
  follow-ups resolve references. Tool results are the dominant context cost, so
  the model is wrapped (`agentflow/context.py`) with a per-call view that caps
  **every** tool result, not just old ones: each **old** result is truncated to
  `AGENT_TOOL_RESULT_MAX_CHARS` (1500) and the last
  `AGENT_TOOL_RESULT_KEEP_FULL` (2) results are capped at the larger
  `AGENT_TOOL_RESULT_RECENT_CHARS` (6000) — knowledge results are exempt, and the
  session/transcript keep the full data. Capping the recent results is what stops
  one huge payload (a full-text web search, an `http-fetch` page) from flooding
  the context in a single turn. The agent uses Strands `SummarizingConversationManager` with proactive
  compression (`AGENT_CONTEXT_COMPRESSION_THRESHOLD`, default 0.9) so the run
  that crosses the limit **still completes** instead of erroring — no
  mid-message "context limit" error. Each model carries a `context_window_limit`
  (`agentflow/models.py`, override `AGENT_CONTEXT_WINDOW` /
  `AGENT_CONTEXT_WINDOW_<MODEL>`); the runtime streams a `context` frame
  (`usedTokens/limitTokens/ratio/full` plus a `breakdown` of system-prompt /
  tools / history tokens) at the start and after the turn. Once the fill reaches
  `AGENT_CONTEXT_FULL_RATIO` (default 0.9), `full: true` is set and the composer
  shows a **ring context meter** (hover for the token breakdown) and tells the
  user to start a new conversation, then stops accepting messages.
- **Planning step.** Before executing, the runtime makes one short, tool-free
  call (`agentflow/planner.py`, fixed model `AGENT_PLANNER_MODEL`, default
  `deepseek-v4-flash-vision-exp`) that returns a JSON plan — a one-line understanding plus
  **sub-queries**, each owning an ordered **todo list**. Sub-queries are kept
  minimal (1 simple, 2-4 multi-dimensional) and only when they invoke a tool;
  todos are few (1-3) and a single todo may own **several tool calls** (its `tool`
  hint is a comma-separated list). Every todo must name a tool — `_clean_plan`
  drops tool-less todos and any sub-query left without one, so the UI never shows
  reasoning as a step. Skills are guidance, **not tools** — the planner is told
  never to name a skill in `tool`, and `_clean_plan` strips any skill name that
  slips through, so a skill-only step never becomes a phantom, never-run todo.
  The plan is streamed (`plan.started` then
  `plan`) and folded into the agent's input so the run follows it
  (`execution_input`). A planner failure is non-fatal.
  Disable with `AGENT_PLANNER_ENABLED=false`.
- Streaming events are normalized in `agentflow/events.py` to
  `run.started|skills|plan.started|plan|text|tool.start|tool.input|
  tool.stream|tool.result|run.completed|run.error`. The `skills` frame lists the
  skills folded into the system prompt (`[{id, name}]`) so the run card can show
  a "Skills" strip — skills themselves are never tool calls. Internal reasoning/thinking
  (`reasoningText`) is **dropped** — it is never emitted to the client, and the
  system prompt tells the agent to return only the final answer. A `tool.result`
  also carries `sources` — citation links extracted from the tool payload
  (knowledge `sources[]` documents/pages, web-search `results[]`). Each tool
  result's sources are tagged with a **run-global `index`** (`tools.py`
  `_number_sources`), the system prompt tells the model to cite them inline as
  `[n]`, and the UI shows the same number in the sources panel (clicking a
  citation scrolls to its source). A `tool.result` also carries `cache` when the
  payload reports it (`knowledge-mcp` stamps `meta.cache`): `{hit, kind, backend,
  similarity?}`, which the run timeline renders as a cache badge on the tool row
  (see "Caching (embeddings + knowledge search)"). The model builds
  a tool's input incrementally, so the runtime emits `tool.start` once per
  `toolUseId` and then `tool.input` snapshots as the arguments stream. The SPA
  consumes them with `frontend/src/lib/agentRun.ts`; the shared reducer
  `frontend/src/lib/runState.ts` turns the stream into plan/todo/tool/answer state
  used by both the chat screen and the builder. Set `VITE_AGENT_RUN_URL` to the
  Function URL (prod) or `/agent-run` (local, proxied by Vite to `:8090`).
- **Chat screen** (`frontend/src/pages/ChatPage.tsx`) is the end-user surface:
  it lists the user's agents and the curated models in the composer, streams the
  selected agent's run inline (no side panel) with `components/chat/` — a unified
  `RunTimeline` (collapsible run card → sub-query groups → numbered todo steps,
  where each step owns its tool invocations) and the answer rendered per the
  agent's output format (markdown via `react-markdown`, pretty JSON, or plain
  text). The run card header reads **Planning** while the planner works (there is
  no separate planning row) and the card auto-collapses once the answer starts
  arriving. Only steps that actually invoked a tool are shown (planned-but-unused
  steps stay hidden); tool calls are mapped to their plan step **in order** so two
  consecutive steps that use the same tool stay separate. A sub-query is rendered
  only when it has such steps, as a tinted labelled group that collapses once
  settled, deliberately distinct from the numbered todo rows. Each tool call shows its
  **exact tool name**, full pretty-printed arguments and full response, plus any
  citation sources, and collapses automatically once it completes (a manual
  toggle wins). After the answer finishes, a `SourceCarousel` below it lists every
  source by its run-global number: a knowledge document renders a live preview of
  the cited PDF page (using the document's presigned `downloadUrl`, resolved via
  `fetchKnowledgeBase`) and opens a full-page viewer on click; a web result
  previews its image/favicon and opens the page. The answer's inline `[n]` markers
  are small **round numbered badges** that scroll the matching card into view (in
  every output format). Sources are shown **only** in that carousel. Text streamed
  before a tool call is
  treated as narration and dropped, so only the final answer shows. The agent
  and model pickers are clickable popovers (not dropdowns, and they open upward);
  a workflow target shows only the target picker (no per-agent-model chip), and
  the composer shows no "Streaming…" status text. Every target has **Answer
  mode** and **Reasoning effort** pickers: for an agent they override its saved
  values for that run; for a workflow they apply to the **host**. Every target
  also has a **Run settings** dialog (`ChatRunConfigDialog`): for an agent it
  picks the knowledge bases, skills, MCP servers and storage files for that run
  (seeded from the agent's saved config); for a workflow it picks which of the
  user's **agents** run this time (seeded from the workflow's `agentIds`). The
  selection is sent as `agentIds` and applied by `resolve_agent_nodes` — existing
  nodes keep their ids/overrides/edges and any added agent runs as an extra
  parallel step; the saved workflow is never modified. Nothing is persisted.
  The composer
  sits at
  the bottom of the chat column (not full-page width) on the canvas background
  (no white footer). Starter questions from
  the selected agent's `config.defaultQuestions` render as one-tap prompts. The
  runtime accepts a per-run `model` override in the payload; the agent's saved
  model is the fallback.
- **Builder right panel** (`frontend/src/components/agent-builder/AgentEventsPanel.tsx`)
  renders the **same** `RunTimeline` + answer from the shared run state
  in its **Run** tab, so the builder shows identical todo/tool structure. Its
  **History** tab lists the agent's persisted conversations/runs (from
  `GET /v1/agents/{id}/runs`) — each links to the chat screen to reopen and
  continue it — above the milestone log; Errors keeps the warnings/errors.
  (Sources are chat-only for now; the builder's final-answer presentation is a
  separate, later concern.)
- **Conversations** (chat + builder runs). Every run belongs to a conversation
  with a **global sequential id** minted by one atomic counter
  (`COUNTER#conversations` / `#SEQ`, `data/repositories/conversations.py`), so
  the URL is a readable number: `/chat/conversation/<id>?agent=<name>`. A new
  chat is `/chat?agent=<name>` until the first message, which creates the
  conversation and rewrites the URL. The transcript (every turn's full run
  events) is one S3 object per conversation (`conversations/<userId>/<id>.json`,
  read-modify-write once per run) written by the runtime
  (`agentflow/conversations.py`); the small metadata item (title, counts,
  recency, preview) is in DynamoDB and powers the closable sidebar
  (`GET /v1/conversations`) and the builder History without touching S3. The
  runtime keeps a **stable Strands `S3SessionManager` session per conversation**,
  so a conversation resumes indefinitely (no TTL). Builder test runs always
  **create a fresh conversation** (no continuation), but that conversation can
  later be reopened and continued from the chat screen. Routes: `POST/GET
  /v1/conversations`, `GET/PATCH/DELETE /v1/conversations/{id}`,
  `GET /v1/agents/{id}/runs`, plus the public `GET /v1/traces/{token}` (signed,
  expiring trace link) and `PUT /v1/feedback/{runId}` (run rating). A run only
  persists its turn when the conversation item exists (a stale/unknown id must
  not write an orphan transcript, which a later conversation could inherit), and
  creating a conversation clears any stale transcript object for its fresh id.
  Chat conversations use the `CHAT#` prefix (the code-interpreter already owns
  `CONV#`).
- Infra: `infra/terraform/modules/agent_runtime` (ECR, runtime role, AgentCore
  runtime, control-plane Lambda + Function URL + CORS, Lambda MicroVM image +
  MicroVM + build role). Deploy with
  `bash infra/aws/deploy-agent-runtime.sh`: it creates the ECR repo, builds and
  pushes the ARM64 image, then applies the runtime with
  `agent_worker_image_uri`; the runtime/proxy are gated off until an image URI is
  supplied. The runtime reaches Amazon Bedrock with its task role (SigV4) — no
  model API key is required.
- **Tracing: OpenTelemetry → CloudWatch + X-Ray (AWS-native).** The runtime's
  spans are plain **OpenTelemetry** (`agentflow/observability.py`): Strands'
  auto-instrumentation (agent loop, generations, tool calls) and one root span per
  run (`run_trace` in `run.py`) enriched with `user_id` (internal userId),
  `session_id` (conversationId), tags (agent/model) and metadata. Export is owned
  by the **AgentCore Runtime's ADOT collector** → CloudWatch (GenAI
  observability) and X-Ray, so there is no observability vendor and no
  credentials to configure (`AGENT_TRACING_ENABLED`, `OTEL_SERVICE_NAME`).
  Every Lambda, Step Functions state machine and the API also run with X-Ray
  `Active`, and CloudWatch **Transaction Search** ingests the runtime's spans
  into the `aws/spans` log group.
- **Trace links.** Each run stores its OpenTelemetry `traceId` on the persisted
  turn (S3 transcript) and the conversation item (`lastTraceId`). `user-api` never
  hands out a raw id: it signs it into a **30-minute expiring link**
  (`TRACE_LINK_SECRET`, HMAC-SHA256) returned as a relative `traceUrl` on turns
  (`GET /v1/conversations/{id}`) and runs (`GET /v1/agents/{id}/runs` →
  `lastTraceUrl`). The **unauthenticated** `GET /v1/traces/{token}` route verifies
  the signature + expiry and 302-redirects to the CloudWatch/X-Ray trace view
  (410 once expired). The chat shows a "View trace" link under each answer and the
  builder History shows one per run.
- **Run feedback.** Every run can be rated (thumbs up/down) with an optional
  details dialog (predefined reasons per sentiment + free text). One small item
  per run (`USER#<userId>` / `FEEDBACK#<runId>`; `data/repositories/feedback.py`),
  addressed by the run id so it works identically in the chat and the builder
  History. `PUT /v1/feedback/{runId}` upserts (an empty `value` clears it), and
  the API emits it as a **CloudWatch EMF metric** (`get1agent/feedback`
  namespace) alongside the DynamoDB item. Feedback is returned with conversation turns
  (`GET /v1/conversations/{id}`) and with builder runs (`GET
  /v1/agents/{id}/runs`); the chat shows thumbs under each answer and the builder
  History shows them beside each run.

### File storage

- **`storage`** (part of `user-api`) is a user's standalone file area, **separate
  from knowledge bases** — files to attach to agents/skills later. Routes:
  `GET /v1/storage/files`, `POST /v1/storage/presign`,
  `POST /v1/storage/files/{fileId}/complete`, `DELETE /v1/storage/files/{fileId}`.
- One DynamoDB item per file (`USER#<userId>` / `STORAGE#<fileId>`, small
  metadata only) and the bytes in S3 at `storage/<userId>/<fileId>/<fileName>`
  (`retrieval.layout.storage_key`). The `storage/` prefix is deliberately **not**
  `raw/`, so the ingestion EventBridge rule never fires.
- Upload is **presigned PUT** (browser → S3 directly); `complete` `head`s the
  object to verify size/ETag before writing the item. Any file type is allowed.
- Limits (separate counters, computed from the file list — max 10): **10 files,
  30 MB per file, 100 MB total**. Repository: `data/repositories/storage.py`.

### Support & security reporting

- **Support is a two-way conversation** between a signed-in user and the admins.
  A ticket's metadata is one item (`USER#<userId>` / `SUPPORT#<ticketId>`,
  projected onto GSI3 under `SUPPORT#all` for the admin inbox); each message is a
  separate item in its own partition (`SUPPORT#<ticketId>` /
  `MSG#<createdAt>#<seq>`) so a long thread never grows a single item. Text only;
  subject ≤160, body ≤8000 chars. Repository:
  `data/repositories/support.py`.
- **Security reports are one-way** — the user describes an issue and the admins
  read it (no replies). One item per report (`USER#<userId>` /
  `SREPORT#<reportId>`, GSI3 `SREPORT#all`). The form captures an optional URL,
  the page/area (a picker), and the description.
- **User routes** (in `user-api`, JWT + user view): `GET/POST
  /v1/support/messages`, `GET /v1/support/messages/{id}`,
  `POST /v1/support/messages/{id}/reply`, `GET/POST /v1/security/reports`. Both
  require a signed-in user; the demo is read-only.
- **Admin routes** (in `admin-console`, admin view): `GET /v1/admin/support`,
  `GET /v1/admin/support/{userId}/{ticketId}`,
  `POST /v1/admin/support/{userId}/{ticketId}/reply`,
  `POST /v1/admin/support/{userId}/{ticketId}/status`,
  `GET /v1/admin/security-reports`,
  `GET /v1/admin/security-reports/{userId}/{reportId}`,
  `POST /v1/admin/security-reports/{userId}/{reportId}/status`. The admin inbox
  lists via one GSI3 Query (never a Scan). Admin console pages: `/admin/support`
  (Support) and `/admin/security-reports` (Security).
- **Frontend:** the user Support page (`/support`) sends messages and follows
  replies; the Security page (`/security`) holds the policy plus the one-way
  report form. Both are footer/`AdaptiveLayout` pages (app shell when signed in,
  minimal shell when signed out). Admins in the admin view are redirected from
  `/support` → `/admin/support` and `/security` → `/admin/security-reports`.

### Privacy & data rights (DPDP)

- get1agent implements the **Digital Personal Data Protection Act, 2023** (India) as a data
  fiduciary for account data and a data **processor** for user-uploaded content. The
  user-facing surface is **Privacy & data rights** (`frontend/src/pages/DataRightsPage.tsx`, route
  `/privacy/rights`); the notice is `PrivacyPage.tsx`, the processor list is `SubProcessorsPage.tsx`
  (`/sub-processors`), and a first-login **ConsentGate**
  (`frontend/src/components/privacy/ConsentGate.tsx`, mounted in `MainLayout`) records consent.
- **Consent** is one item (`USER#<userId>` / `#CONSENT`; `data/repositories/consent.py`) holding the
  notice `consentVersion`, the accepted `purposes`, `adultConfirmed`, `language`, `acceptedAt` and
  `withdrawnAt`. Purposes are declared once in `consent.PURPOSES` (`required` = intrinsic to the
  service). Consent is withdrawable as easily as it is given. Bump `CONSENT_VERSION` when the
  notice changes materially.
- **Routes** (in `user-api`, under `_route_user`, JWT + user view):
  `GET/POST/DELETE /v1/user/consent`, `GET /v1/user/export` (right of access — a machine-readable
  bundle with presigned download links; encrypted/token fields are stripped by `_public_item`),
  `DELETE /v1/user/account` (right to erasure), and
  `GET/POST /v1/user/grievances` (data-rights requests, stored as support tickets with
  `kind="grievance"`).
- **Erasure** (`_handle_user_account_delete`) deletes every `USER#<userId>` item plus the
  `EVALRUN#<runId>` and `SUPPORT#<ticketId>` child partitions (`users.delete_user_data`), every S3
  prefix for the user (`raw/`, `derived/`, `index/`, `storage/`, `conversations/`, `custom/`,
  `playground/`, `evals/`, `mcp/`, `agent-sessions/`), the vector index
  (`vector_store().delete_user`), the `SUB#<sub>` identity binding, and — best-effort, when
  `AUTH_MGMT_*` is configured — the Auth0 identity. S3/Auth0 failures are logged and reported, never
  block the DB erasure.
- **Age (18+)**: the first-login ConsentGate asks if the user is 18+; choosing "under 18" hard-blocks
  the app (non-dismissible, offers sign-out or account erasure) and `POST /v1/user/consent` rejects
  anything without `adultConfirmed`. get1agent does not serve children. Grievance contact is
  published (`PRIVACY_OFFICER_*`, `PRIVACY_RESPONSE_DAYS` env).
- Engineering reference and operational runbooks: `docs/compliance/` (`DPDP.md`, `retention.md`,
  `breach-response.md`, `data-requests.md`).

### Notifications

- **A real, per-user feed** — one small item per notification
  (`USER#<userId>` / `NOTIF#<id>`, TTL 90 days) with `kind`, `title`, `detail`,
  an optional in-app `link`, `read`, `createdAt`. Repository:
  `data/repositories/notifications.py` (`create_notification`,
  `list_notifications`, `unread_count`, `mark_read`, `mark_all_read`,
  `delete_notification`); the feed is read with one base-table Query on
  `USER#<userId>` + the `NOTIF#` prefix (never a Scan) and sorted newest-first.
  Distinct from the `#NOTIF` notification-*preferences* item.
- **Emitted from real events** (best-effort — never breaks the source path):
  ingestion emits on a document reaching `ready`/`failed`
  (`ingestion/pipeline.py:set_document_status`), and the scheduler emits on a
  scheduled run finishing/failing (`scheduler/handler.py:_run_schedule`).
- **Routes** (in `user-api`, JWT + user view): `GET /v1/notifications`,
  `POST /v1/notifications/{id}/read`, `POST /v1/notifications/read-all`,
  `DELETE /v1/notifications/{id}`.
- **Frontend:** the TopBar bell (`components/layout/NotificationsMenu.tsx`)
  shows a count badge, lists the feed, and **clicking a notification marks it
  read** (and follows its `link`); there is a "Mark all read" action and a
  per-item dismiss. The menu is hidden in the admin view (the routes are
  user-view only). Client is `lib/notifications.ts` (query key `notifications`).
- **Demo:** the read-only demo has canned notifications
  (`lib/demo/notifications.ts`) and emulates mark-read / mark-all / dismiss
  entirely client-side (in-memory), since the demo client rejects writes.

### Vault (encrypted user secrets)

- The **Vault** (`frontend/src/pages/VaultPage.tsx`, route `/vault`, nav-bar
  icon) stores **AI provider API keys only** — OpenAI-compatible provider keys
  (OpenAI/OpenRouter/Gemini/Groq/DeepSeek/Mistral/Together/xAI/
  Fireworks/Perplexity/Ollama/`custom`). There is **no generic secret type**:
  `POST/PUT /v1/vault/secrets` reject anything but `kind: "provider"`, and a
  provider secret requires a base URL. CRUD lives in **`user-api`**; backend test client is
  `src/vault/tester.py`, presets are `src/vault/providers.py`. A **provider
  secret offers a model list** (`models[]`, max 20; `defaultModel` is the
  selected default and is always added to the list), so one provider/API key is
  not limited to a single model — the builder picker and the chat composer offer
  every listed model. The dialog can **fetch the provider's models live**
  (`POST /v1/vault/models`, server-side so the key stays private) and add them
  with a multi-select. There is **no separate display label** — the reference
  `name` is the label.
- **Operator-blind at the API surface (locked decision).** One DynamoDB item per
  secret (`USER#<userId>` / `VAULT#<name>`, plus GSI1 `byId` for UUID lookups;
  `name` is the lowercase-hyphen reference slug). The secret material is a small
  JSON `{"fields": {...}}` document **KMS-encrypted** (`core.crypto`,
  `VAULT_KMS_KEY_ARN`, context `vault_context(userId, secretId, field)` — distinct
  context keys from MCP's `connection_context`, so ciphertexts are never
  cross-usable). The API **never returns plaintext or ciphertext**: list/detail
  responses carry only metadata + a masked preview (`••••…last4`, no prefix), and
  `payloadEnc` is never serialised. `POST /v1/vault/secrets/{id}/reveal` is the
  only route that decrypts, and only for the authenticated owner.
- Routes: `GET /v1/vault/providers`, `GET/POST /v1/vault/secrets`,
  `GET/PUT/DELETE /v1/vault/secrets/{id}`, `POST /v1/vault/secrets/{id}/reveal`,
  `POST /v1/vault/secrets/{id}/test` (test a saved secret),
  `POST /v1/vault/test` (test an unsaved key from the create dialog). Limits:
  **100 secrets/user**; the whole encrypted payload is capped at 4000 chars
  (KMS direct-encrypt is 4096 bytes), so keep the value small.
- **References.** Any stored value may contain `{{vault:name}}` (or
  `{{vault:name.field}}`); `data/repositories/vault.py:resolve_references(userId, text)`
  decrypts and substitutes them server-side, recording a best-effort usage
  counter (`usageCount`/`lastUsedAt`, surfaced as the page's live usage stats).
  Wired into the **MCP aggregator**: an `apikey` connection may store
  `{{vault:name}}` instead of a literal token, resolved at call time in
  `mcp-connections/src/service.py:_token_for` so rotating the Vault value is
  picked up live (that Lambda carries `VAULT_KMS_KEY_ARN` too).
- **As an agent model (provider-as-model).** An agent may set
  `config.providerSecretId` to one of the user's Vault provider secrets. The
  AgentCore runtime (`agents/agentflow/provider.py`) decrypts it in-process and
  builds an OpenAI-compatible client against the user's base URL + key
  (`models.build_model(..., provider=...)`), so the model call is billed to the
  user's own key. A missing/broken provider fails the run rather than silently
  falling back to the platform gateway. The **run payload** carries
  `providerSecretId` (presence-based: an explicit `""` forces the platform).
  The **agent builder** and **chat composer** list the user's provider secrets
  in the model picker (chat encodes the choice as `vault:<secretId>:<model>`);
  workflow member agents **inherit** the agent's provider (no per-node override).
- **Per-key usage.** When the runtime runs on a provider secret it records the
  run's tokens (`run.completed.usage` → `vault.record_run`): `runCount`,
  `tokensIn`/`tokensOut`/`tokensTotal`, `lastModel`, `lastUsedAt`, surfaced in
  the Vault list and the Usage page. (Workflow runs use the key but do not yet
  contribute per-key tokens.) `usageCount` stays the `{{vault:name}}` resolution
  counter.
- **Testing** (`src/vault/tester.py`) runs server-side with stdlib `urllib`:
  `GET /models` validates the key + base URL and one tiny `POST /chat/completions`
  confirms the model answers (latency, sample output, model list are returned and
  stored on the item). A small SSRF guard blocks non-https and
  loopback/private/link-local/metadata addresses unless
  `VAULT_ALLOW_PRIVATE_URLS=true` (set locally so a local provider key works; prod false).
  Env: `VAULT_KMS_KEY_ARN`, `VAULT_TEST_TIMEOUT_SECONDS` (15),
  `VAULT_ALLOW_PRIVATE_URLS`. Each secret's last test result is stored and shown
  as a Verified/Test-failed badge.
- Infra: a dedicated `module "vault_kms"` (`get1agent-prod-vault`); `user_api`
  gets `kms_key_arns` + `VAULT_*` env, `mcp_connections` gets the Vault key for
  reference resolution, and the **agent runtime** gets `VAULT_KMS_KEY_ARN` +
  `kms:Decrypt` (provider-as-model + per-key usage). Floci creates
  `alias/get1agent-local-vault` and folds the env into `api_env`. Changing the
  runtime path requires rebuilding/redeploying the AgentCore image.


### LLM budget, pricing & usage accounting

- **Pricing** lives in `packages/core/usage.py`: `MODEL_PRICES` maps a platform
  model id to `(input_usd, output_usd)` **per 1M tokens**, with a
  `DEFAULT_MODEL_PRICE` fallback; override any model with
  `MODEL_PRICE_<ID>` = `"in,out"`. Money is **integer micro-USD** everywhere
  (`1_000_000` micro-USD = $1) so DynamoDB counters stay exact (no `Decimal`
  needed) — `usage.cost_micro_usd(model, in, out)`.
- **AI credits.** The UI prices usage in **AI credits** (`AI_CREDITS_PER_USD`,
  100 credits = $1 by default). `usage.usd_to_credits` / `credits_to_micro_usd` /
  `format_credits` convert between credits and money. The default grant is
  **$0.50 = 50 credits** for everyone, admins included
  (`USER_DEFAULT_BUDGET_USD` / `ADMIN_DEFAULT_BUDGET_USD`).
- **Budget** lives on the existing quota item (`USER#<userId>` / `#QUOTA`):
  `budgetMicroUsd`, `spentMicroUsd`, `platformTokensIn/Out`, `platformRuns`.
  There is **no unlimited mode** — every user has a finite grant, and the only
  remedy at the limit is an admin raising it. Access via
  `data.repositories.quotas`
  (`get_budget`/`check_budget`/`charge_usage`/`set_budget_credits`/`add_budget_credits`/`reset_spend`).
  The retired `unlimited` / `unlimitedSetAt` attributes are cleared once by the
  login-time `ensure_quota` sync.
- **Admins raise limits** from the admin console (`/admin/users`, "AI Credits"):
  `GET /v1/admin/users` (a GSI3 `USERS#all` page — never a Scan),
  `POST /v1/admin/users/{userId}/credits` (`{credits, mode}` — `mode: "add"`
  (default) tops the grant up, `mode: "set"` replaces it and is rejected if the
  new limit is below what the user already spent), and `.../reset` to zero the
  spend. Served by the **`admin-console`** admin Lambda. Admins start on the
  same default as users and simply raise their own grant in that page.
- **Enforcement (clean choke points, no per-request guessing).**
  - The **agent runtime** checks the budget at the start of a run
    (`agentflow.run`): a **platform-gateway** run is refused with a clear
    `run.error` once spent ≥ budget; a run on the user's **own Vault provider
    key is always allowed**, but the planner (platform key) is skipped for an
    over-budget user so the app spends nothing. After the run the platform
    cost is charged from the captured `run.completed.usage`.
  - **Workflows** are charged as platform runs (the host is always the platform
    gateway); the workflow runtime records the normalized `accumulated_usage`.
  - **`user-api` Labs** that spend the platform key (`custom-tools` generate,
    eval runs, playground run/judge) call `_require_budget(claims)` (HTTP
    `402` when exhausted); playground runs are charged per replay.
- **Tracing/usage everywhere.** `agentflow.events.accumulated_usage()` normalizes
  Strands' usage whether it is an object or a dict (camelCase or snake_case) and
  is used by both the agent and workflow runtimes, so cumulative tokens are
  never silently dropped. Cumulative stats surface on the **Usage** page
  (application budget + per-model rates from `GET /v1/user/settings`); the raw
  per-trace view is CloudWatch/X-Ray and is not shown in-app.

### Prompt Playground (trace replay)

- The **Playground** (`frontend/src/pages/PlaygroundPage.tsx`, route
  `/playground`, sidebar section `labs`) replays a real LLM call. It is opened
  from a trace row's **Replay** action on the **Traces page**
  (`/playground?trace=<traceId>`); the trace's **generation** observations are
  loaded from `GET /v1/lab/traces/{traceId}` and the first (or `?generation=`)
  one has its messages and model lifted into an editable prompt. Edit any
  message, change model/temperature/max tokens, and **Run**.
- `POST /v1/lab/playground/run` takes one prompt spec or a `runs[]` array (A/B
  up to 4 models, executed in parallel) and makes one **Amazon Bedrock
  (Converse)** call per run (`src/evals/playground.py`), returning
  `{results: [{ok, model, output, usage, latencyMs}]}`; the UI shows the original
  trace output and each replay side by side. Models are limited to
  `PLAYGROUND_MODELS` (the curated Bedrock set).
- `POST /v1/lab/playground/judge` scores a replay with the **same judges as the
  evaluator** (`judge_relevance`, plus `judge_correctness` with an optional
  reference and `judge_faithfulness`/`judge_context_relevance` when contexts are
  supplied), returning per-metric values + reasoning.
- **`{{variable}}` templating**: message content may contain `{{name}}`
  placeholders; the Playground renders a variables panel and substitutes the
  values before running (frontend-only, `src/lib/promptPlayground.ts`).
- **Save as dataset case**: the replay's last user message and output become a
  dataset case via `POST /v1/evals/datasets/{name}/cases` (dataset created on
  demand), tying the playground into the evaluation flywheel.

### Evaluations lab (RAG offline evaluation)

- The **Evaluations lab** lives in `frontend/src/pages/EvaluationsPage.tsx`
  (route `/evaluations`, sidebar section `labs`; note `ExperimentsPage.tsx` is
  the Playground, a different page) and lets a user run **RAG offline
  evaluations** against a golden dataset. Backend CRUD + the run worker live in
  **`user-api`** (`src/evals/`, `data/repositories/evals.py`); there is no
  separate Lambda.
- **Datasets and their cases are AWS-native** (one item per case, in the shared
  DynamoDB table): a dataset is a `LAB#DATASETS` item named `u_<userId>/<name>`
  (lowercase-hyphen, ≤48 chars) and a case is a `LAB#CASES` item with
  `input = {question}`, optional `expectedOutput`, and
  `metadata.expectedSources`. A **run**
  (`USER#<userId>` / `EVALRUN#<runId>`) only keeps the config + status +
  aggregate metrics for the UI; each **case result**
  (`EVALRUN#<runId>` / `CASE#<caseId>`) is tiny and the bulky artifact
  (retrieved contexts, generated answer, judge reasoning) is one S3 object at
  `evals/<userId>/<runId>/<caseId>.json`. Limits: **50 datasets, 200
  cases/dataset, 20 cases/run** (`src/evals/config.py`, env
  `EVAL_MAX_CASES_PER_RUN`). The Evaluations page's Datasets tab opens a
  **dataset detail** listing every case (query, expected output, and a **View
  trace** link back to its source trace) plus the runs that used the dataset.
- Routes: `GET/POST /v1/evals/datasets`, `GET/PUT/DELETE
  /v1/evals/datasets/{id}`, `GET/POST /v1/evals/datasets/{id}/cases`,
  `DELETE /v1/evals/datasets/{id}/cases/{caseId}`,
  `GET /v1/evals/datasets/{id}/runs` (the runs that used the
  dataset), `GET/POST /v1/evals/runs`,
  `GET/DELETE /v1/evals/runs/{id}`, `GET /v1/evals/runs/{id}/cases`,
  `GET /v1/evals/runs/{id}/cases/{caseId}`. `POST /v1/evals/runs` creates the run
  and starts the work as a **background invocation of user-api itself**
  (`_invoke_self_async`, the same pattern as the Playground turn) so it outlives
  the 30s gateway cap; the SPA polls the run until it completes.
- **The task is the real retrieval path**: each case calls the knowledge-mcp
  `search-user-knowledge-bases` tool over the direct-invoke transport
  (`core.mcp_client`, identity in the payload) and a controlled generator
  answers from the retrieved `chunks[].content` (mode `rag`; `retrieval` skips
  generation). Retrieval and generation are scored **separately** (the
  Ragas convention): deterministic `context_recall`,
  `context_precision`, `hit_rate`, `mrr` when the case declares expected
  sources; the LLM judge runs **in user-api** on Bedrock with **one
  focused call per metric** — Ragas-aligned `faithfulness` (the answer is
  decomposed into atomic claims; score = supported / total) and
  `context_relevance` (every retrieved passage labelled relevant; score =
  relevant / total), plus `answer_relevance`, and `answer_correctness` when an
  expected answer exists. The unsupported claims and passage labels are kept in
  the S3 artifact and shown in the run's case detail (explainability). Ground
  truth is **optional per case** — metrics light up only when their inputs are
  present. Judges return strict JSON via **Amazon Bedrock (Converse)**
  (`EVAL_ANSWER_MODEL` / `EVAL_JUDGE_MODEL`, defaults `amazon.nova-2-lite-v1:0`);
  each case's metrics are stored on its `CASE#<caseId>` result item.
- A run stops persisting before the 300s Lambda timeout
  (`EVAL_RUN_BUDGET_SECONDS`, default 260) and marks remaining cases `skipped`.
  `user-api` now direct-invokes `knowledge-mcp`, so its role needs that
  `lambda:InvokeFunction` grant (`lambda_invoke_arns`).
- **Runs persist to DynamoDB + S3**: the background worker loads the dataset's
  cases from the Lab store and, per evaluated case, writes a tiny
  `CASE#<caseId>` result item (metrics) plus one S3 artifact
  (`evals/<userId>/<runId>/<caseId>.json`) holding the retrieved contexts,
  generated answer and judge reasoning; the aggregate metrics live on the run
  item. Everything is AWS-native — no external experiment service.
- **Agent task (service auth).** A run's `config.task` is `rag` (default: the
  retrieval + answer pipeline) or `agent` (re-run a saved agent end to end).
  The agent task has no user JWT, so the worker authenticates as the **platform
  service**: it fetches an Auth0 client-credentials (M2M) token, direct-invokes
  the **agent-run control plane** (IAM) to launch a MicroVM, POSTs the run to
  its `/invocations` (service bearer + ingress token) and reads the SSE frames
  (`src/evals/agent_client.py`). The runtime trusts that token only when its
  `sub` is `<SERVICE_AUTH_CLIENT_ID>@clients` and then takes the target `userId`
  from the payload (`agentflow/identity.py`). Metrics: `answer_relevance`
  (no-context judge), `answer_correctness` when the case has an expected answer,
  and trajectory metrics `tool_precision`/`tool_recall`/`tool_f1`/`tool_calls`
  when the item's metadata carries `expectedTools`. Knowledge bases are optional
  for agent runs. Env: `AGENT_RUN_FUNCTION`, `AGENT_SERVICE_CLIENT_ID` /
  `AGENT_SERVICE_CLIENT_SECRET`, `AUTH_AUDIENCE`, `AUTH_TOKEN_URL` (defaults
  to `https://<auth_domain>/oauth/token`); the agent runtime gets
  `SERVICE_AUTH_CLIENT_ID`. Auth0 setup: one Machine-to-Machine app authorised
  for the API audience, then set the TF vars.

#### AWS-native curation (traces page, datasets, annotation queues)

- The **curation** layer is AWS-native: `user-api` serves **`/v1/lab/*`** from
  `src/evals/store.py` (the **Lab store**), which keeps everything in the shared
  `get1agent` DynamoDB table under `LAB#` partitions. Every dataset /
  annotation-queue / score-config name is namespaced **`u_<userId>/<name>`**, so a
  user can only ever read or write their own objects. Trace ids are the
  OpenTelemetry trace ids exported to CloudWatch/X-Ray.
- **Traces page** (`frontend/src/pages/TracesPage.tsx`, route `/traces`, sidebar
  `labs`) is the only place a trace can be **added to a dataset or an annotation
  queue** — there are no such actions on the chat, builder, or evaluations
  screens. It lists the caller's traces (`GET /v1/lab/traces`, derived from the
  user's stored conversations) and offers **Dataset** / **Queue** actions per row.
- Routes: `GET /v1/lab/traces`; `POST /v1/lab/traces/{traceId}/dataset`
  (creates a dataset item with `sourceTraceId` + a deterministic item id so
  re-adding upserts); `POST /v1/lab/traces/{traceId}/queue` (ownership-checked,
  then a queue item with `objectType=TRACE`); `GET/POST /v1/lab/datasets`;
  `GET/POST /v1/lab/queues`; `GET/POST /v1/lab/score-configs`.
- **Review queues**: `GET /v1/lab/queues/{queueId}/items` (pending items), `GET
  /v1/lab/traces/{traceId}` (the trace for rendering), and `POST
  /v1/lab/queues/{queueId}/items/{itemId}` (writes scores — categorical/boolean/
  text via `stringValue`, numeric via `value` — and optionally completes the
  item). Score configs are created or selected in the add-to-queue dialog, and the
  Traces page's **Review queues** tab opens the review surface
  (`QueueReviewDialog`).
- **Metrics page** (`frontend/src/pages/MetricsPage.tsx`, route `/metrics`) is
  populated by `GET /v1/lab/metrics`, which aggregates the caller's runs from the
  Lab store + conversation counts + `core.usage` spend (a daily series + totals,
  per-score averages). `configured` is always true (AWS-native).
- **Usage page** (`frontend/src/pages/UsagePage.tsx`, route `/usage`, sidebar
  `manage`) is the workspace-wide live view: the run/token/cost KPIs and the
  per-model breakdown come from the same `/v1/lab/metrics` route, the **provider
  keys** card reads the real Vault (masked, with per-key use counts + test status
  and a Manage link), and the **Resources** tab aggregates the real limits already
  returned by `/v1/knowledge-bases`, `/v1/storage/files`, `/v1/agents`,
  `/v1/workflows`, `/v1/agent-skills`, `/v1/mcp/connections` and
  `/v1/vault/secrets`. The **Network tools** card reads `GET /v1/user/network`
  (current-hour runs vs the rate limit, all-time network runs, the per-run
  connection cap, timeouts and whether an admin disabled network access). There
  is **no billing/credit backend**, so no invoice or
  balance data is fabricated — every number on the page is server-derived.
- The eval lab is fully AWS-native: datasets + cases in DynamoDB, per-case
  artifacts in S3, metrics on the run item. The worker can run either the RAG task
  or a saved **agent** end to end (service auth, above).

### Bedrock cost & latency levers

One module, `core/bedrock_features.py`, owns the knobs (all env-driven, safe defaults):

- **Prompt caching** — `BEDROCK_PROMPT_CACHE` (`auto`|`anthropic`|`off`) +
  `BEDROCK_PROMPT_CACHE_TTL` (`5m`|`1h`). The agent runtime passes Strands
  `cache_config` (system prompt + tool schemas cached); the Labs add a
  `cachePoint` to the Converse `system` block. Cache reads are up to ~90% cheaper.
- **Service tiers** — `BEDROCK_SERVICE_TIER` (`standard`|`flex`|`priority`).
  Ingestion embedding defaults to **`flex`** (~50% cheaper, batch-tolerant);
  chat stays `standard`.
- **Intelligent prompt routing** — `BEDROCK_PROMPT_ROUTER_ARN` (empty disables).
  Routes within a model family (Nova Lite ↔ Pro) to the cheapest capable model.
- **Application inference profiles** — `BEDROCK_PROFILE_CHAT` / `_EVAL` /
  `_INGESTION` (workload is selected via `BEDROCK_WORKLOAD`, set to `eval` by the
  judges and `ingestion` by the embed worker) so the bill is attributable per
  feature. `resolve_model()` applies profile → router → model.
- **Structured outputs** — `core.bedrock_chat.converse(..., output_schema=…)`
  constrains the model to a JSON Schema object (`outputConfig.textFormat.type =
  "json_schema"`, schema as a JSON string; the value is read back from the
  response content, from a `json` block or the `text` JSON). Used by the eval
  **judge** and the custom-tools **generator**; both fall back to prompt-only
  JSON parsing when the model or schema is unsupported, so generation/judging
  never fails outright.
- **Guardrails as IaC** — `aws_bedrock_guardrail` (+ `_version`) defines the
  content/PII/topic policy in Terraform; `local.guardrail_id` feeds
  `GUARDRAIL_ID`, falling back to `var.guardrail_id` when `enable_guardrail_iaC=false`.

### AgentCore Registry, Evaluations, Optimization & Browser

- **Registry (A5) — not provisioned.** The managed catalog would be
  `aws_bedrockagentcore_registry`, but that resource is **deprecated and disabled**
  in Terraform (it hangs the AWS provider; see the note in
  `infra/terraform/envs/prod/backend.tf`), so `registry_id`/`registry_arn` are
  empty. `core/registry.py` publishes/searches when an ARN is supplied, and
  `admin-console` exposes `GET /v1/admin/platform/registry`,
  `POST .../publish`, `GET .../search` — all reporting "not configured" until one
  exists. The **product's** publish-to-library does **not** use it: it flips
  `visibility=public` and projects onto the DynamoDB GSI3 `AGENTLIB#public`
  (see Agents). Env: `AGENTCORE_REGISTRY_ARN`, `AGENTCORE_REGISTRY_ID`.
- **Evaluations (A6)** — managed `aws_bedrockagentcore_evaluator` resources are
  created, but the **online-evaluation config is not**: it samples live traces from
  the CloudWatch `aws/spans` group, which is AWS-reserved and cannot be created by
  Terraform, so it is disabled (`online_evaluation_sampling_percentage` is
  reserved/unused until that group exists). **The app's own judge lab
  (`src/evals/`) is the working evaluation path** — datasets, runs, the Bedrock
  judge and the S3 case artifacts are fully wired.
- **Optimization (A7)** — `core/optimization.py` surfaces availability and the
  config surfaces it may rewrite (`system_prompt`, `tool_descriptions`);
  admin-only route `GET /v1/admin/platform/optimization`. Insights/Recommendations
  consume Evaluations results and are free during preview.
- **Browser (A8)** — `aws_bedrockagentcore_browser` backs a new **`browser` MCP
  server** (`backend/services/mcp/browser/`, `POST /mcp/browser`, agent `builtin`
  server `browser`). Tools: `open-browser-session` / `close-browser-session`.
  `core/browser.py` starts/stops sessions and enforces a **domain allowlist**
  (`BROWSER_ALLOWED_DOMAINS`, empty denies all); the `browser` tool is also
  covered by AgentCore Policy. Admin-only routes (admin-console) under
  `/v1/admin/platform/browser` (`GET`, `POST /check`, `POST /session`,
  `POST /session/close`). Env: `BROWSER_ID`, `BROWSER_REGION`,
  `BROWSER_ALLOWED_DOMAINS`, `BROWSER_MCP_FUNCTION`.

### AgentCore Identity (managed OAuth)

- Third-party tokens (Google/GitHub/Slack/…) are held by the **AgentCore Identity
  token vault**, not the app: `aws_bedrockagentcore_workload_identity` gives the
  runtime a machine identity, `aws_bedrockagentcore_token_vault_cmk` stores tokens
  under the deployment's KMS key, and one
  `aws_bedrockagentcore_oauth2_credential_provider` per provider holds the client
  credentials. Providers are created only when their credentials are supplied
  (`identity_google_client_id`, `identity_github_client_id`, `identity_slack_client_id`).
- `core/identity.py` resolves a provider key to its ARN and calls
  `GetResourceOauth2Token` for a user. Only **`admin-console`** calls it today
  (the agent runtime carries the IAM grant but has no code path that uses it), so
  treat Identity as an **admin/platform surface**, not part of a run.
- **MCP server OAuth tokens are stored by the app**, not by AgentCore Identity:
  `mcp-connections` keeps them encrypted per user (`data/repositories/
  mcp_connections.save_tokens`, KMS) and refreshes them itself. Identity is
  available for on-behalf-of delegation; it is not what backs the MCP connect
  flow.
- Routes (admin-only, admin-console): `GET /v1/admin/platform/identity`,
  `POST /v1/admin/platform/identity/token` (fetch a user's token by provider —
  never returns the raw secret to the client).
  Env: `AGENT_WORKLOAD_IDENTITY_ARN`, `AGENT_TOKEN_VAULT_ID`,
  `AGENT_IDENTITY_PROVIDERS`, `AGENT_IDENTITY_RETURN_URL`.
- The Vault (KMS-encrypted user secrets) remains for user-supplied API keys;
  AgentCore Identity is the managed path for OAuth delegation.

### AgentCore Gateway (managed MCP)

- The platform's MCP servers are fronted by one **AgentCore Gateway**
  (`aws_bedrockagentcore_gateway`, protocol `MCP`, `AWS_IAM` authorizer, semantic
  tool search). Every MCP Lambda (knowledge, code-interpreter,
  http-fetch, storage, custom-tools, remote MCP) is registered as a **Lambda target**
  (`aws_bedrockagentcore_gateway_target`, `target_configuration.mcp.lambda`), so
  agents call a single signed HTTPS endpoint instead of invoking each function.
- The deployed runtime sets `MCP_TRANSPORT=gateway` and receives the endpoint as
  `MCP_GATEWAY_URL`; `agentflow/tools.py` then routes every tool call through
  `core.mcp_client.gateway_call_tool`, which signs the request with **SigV4**
  (`bedrock-agentcore`) and normalizes JSON **or SSE** MCP responses. The in-app
  direct-invoke path remains for local development
  (`MCP_TRANSPORT=aggregator`).
- The gateway also carries a `policy_engine_configuration` pointing at the managed
  policy engine, so tool-call policy is enforced at both the gateway and in
  process. The gateway role can only `lambda:InvokeFunction` the six MCP servers.

### AgentCore Memory + Policy (AWS-native)

- **User memory is Amazon Bedrock AgentCore Memory, scoped to the user.**
  `agentflow/memory.py:build_memory_manager` builds the official Strands
  `AgentCoreMemoryStore`: the **user id is the actor** and the namespace is
  **user-only** (`namespace_path="/users/{actorId}/"`, no session or agent
  component), so long-term memory is recalled across sessions, agents and
  workflows. The store is writable with **server-side extraction** and
  `InvocationTrigger` (extract after every invocation, so a new fact is
  recallable quickly); `MemoryManager`'s search tool + passive `<memory>`
  injection are on (`add_tool_config` stays off — `AgentCoreMemoryStore` has no
  `add`). Injection renders on **every** model call with the user's latest ask as
  the query, so `build_memory_manager` returns a run-scoped `MemoryManager`
  subclass that memoizes `search` — an unmemoized run embeds and searches the
  user's memory once per LLM call (six searches to answer a six-step question),
  and a query's results cannot change within a run. `memory_injection_config()` is
  the single owner of the `everyTurn` + user-anchored-query policy, so the runtime
  and its tests cannot drift apart. One managed resource per deployment
  (`aws_bedrockagentcore_memory`
  with `SEMANTIC` `/users/{actorId}/facts/` and `USER_PREFERENCE`
  `/users/{actorId}/preferences/` strategies) and its id is injected as
  `AGENTCORE_MEMORY_ID`. `config.memory.enabled` is legacy and ignored: memory is
  a **workspace setting** (`memoryEnabled`, default on) toggled on the Memory
  page. `AGENT_MEMORY_BACKEND=dynamo` selects the in-app `DynamoMemoryStore`
  (`USER#<userId>` / `MEM#<memId>` items + S3 Vectors `status="memory"`) and
  exists **only** for local dev/tests; a deployed runtime always uses the managed
  service, and a missing `AGENTCORE_MEMORY_ID` raises (the run loop degrades to
  no-memory instead of failing the run).
- **Memory page + erase APIs** (`/v1/memory`, in `user-api` via
  `core/memory.py`): the **Memory** page (sidebar **Resources**, route `/memory`)
  lists, searches, deletes individual records and erases all memory; the toggle
  writes the workspace setting. `core/memory.py` uses **raw boto3** (no
  `bedrock_agentcore` SDK dependency in `user-api`):
  `list_memory_records`/`retrieve_memory_records`, `delete_memory_record`,
  `batch_delete_memory_records` + `list_sessions`/`list_events`/`delete_event`
  for a full erase. Every call is namespaced `/users/<userId>/`, so a user can
  only ever read/erase their own memory. DPDP: `/v1/user/export` includes the
  user's memory, and account erasure (`/v1/user/account`) clears it
  (`memoryErased`).
- **Every tool call is governed by AgentCore Policy** (`core/policy.py`,
  `agentflow/memory.build_guard`). The engine id is a managed
  `aws_bedrockagentcore_policy_engine` injected as `AGENT_POLICY_ENGINE`; both the
  single-agent and multi-agent runtimes pass the guard into `build_tools`, so the
  check runs before any MCP server is invoked and a denial is returned to the
  model as `Blocked by policy: <reason>`. `AGENT_POLICY_DENY_TOOLS` denies tools
  outright; `AGENT_POLICY_MODE` (default `enforce`) may be set to `report` to stage
  a rule. A guard that raises **fails closed**.

### Bedrock Guardrails

- **Users create their own guardrails.** The Guardrails page (in the **Build**
  sidebar section) calls Bedrock's control plane and stores one item per
  guardrail (`USER#<userId>` / `GUARDRAIL#<name>`; `data/repositories/guardrails.py`).
  The app-side `name` is a lowercase-hyphen slug (the item key, ≤48 chars, ≤20 per
  user); Bedrock's raw id lives in `guardrailId`. The UI policy (content filters,
  denied topics, word filters, sensitive information, contextual grounding) is
  kept in the item's `config` so the editor can reload it;
  `core/guardrails.policy_config_kwargs` maps it to the Bedrock request and
  `default_policy_config()` is the standard starting set.
- A guardrail is referenced by **Bedrock id only** — the version is always
  Bedrock's working `DRAFT` and is never user-configurable. The agent runtime
  applies it on every model call via Strands' `guardrail_*` kwargs
  (`agentflow/models.py`); `core/guardrails.py` exposes `enabled()`,
  `guardrail_config()`, `config_for(id, version)`,
  `apply(text, source=…, guardrail_identifier=…)`, plus the management calls
  (`create_managed_guardrail` / `get_managed_guardrail` /
  `update_managed_guardrail` / `delete_managed_guardrail`).
- **Resolution** (`agentflow/guardrails.py:resolve_guardrail`, one small
  `GetItem` on the settings item): the agent/workflow's own
  `config.guardrail = {enabled, id}` wins (an explicit id, or `enabled:false` to
  opt out); a workflow's guardrail is the fallback for its member agents; then
  the user's workspace default (`guardrailId` on `#SETTINGS`, saved by the
  Guardrails page); then the platform-wide `GUARDRAIL_ID` env (Terraform). A run
  on the user's own Vault provider key has no Bedrock guardrail (third-party
  endpoint).
- **Per agent / per workflow.** `config.guardrail` is part of the canonical agent
  config and the workflow config; the agent builder (agent card → Guardrail
  group) and the workflow inspector (host card) expose a toggle + a **dropdown of
  the user's guardrails** (plus "Workspace default"), defaulting to the workspace
  guardrail. The runtime resolves it for the single-agent model
  (`agentflow/run.py`), the workflow host and every member (`workflow/build.py`).
  The agent runtime role carries `bedrock:ApplyGuardrail` on
  `guardrail/*`, and `user-api` carries the guardrail management actions
  (`enable_guardrail_management` on the Lambda module).
- Env: `GUARDRAIL_ID` (empty disables), `GUARDRAIL_VERSION` (default `DRAFT`).
- Routes (in `user-api`, registered in API Gateway + Floci): `GET /v1/guardrails`
  (the user's guardrails + the effective default), `POST /v1/guardrails` (create),
  `GET/PUT/DELETE /v1/guardrails/{name}` (detail/update/delete),
  `PUT /v1/guardrails/config` (record the workspace default id on the settings
  item), `POST /v1/guardrails/test` (`ApplyGuardrail` on a text; uses the
  supplied id, else the saved default, else env). Deleting a guardrail clears it
  from the workspace default when it pointed there.
- Frontend: the **Guardrails page** (`frontend/src/pages/GuardrailsPage.tsx`,
  route `/guardrails`, sidebar `build`) lists the user's guardrails, creates and
  edits them (`components/guardrails/GuardrailEditorDialog.tsx` — the full policy
  editor), sets the workspace default, tests a guardrail, and deletes it.
### Remote MCP servers & connections

- `mcp-connections` (`backend/services/mcp/mcp-connections/`) is the **OAuth broker
  and connection store** for remote (Streamable HTTP) MCP servers, plus an
  **aggregator MCP server**. It is outside the VPC and reaches providers over
  public HTTPS.
- Shared code: `core.oauth` (PRM discovery RFC 9728 → AS metadata RFC 8414 →
  registration (pre-registered/CIMD/DCR) → Auth Code + PKCE S256 + `resource`
  RFC 8707 → token exchange/refresh), `core.mcp_http` (Streamable HTTP JSON-RPC
  client — JSON and SSE responses, `Mcp-Session-Id`, `MCP-Protocol-Version`),
  `core.crypto` (KMS `Encrypt`/`Decrypt` with an encryption context bound to
  `{userId, connId, field}`; 4096-byte direct limit).
- Routes: `GET /v1/mcp/catalog`, `GET /v1/mcp/registry`, `GET/POST /v1/mcp/connections`,
  `GET/PATCH/DELETE /v1/mcp/connections/{id}`,
  `POST /v1/mcp/connections/{id}/{refresh|authorize|token}`,
  `GET/PATCH /v1/mcp/connections/{id}/tools`, `POST /v1/mcp/connections/{id}/call`,
  `GET /v1/mcp/oauth/callback` (**unauthenticated** — the browser redirect; the
  single-use `state` embeds the userId, so no Scan is needed), and
  `POST /mcp/remote` (the aggregator MCP server for agents).
- **Tokens**: encrypted in the connection item; tool schemas cached in S3. An
  `apikey` connection's token may be a Vault reference (`{{vault:name}}`) instead
  of a literal value — resolved at call time (see the Vault section).
  Refresh is **lazy** on every outbound call (60 s skew) with rotation-safe
  compare-and-swap (`save_tokens(..., expected_refresh_enc=...)`) so concurrent
  refreshes cannot lose a rotated token. On `invalid_grant` the connection goes
  `reauth_required` and the UI offers Reconnect (`/authorize`). Never refresh on
  a timer.
- **Catalog**: `src/catalog.json` is public, reviewable data (served by
  `GET /v1/mcp/catalog`) and holds the curated/featured servers. Entries carry
  OAuth overrides for providers without standard metadata and the **names** of
  the env vars holding pre-registered client credentials — never the secrets.
  GitHub (launch provider) is pre-registered: register a GitHub OAuth App with
  callback `<api>/v1/mcp/oauth/callback` and set `MCP_GITHUB_CLIENT_ID` /
  `MCP_GITHUB_CLIENT_SECRET`.
- **Registry**: `GET /v1/mcp/registry?search=&cursor=&limit=` proxies the official
  public MCP Registry (`registry.modelcontextprotocol.io`, override with
  `MCP_REGISTRY_URL`), so the SPA can browse/search any published server without
  us maintaining a list. The proxy keeps only `streamable-http` remotes that do
  **not** require a caller-supplied header credential (open or OAuth — OAuth is
  not labelled by the registry; the connect flow probes it). Results are cached
  in-container for `MCP_REGISTRY_CACHE_TTL_SECONDS` (600). Connecting a registry
  entry goes through the normal `POST /v1/mcp/connections` `{name, url}` path.
- **Aggregator**: `POST /mcp/remote` merges every connected server's cached tools
  (namespaced `<slug>/<tool>`) and proxies `tools/call` with a refreshed token.
  Future agents consume built-ins via `core.mcp_client` and remotes via this
  endpoint.
- **stdio servers are not run in Lambda** (no persistent stdin/stdout; stateful
  servers break). Managed stdio hosting (containers on AgentCore Runtime) is a
  later phase; the public catalog currently lists remote HTTP servers only.

### Sign-in (Google via Auth0)

- **Google-only auth via Auth0.** The frontend signs in with
  `loginWithRedirect` pinned to the Google social connection
  (`AUTH_GOOGLE_CONNECTION`, default `google-oauth2`, override
  `VITE_AUTH_CONNECTION`). Auth0 renders the Google account chooser, so there is
  **no extra Google client id on the frontend** and no One Tap script.
- Sign-in is a manual choice on `/login` (no silent redirect). The fixed navbar
  carries **Sign in with Google** and **Demo**; the read-only demo is the other
  way in.

### Admin console & strict role separation

- **Admin** is an Auth0 role. The Login Action copies `event.authorization.roles`
  onto namespaced custom claims: `https://get1agent.com/roles` and
  `https://get1agent.com/isAdmin`. Assign the `admin` role in Auth0; re-login
  refreshes the tokens.
- Shared role logic lives in the `core` package (`core.auth`):
  `is_admin_claims`, `require_admin` and `require_user`. The same package holds
  the thin MCP JSON-RPC client (`core.mcp_client`) and the shared MCP
  transport (`core.mcp_server`).
- **View-based access, enforced server-side** — the frontend is only a UX gate.
  The SPA sends `x-active-view` (`user` | `admin`); the backend validates it
  against the token's real roles:
  - `require_user` (user view): `user-api` and the `knowledge-mcp` **HTTP** path.
    An admin who chose the user view is allowed.
  - `require_admin` (admin view): `admin-console`.
  - No header → falls back to `admin` if the token has the admin role, else
    `user`.
- Admin code is kept separate: frontend UI under `frontend/src/admin/`, backend
  Lambda under `backend/services/admin/admin-console/`.
- **`admin-console`** (`GET /v1/admin/mcp/tools`, `POST /v1/admin/mcp/call`) is the
  MCP *client*: it reads the admin claim + `sub`, resolves the caller's internal
  `userId`, builds MCP JSON-RPC, and invokes every MCP server in `MCP_FUNCTIONS`
  over their direct-invoke transports, merging their tool lists and routing each
  call to the owning server. It also serves the admin **AI-credit** routes
  (`GET /v1/admin/users`, `POST /v1/admin/users/{userId}/{credits|reset}`), the
  support/security inboxes and the admin **Platform status** routes
  (`/v1/admin/platform/*`: Identity, Registry, Browser, Optimization, Bedrock
  levers, Network tools) — see
  the budget section. The admin SPA pages are `AdminIntegrationsPage`
  (`/admin/mcp-tools`) and `AdminUsersPage` (`/admin/users`, sidebar "AI Credits").

### Read-only demo ("View") mode

- The start screen (`frontend/src/pages/LoginPage.tsx`, `/login`) offers **Sign
  in** or **View demo — read-only** — it no longer auto-redirects to Auth0, so a
  prospective customer can explore without an account.
- Demo mode is a localStorage flag (`auth/demo.ts` + `useDemoMode`). When on,
  `useApiClient` returns a **demo client** (`lib/api.ts`): GETs are answered from
  canned data (`lib/demoData.ts`, shapes mirror the real API) and **every write
  is rejected client-side** with a friendly "read-only demo" message. No request
  reaches the network, so there are no 401s.
- The route guards allow the shell without an account (`RequireAuth`/`RequireUser`
  short-circuit on demo; `RequireAdmin` redirects to the dashboard), and a sticky
  **read-only banner** + a "Sign in" action sit in `MainLayout`/`AccountMenu`.
  The question is never persisted; leaving demo mode (Sign in) restores the real
  API client.
- **Security is unchanged and enforced by the backend**: every API Gateway route
  is JWT-protected, so even a hand-crafted API call without a token is rejected
  regardless of the UI. The demo is a UX layer, not an access-control boundary.

## Conventions

### Page loading states

Loading is handled in one place per concern — never hand-roll timers per page.

- **Route entry (all pages):** routes are lazy (`React.lazy` in `App.tsx`) and
  `RouteGate` in `layouts/MainLayout.tsx` is a pass-through suspense boundary
  with an empty fallback — the page mounts directly and its own data skeleton
  below covers slow loads. No route-level skeleton (a generic one flashed a
  different shape before the page's own skeleton appeared).
- **Page data:** fetch with `usePageQuery(key, fetcher)`
  (`frontend/src/hooks/usePageQuery.ts`). Render a **shaped skeleton** while
  `isPending`, inside a single `<PageShell>`:
  ```tsx
  const { data, isPending } = usePageQuery('my-page', () =>
    api.get<MyData>('/v1/...'),
  )
  return (
    <PageShell>
      {isPending ? <MyPageSkeleton /> : <MyPageContent data={data!} />}
    </PageShell>
  )
  ```
- Skeletons are neutral (no accent color) and use the `.skeleton` shimmer
  (`frontend/src/index.css`); primitives live in
  `frontend/src/components/ui/Skeleton.tsx`.
- Small inline/button loading uses the circular `<Spinner />`, not a skeleton.

### Live ingestion activity

The ingestion timeline refreshes through `useAdaptivePoll`
(`frontend/src/hooks/useAdaptivePoll.ts`) — never hand-roll an interval per page.

- Polling only runs while the **Activity panel is open** and something is
  active (`pending`/`uploaded`/`processing`). A closed panel makes zero requests.
  For a Graph RAG KB the **graph** stage runs *after* the document is `ready`
  (Index sets the status), so `graphStagesInFlight()`
  (`frontend/src/lib/knowledgeBases.ts`) also counts an unresolved graph stage —
  and the short Index → Graph window — as active; document status alone would
  stop polling before the stage finishes and freeze the card on "Extracting…".
- Backoff 2s → 15s, reset when a new event arrives; paused while the tab is hidden.
- Stops after 10 minutes of active polling and shows a manual **Refresh**.
- Tune it in exactly one spot: the `useAdaptivePoll` call in
  `frontend/src/pages/KnowledgeBasesPage.tsx`.

## Local development

Everything runs locally on **Floci** — a free, LocalStack-compatible AWS
emulator (no AWS account, no auth token). Lambda, API Gateway, S3, SQS,
EventBridge and Step Functions run in Docker; **DynamoDB Local** stores
operational data. There is no custom local emulation: the same Lambda code, the
same state machine definition and the same API routes as production run against
Floci, configured only by environment variables.

```bash
make floci            # build + start + provision; prints the API URL
make ui               # React app -> http://localhost:5173
make floci-logs       # follow Floci logs
make floci-down       # stop and remove (named volumes are kept)
```

- **State persists across restarts.** Floci runs `FLOCI_STORAGE_MODE=persistent`
  backed by the `floci_data` volume (`/app/data`), and DynamoDB Local uses
  `-dbPath /home/dynamodblocal/data` on the `dynamodb_data` volume. So uploaded
  documents and the retrieval index survive `make floci-down`/`floci-up`. To
  reset everything, `docker compose -f infra/local/floci/docker-compose.yml down -v`.

- **Lambda cold starts are real, and are the dominant local latency source.**
  Every emulated Lambda is a Docker container, and Floci tears an idle one down
  after `FLOCI_SERVICES_LAMBDA_CONTAINER_IDLE_TIMEOUT_SECONDS` (Floci's default
  300s; `docker-compose.yml` sets **3600**). A cold container costs ~3–4s
  (container create + Python/boto3 import) versus ~30–90ms warm, and the cost
  multiplies per Lambda a request touches: `GET /v1/admin/mcp/tools` invokes five
  containers **sequentially** (`core.mcp_client.list_tools_multi` loops over
  `MCP_FUNCTIONS`), so it measures **~14s cold vs ~0.7s warm**. Raise the knob to
  stay warm longer; `0` (or `FLOCI_SERVICES_LAMBDA_EPHEMERAL=true`) always
  cold-starts. Changing it needs a container recreate (`make floci-up`).

- API base URL: `http://get1agent.execute-api.localhost.floci.io:4566`
  (`localhost.floci.io` resolves to 127.0.0.1 on the host, and Floci's embedded
  DNS resolves it inside Lambda containers, so presigned S3 URLs work from both).
- Point the UI at it via the Vite dev proxy:
  `printf 'VITE_API_URL=/\nVITE_API_PROXY_TARGET=http://get1agent.execute-api.localhost.floci.io:4566\n' > frontend/.env.local`
- Auth: the HTTP API uses a JWT authorizer against the real Auth0 issuer, so the
  Floci container needs network access to `https://get1agent.us.auth0.com/`.
- Compose file: `infra/local/floci/docker-compose.yml`. Host env: the root
  `.env` (from `infra/local/floci/env.example`).
- **Real AWS from local.** `.env` sets no credentials: host processes use your
  normal chain (exported vars, `~/.aws`, SSO). `make floci-up` resolves the same
  chain with `aws configure export-credentials` and passes it to the Floci
  container. Floci does **not** forward those to Lambda containers — it injects
  emulated execution-role credentials instead, so a function hitting real AWS
  fails with `UnrecognizedClientException`. The compose stack therefore sets
  `FLOCI_SERVICES_LAMBDA_AWS_CONFIG_PATH=${HOME}/.aws`, which bind-mounts the
  host's real `~/.aws` into every Lambda (Floci exposes it via
  `AWS_SHARED_CREDENTIALS_FILE`). `user-api` additionally pins
  `AWS_ENDPOINT_URL_BEDROCK_RUNTIME` to real AWS (Floci's `bedrock-runtime` is a
  **stub** that returns `"Floci stub response for model=…"`), so the Labs reach
  real Bedrock. Credentials come from `~/.aws` (refresh with `aws sso login`; no
  snapshot to re-export for the Lambdas). The **agent** container is the
  exception: it mounts the host's `~/.aws` read-only and reads live credentials,
  so it does not depend on the export (a missing export used to silently fall
  back to Floci's placeholder `test` keys and every `ConverseStream` failed with
  `UnrecognizedClientException`). (Web Search is the AgentCore Gateway
  connector and is **not** available locally: the gateway is not emulated.)
- **The agent runs in the stack.** The `agent` compose service (built from
  `backend/agents/Dockerfile`, context `backend/`) runs the AgentCore app
  continuously on host `:8090` (Vite proxies `/agent-run` to it) — there is no
  host-run `make agent`. It reads the repo-root `.env` and overrides the
  endpoints for the compose network (`DYNAMODB_ENDPOINT_URL=http://dynamodb:8000`,
  `AWS_ENDPOINT_URL=http://floci:4566`). After agent-side changes:
  `make floci-reload` (rebuilds the image + re-provisions Floci in place).
- **Rate limiting & Redis.** The stack ships a `redis` compose service — the
  **full Redis Stack** image (`redis/redis-stack-server`, so `FT.*`/RediSearch is
  present for the semantic cache, matching a Redis Cloud instance with the search
  module) with persistence off and an LRU policy sized to mirror the managed
  instance's shape. `redis-server` flags come from the image's `REDIS_ARGS` env
  (a compose `command:` would replace `/entrypoint.sh` and drop the modules). The
  Lambdas run with `RATELIMIT_BACKEND=auto`, `CACHE_BACKEND=auto`,
  `SEMANTIC_CACHE_BACKEND=auto` and `REDIS_URL=redis://redis:6379/0`, so the
  limiter (GCRA), the exact cache, the semantic cache and the Bedrock token
  bucket all run on Redis and fall back to DynamoDB / S3 Vectors if it is
  unreachable. `make floci`/`floci-up` starts and provisions it alongside the
  rest; set `RATELIMIT_BACKEND=dynamodb` (or `CACHE_BACKEND=dynamodb`,
  `SEMANTIC_CACHE_BACKEND=s3vectors`) in the root `.env` to exercise the fallback
  without Redis. Production gets the URL from the SSM SecureString
  (`REDIS_URL_SSM_PARAM`), not from the compose env.
- `infra/local/floci/init/ready.d/10-provision.py` mirrors Terraform: DynamoDB
  table + GSIs, bucket + EventBridge notification (`raw/` prefix) → rule → SQS +
  DLQ → dispatcher → state machine → workers, plus the HTTP API + JWT authorizer
  + routes from `infra/terraform/envs/prod/api_gateway.tf`.
- The state machine definition is the same file Terraform deploys:
  `infra/terraform/modules/ingestion/statemachine.asl.json`.
- Ingestion runs with `EMBED_MODE=bedrock` in Floci: it embeds with the real
  Amazon Titan models on AWS (the stack ships no offline embedder), using the
  credentials forwarded from the host — see "Real AWS from local".
- Retrieval runs with `VECTOR_STORE=local` (brute-force cosine over
  `index/<userId>/vectors.json`; S3 Vectors is not emulated) and
  `RERANK_MODE=none` (rerank is opt-in per request). Set `RERANK_MODE=local` to
  use the HuggingFace TEI `reranker` container instead; `make floci` then starts
  it and waits for `/health`. (`RERANK_MODE=bedrock` calls Bedrock Rerank, which
  needs AWS credentials.)
- After changing Lambda code: `make floci-build` then `make floci-up`
  (provisioning is re-run on every boot), or `make floci-reload`.
- Local OAuth for remote MCP servers: providers reject plaintext-HTTP redirect
  URIs unless loopback, and Floci only serves the API on its own host. The
  `oauth-proxy` compose service (a stdlib loopback forwarder) runs with the
  Floci stack — started by `make floci`/`floci-up`, left running by
  `floci-reload` — so just set
  `MCP_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/v1/mcp/oauth/callback`.
  `make floci-oauth-proxy` (re)starts it and `make floci-oauth-proxy-logs`
  follows its logs if needed.

### Migrations

DynamoDB schemas are declarative: Terraform
(`infra/terraform/modules/dynamodb`) creates the table, GSIs and indexes, and
the Floci init hook mirrors it locally. Adding an attribute or GSI is a
code/Terraform change.

## Commands

- Frontend: `npm run dev`, `npm run lint`, `npm run build`
- Backend tests: `make test` — integration tests in `backend/services/integration-tests/` using
  `moto` (DynamoDB) + an in-memory S3 double. No Docker, no AWS. Run a single
  file with `cd backend/services/integration-tests && uv run pytest test_search.py`.
- Per-lambda unit tests: `make test-unit` (or `make -C backend/services/mcp/knowledge-mcp test`)
  — stdlib `unittest` in each app's `tests/` dir. The integration suite gates
  every deploy; each Lambda's own unit tests run before it is packaged.
- Local Lambdas / infra: see "Local development" above (`make floci-*`).
- Backend Lambdas: `make -C backend/services/<name> package`;
  `bash infra/aws/deploy-backend.sh <name|group> [package|deploy]`. The
  `Backend` workflow deploys by group (`user-apis`, `knowledge-mcp`,
  `admin-apis`, `mcp-tools`, `ingestion-apis`), defined by the `group` field in
  `backend/registry.json`.

## Rules

- **Follow the data-access rules in "DynamoDB single table" above — they are
  mandatory.** One item per entity; small metadata only in DynamoDB (vectors and
  bulky artifacts in S3 Vectors/S3); `GetItem`/`Query` only (no `Scan`, no N+1);
  atomic counters on their own item; TTL for ephemeral items. This is what keeps
  the app fast — do not deviate without recording it in the design doc.
- Run everything locally through the Floci stack (`make floci-*`); it is the
  approved way to run Lambda in Docker and emulate AWS services locally. Do not
  add custom local emulation or Floci-specific branches to application code —
  configure Floci with environment variables instead.
- Do not deploy from a local machine, and do not run Lambda functions on real
  AWS; deployment happens via GitHub Actions unless use asks explicitly to deploy to prod from local
- Never commit secrets or `.env*` files.
- Do not edit generated files (`dist/`, `node_modules/`, `.terraform/`).
- One primary action per page. Render each primary CTA (e.g. "New Knowledge
  Base") in exactly one place — the page header (`PageHeader` `action`). Do not
  duplicate the same action in empty states, cards, or secondary sections;
  empty states should point to the existing header action instead.

## Do not touch

<!-- Paths agents must never modify. -->

# AGENTS.md

Context and rules for AI coding agents working in this repository.
Edit this file freely — opencode loads it automatically as project context.

## Project

`get1agent` monorepo.

```
frontend/              React + TypeScript + Tailwind (Vite)
backend/
  services/            Lambda apps (user-api, knowledge-mcp, mcp-tester, ingestion-*,
                       web-search, code-interpreter, custom-tools)
  services/dependency-layers/   third-party Lambda layers (base, genai, extra-tools, ml)
  services/integration-tests/   moto + in-memory S3 integration tests
  agents/              AgentCore runtime (agentflow: single-agent; workflow: multi-agent)
  packages/            shared modules: core, data, retrieval, ingestion
infra/                 Terraform, deploy scripts, local Floci stack
```

## Current status

- Bedrock access is not enabled yet. Embeddings and rerank run on **Voyage AI**
  (`EMBED_MODE=voyage` / `RERANK_MODE=voyage`, the defaults everywhere, including
  prod) — do not block on Bedrock. The `bedrock` paths are kept dormant for
  later.

## Architecture

The backend is **serverless with no VPC and no RDS**:

- **DynamoDB** (single table `get1agent`) holds all operational data.
- **S3 Vectors** holds the semantic (embedding) index; **S3 objects** hold the
  keyword (BM25) index, parents, manifests and staged artifacts.
- **No Lambda joins a VPC.** Everything reaches DynamoDB, S3, S3 Vectors and
  Voyage AI over public endpoints.
- The frontend talks to API Gateway only; never directly to DynamoDB or S3
  (uploads use presigned URLs).

### Lambda code layout — package vs dependency layer

Deployables live under `backend/services/` (all Lambda apps, including the
`web-search`/`code-interpreter` MCP servers) and `backend/agents/`. Shared
application code lives once in **`backend/packages/`** as four top-level modules
(`core`, `data`, `retrieval`, `ingestion`) and is **bundled into each Lambda's
zip** (never in a layer):

```
packages/core/       core       auth, mcp_server, mcp_client, storage, json_utils, logging
packages/data/       data       client, keys, repositories/*
packages/retrieval/  retrieval  layout, s3_vectors, term_index, maintenance, embedding/
packages/ingestion/  ingestion  pipeline, chunking, extractors, actions
```

Each app keeps its Lambda entry point as `handler.py` at the app root and the
rest of its code in `src/`; the `Makefile` copies `handler.py`, `src/` and the
shared modules it uses to the zip root and zips it. **Dependency layers carry
only third-party dependencies** — never `core`/`data`/`retrieval`/`ingestion`:

| Layer | Contents | Attached to |
|---|---|---|
| `base` | `tzdata`, `python-dateutil` | user-api, knowledge-mcp, web-search, code-interpreter, custom-tools |
| `genai` | `awslabs.mcp-lambda-handler` (future: strands, AI SDKs) | knowledge-mcp, web-search, code-interpreter, custom-tools |
| `extra-tools` | `pymupdf`, `python-docx`, `openpyxl` | ingestion-extract |
| `ml` | *(future)* torch/transformers/… | *(future)* |

App-local code stays in the app's `src/` package: `src.skills`,
`src.search` (hybrid-search orchestration), `src.service`/`src.exa`, and
`src.guard`/`src.sessions`. Layer membership and per-app packages are
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
| Session (code-interp) | `USER#<userId>` | `CONV#<conversationId>` | — |
| Conversation | `USER#<userId>` | `CHAT#<globalId>` | `byId` (`CHATAGENT#<agentId>`); `byUser` (`CHAT#<updatedAt>#<id>`) |
| Playground session | `USER#<userId>` | `PGSESSION#<sessionId>` | `byUser` (`PGSESSION#<updatedAt>#<id>`) |
| Conversation counter | `COUNTER#conversations` | `#SEQ` | — |
| Run feedback | `USER#<userId>` | `FEEDBACK#<runId>` | — |
| MCP connection | `USER#<userId>` | `MCPCONN#<connId>` | — |
| MCP OAuth state | `USER#<userId>` | `MCPSTATE#<state>` | — (TTL, single-use) |
| Eval run | `USER#<userId>` | `EVALRUN#<runId>` | `byUser` (`EVALRUN#<updatedAt>#<id>`) |
| Eval case result | `EVALRUN#<runId>` | `CASE#<caseId>` | — |
| Support ticket | `USER#<userId>` | `SUPPORT#<ticketId>` | `byStatus` (`SUPPORT#all`) |
| Support message | `SUPPORT#<ticketId>` | `MSG#<createdAt>#<seq>` | — |
| Security report | `USER#<userId>` | `SREPORT#<reportId>` | `byStatus` (`SREPORT#all`) |

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
  → `ingestion-mark-failed`). Each stage is its own Lambda.
- **3 stages**: `ingestion-extract` downloads + parses + **chunks** (writes
  `derived/` + `chunks.json`); `ingestion-embed` reads `chunks.json`, calls
  Voyage (or Ollama locally), writes `embeddings.json`; `ingestion-index` writes
  vectors (S3 Vectors / local), parent objects, term postings, catalog, stats and
  the manifest, then sets `documents.status=ready`.
- The pipeline lives in the `ingestion` package
  (`backend/packages/ingestion/`, import `ingestion.*`); each
  `ingestion-*` Lambda is a thin handler that calls one stage action. Embedding
  config/clients live in `retrieval.embedding`. Heavy extractor deps
  (`pymupdf`, `python-docx`, `openpyxl`) ship in the `extra-tools` layer.
- Embeddings: selected by `EMBED_MODE` — **Voyage AI** (`voyage`, the default
  everywhere: `VOYAGE_TEXT_MODEL` default `voyage-4-large`,
  `VOYAGE_MULTIMODAL_MODEL` default `voyage-multimodal-3.5`, key in
  `VOYAGE_API_KEY`). Voyage embeds text and images (`/embeddings` +
  `/multimodalembeddings`, batched, `input_type` `document` for ingestion and
  `query` at search time). Ollama `mxbai-embed-large` (`local`) is the offline
  fallback; **Titan** (`bedrock`) is dormant until Bedrock access is added. Image
  embeddings are computed but not searched.
- Ingestion config (embedding model + chunk size/overlap) is **per knowledge
  base**, set at creation (`knowledge_bases` columns); the page-level "Workspace
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
- **Rerank is opt-in** (`rerank: true`) and never runs unless requested.
  `RERANK_MODE=voyage` (the default) calls the Voyage rerank API
  (`VOYAGE_RERANK_MODEL` default `rerank-3`); `RERANK_MODE=local` calls a
  HuggingFace TEI cross-encoder (`reranker` container, `POST /rerank`);
  `RERANK_MODE=bedrock` uses Bedrock Rerank (`amazon.rerank-v1:0`, `us-west-2`)
  once Bedrock access is added; `none` skips it. If the reranker is unreachable
  the RRF order is returned instead of failing.
- **Identity is passed in the event** (`userId`, the internal UUID) for direct
  invokes, or resolved from the JWT `sub` for HTTP (via the `SUB#<sub>` item).
- **Each MCP server is its own Lambda** (`awslabs.mcp-lambda-handler`,
  stateless) exposing its tools over its own `POST /mcp…` route behind the Auth0
  JWT authorizer, plus the direct Lambda invoke transport. `knowledge-mcp` owns
  the knowledge tools (`POST /mcp`), `web-search` owns `web-search`
  (`POST /mcp/web-search`), `code-interpreter` owns `code-interpreter`
  (`POST /mcp/code-interpreter`) and `http-fetch` owns `http-fetch`,
  `list-storage-files` and `read-storage-file` (`POST /mcp/http-fetch`).
- Knowledge base names follow **S3-bucket-style rules** (lowercase letters,
  digits and hyphens; 3–63 chars; must start/end alphanumeric) and are unique
  per user (`uq_knowledge_bases_user_name`); the create handler returns `409` on
  a duplicate. Per-user limits: **30 knowledge bases, 50 files each, 100 MB
  storage** (`packages/data/.../repositories/quotas.py`).

### Caching (embeddings + knowledge search)

- A best-effort cache lives in **`core.cache`**
  (`backend/packages/core/cache.py`), default backend **Upstash Redis over
  REST** (`CACHE_BACKEND=redis`, `UPSTASH_REDIS_REST_URL`,
  `UPSTASH_REDIS_REST_TOKEN`) — no VPC, no connection pool, stdlib `urllib`.
  Missing credentials (or `CACHE_BACKEND=none`) makes every call a no-op, and all
  operations swallow errors so the cache can never break a request. Keys are
  `g1a:<kind>:<sha256(parts)>`; per-kind TTLs come from
  `CACHE_<KIND>_TTL_SECONDS` (`CACHE_SEARCH_TTL_SECONDS` 300,
  `CACHE_EMBEDDING_TTL_SECONDS` 2592000).
- It is used on the **normal request path only** — never in the Labs:
  - `retrieval.embedding.embeddings.embed_texts` caches vectors keyed by
    `(embed_mode, model, input_type, text)`; embeddings are deterministic, cached
    vectors are read/written in batches, and only misses hit
    Voyage/Ollama/Bedrock.
  - `knowledge-mcp` caches the whole search payload keyed by
    `(userId, query, kbNames, tags, rerank, topK, maxPerDocument)` so a repeated
    question skips embed + search + rerank (per-user scope; short TTL).
  - **Semantic cache** (`core.semantic_cache`): a near-duplicate query reuses the
    cached search payload. It uses **Upstash Vector** (a separate serverless
    vector DB — Upstash Redis has no RediSearch vector search) as the ANN index,
    in a **namespace per user**, and stores the payload in the vector's raw
    `data` field with `expiresAt` + a hard `kb` filter in metadata. A hit
    requires cosine score ≥ `SEMANTIC_CACHE_THRESHOLD` (0.95), a non-expired
    entry, and the same knowledge-base set. Flow in `knowledge-mcp._search`:
    exact cache → embed → semantic lookup → real search → store exact + semantic.
    Env: `UPSTASH_VECTOR_REST_URL`/`UPSTASH_VECTOR_REST_TOKEN`,
    `SEMANTIC_CACHE_ENABLED`, `SEMANTIC_CACHE_THRESHOLD`,
    `SEMANTIC_CACHE_TTL_SECONDS` (600), `SEMANTIC_CACHE_MAX_BYTES` (200000).
    Stale vectors are ignored via `expiresAt` (Upstash Vector has no native TTL).
- **Single-flight** (`core.singleflight`, same Upstash REST client, fails open):
  the knowledge search path is wrapped in a **`SET NX` lock** so N concurrent
  identical requests compute once and the rest wait for the cached result. This
  is cost deduplication — **not** rate limiting (rate limiting lives at the API
  Gateway). Env: `SINGLE_FLIGHT_ENABLED` (default true),
  `SINGLE_FLIGHT_LOCK_SECONDS` (20), `SINGLE_FLIGHT_WAIT_SECONDS` (6).
- **API Gateway throttling** (coarse, common to all clients): the HTTP API has a
  stage-level default (`stage_throttle_burst_limit` / `stage_throttle_rate_limit`,
  defaults 100 / 50) plus per-route overrides on the heavy MCP routes and
  `/v1/agent-run/session` (`throttle_burst_limit` / `throttle_rate_limit` in
  `lambda_routes`). This is volumetric protection **before** Lambda; per-user
  fairness is `core.ratelimit`.
- **Not cached:** the Playground, Evaluations/judges, and anything with tool
  calls or side effects — Labs must show fresh, uncached output.

### Code interpreter tool

- `code-interpreter` (`backend/services/code-interpreter/`) is its own MCP server
  Lambda (`POST /mcp/code-interpreter`) owning the `code-interpreter` tool. It
  runs LLM-generated Python in **Bedrock AgentCore Code Interpreter** sandboxes
  (`aws.codeinterpreter.v1`, available in `ap-south-1`). It is **outside the
  VPC** (AgentCore + DynamoDB are public endpoints).
- **Guard**: before any AWS call, the guard runs an AST/literal pass blocking
  OS/shell, network/cloud SDKs, dynamic code and heavy ML. `BLOCKED_MODULES`/
  `ALLOWED_MODULES` extend/except the list. Every execution is also prefixed with
  an idempotent `sys.addaudithook` prelude. The microVM remains the real
  isolation boundary.
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
  timeout is 240s; `knowledge-mcp` (and `mcp-tester`) timeouts are 300s so the
  synchronous call chain fits. API Gateway caps HTTP integrations at 30s, so long
  runs must use direct invoke.
- **Local**: `CODE_INTERPRETER_MODE=local` runs the same guard + prelude in an
  isolated subprocess with `resource` limits (Floci does not emulate AgentCore).
  The Playground's `custom-tools` uses the same path via `CUSTOM_TOOLS_MODE=local`.

### Web search tool

- `web-search` (`backend/services/web-search/`) is its own MCP server Lambda
  (`POST /mcp/web-search`) owning the `web-search` tool. It calls the **Exa
  Search API** (`POST https://api.exa.ai/search`). It is **outside the VPC** and
  ships no third-party HTTP client — a stdlib `urllib` client.
- Token-aware defaults: `type=auto`, 5 results (cap 25), `maxAgeHours=24`, and
  **highlights only** (~400 chars each) — full page text is opt-in via
  `text=true`/`textMaxCharacters`. Every content budget is **hard-capped**
  server-side: `textMaxCharacters` ≤ `MAX_TEXT_MAX_CHARACTERS` (8000), a bare
  `text: true` defaults to `DEFAULT_TEXT_MAX_CHARACTERS` (4000),
  `highlightsMaxCharacters` ≤ 2000 and `subpages` ≤ 20 — so a search can never
  flood the agent's context (the runtime also caps tool results independently).
  Deep types can return zero results; the tool retries once with `type=auto`.
- Config: `EXA_API_KEY` (required), `EXA_API_BASE_URL`,
  `WEB_SEARCH_TIMEOUT_SECONDS`, `WEB_SEARCH_MAX_RESULTS`. There is **no local
  emulation branch** — Floci containers reach `api.exa.ai` directly using the
  host `EXA_API_KEY`; set it in `.env`.

### HTTP fetch & storage access tool

- `http-fetch` (`backend/services/http-fetch/`) is its own MCP server Lambda
  (`POST /mcp/http-fetch`, group `mcp-tools`) owning three tools:
  - **`http-fetch`** — fetch a public `http(s)` URL/API endpoint in **trusted
    code** (never the sandbox) and **save the response to the caller's S3
    storage** (`storage/<userId>/<fileId>/<fileName>` + a `STORAGE#` item), so
    it is a first-class Storage file and obeys the 10-file / 30 MB / 100 MB
    limits. It returns the file metadata + a presigned `downloadUrl`, never the
    bytes. Supports HTML, JSON, XML, CSV, text and binary.
  - **`list-storage-files`** — list the caller's stored files (fetched or
    uploaded).
  - **`read-storage-file`** — read one stored file back by id (JSON parsed,
    text decoded, binary base64), capped at `maxChars` (default 20 000).
- **SSRF guard** (`src/fetcher.py`): only `http`/`https`, no embedded
  credentials; the hostname is resolved and **every** address checked against a
  loopback/private/link-local/reserved/metadata denylist; the connection is
  **pinned to the validated IP** while keeping the `Host` header + TLS SNI (so a
  DNS rebind cannot redirect it); redirects are followed manually and
  re-validated; size/time capped. Optional `HTTP_FETCH_ALLOWED_DOMAINS`
  (comma-separated suffix allowlist) hardens prod.
- Identity: HTTP requests resolve the JWT `sub` → internal `userId`
  (`resolve_user_id`); direct invokes carry `userId`. Files are scoped by that
  userId, so one user can never read another's. This is also how the agent
  runtime (and agent-to-agent handoff) accesses uploaded/stored S3 files.
- Config: `HTTP_FETCH_ALLOWED_DOMAINS` (optional), `HTTP_FETCH_TIMEOUT_SECONDS`.
  No local emulation branch — Floci containers reach the public internet
  directly. The Playground's sandboxed custom tools cannot fetch themselves;
  the agent calls `http-fetch`, then `read-storage-file`, and passes the content
  to a custom tool as an argument.

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
  (`backend/services/custom-tools/`, `POST /mcp/custom-tools`, group
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
  subprocess with `CUSTOM_TOOLS_MODE=local` under Floci). The test route
  direct-invokes `custom-tools` (IAM-trusted, no API-Gateway 30s cap); the SPA
  never executes user code.
- **AI generation**: `POST /v1/custom-tools/generate` (and the turn worker above)
  makes one OpenCode Go `/chat/completions` call (`CUSTOM_TOOLS_GENERATOR_MODEL`,
  default `deepseek-v4-flash-vision-exp`) returning `{name, description, code,
  inputSchema, outputSchema}`; the Playground re-sends the current code and last
  test error to iteratively refine it. The synchronous `/generate` route is
  capped at `CUSTOM_TOOLS_GENERATE_TIMEOUT_SECONDS` (25, under the gateway's
  30s); the turn worker uses `CUSTOM_TOOLS_GENERATE_ASYNC_TIMEOUT_SECONDS` (240,
  under user-api's 300s Lambda timeout). `CUSTOM_TOOLS_GENERATE_MAX_TOKENS`
  (32000) must stay large: the model spends up to ~18k hidden reasoning tokens
  **before** the JSON, and a smaller budget is consumed entirely by reasoning
  (`finish_reason=length`, no tool). `CUSTOM_TOOLS_FUNCTION`,
  `OPENCODE_API_KEY`/`OPENCODE_BASE_URL` and these knobs live on **user-api**
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
  servers `code-interpreter`, `web-search` and `http-fetch` are offered to
  everyone;
  knowledge-base tools are internal and never shown. The user's connected,
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
- **`verify` = config dry-run.** The `/verify` endpoint still checks the
  prompt/graph and that every referenced KB/skill/MCP server exists and is
  usable, then stamps `verifiedAt`. There is no model call yet (no agent
  runtime). The builder no longer exposes a **Test run** button; publishing is
  ungated.
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
- **Knowledge rerank is stored, not executed** — the knowledge node's dialog has
  a "Rerank results" toggle that writes `config.knowledgeRerank` (and the node's
  `data.rerank`); the future agent runtime passes it as `rerank: true` when it
  calls the knowledge search tool (which already supports it).
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
  draggable or re-connectable; every link is a static dotted curve. A right-hand
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

- A schedule is `{enabled, cron, timezone}` on an agent/workflow `config` (the
  builder's schedule card / node). Saving mirrors an enabled schedule into the
  registry `data/repositories/schedules.py`
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
  `AGENT_SERVICE_CLIENT_SECRET`, `AUTH0_AUDIENCE`, `AUTH0_TOKEN_URL`. Infra:
  `module "scheduler"` + the `get1agent-prod-scheduler` EventBridge rule in
  `infra/terraform/envs/prod/backend.tf`; Floci creates the function (rule off
  unless `ENABLE_LOCAL_SCHEDULER=true`, since AgentCore isn't emulated locally).
- A scheduled run is one synchronous Lambda invocation (15-minute cap); a run
  longer than that keeps going in AgentCore but its Lambda wait is cut short.

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
- Models: **OpenCode Go** (`OPENCODE_API_KEY`, `OPENCODE_BASE_URL`), or a user's
  **Vault provider** when the agent sets `config.providerSecretId` (the runtime
  decrypts it and calls the user's base URL/key — see the Vault section). Most
  models use the OpenAI-compatible `/chat/completions` via Strands `OpenAIModel`;
  `gpt-5.6-luna` is served through the Responses API via Strands
  `OpenAIResponsesModel` (see `RESPONSES_MODELS`). Go requires a descriptive user
  agent and a stable `x-opencode-session` header on every request (sent by
  `agentflow/models.py`). The builder dropdown offers six curated cheap/strong Go
  models (see `AGENT_MODELS` / `SUPPORTED_AGENT_MODELS`): `mimo-v2.5`,
  `glm-5.3-flash`, `qwen3.8-flash`, `deepseek-v4-flash-vision-exp`,
  `gpt-5.6-luna`, `kimi-k2.6`.
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
  (same set as the `extra-tools` Lambda layer). A run payload may override
  `knowledgeBaseIds`/`skillIds`/`servers`/`fileIds` per run; an empty list means
  "none selected".
- **Sessions** persist in S3 (`S3SessionManager`, prefix
  `agent-sessions/<userId>/<agentId>/`). **User memory** is a custom Strands
  `MemoryStore` (`src/memory.py`) over DynamoDB items (`USER#<userId>` /
  `MEM#<agentId>#<memId>`) + S3 Vectors (`status="memory"`, so it never leaks
  into KB search) + Voyage embeddings.
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
  citation scrolls to its source). The model builds
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
  `agent_worker_image_uri`. Needs the `OPENCODE_API_KEY` repo secret
  (`TF_VAR_opencode_api_key`); the runtime/proxy are gated off until an image URI
  is supplied.
- **Tracing: Langfuse, not X-Ray.** The runtime's traces go to **Langfuse** over
  OTLP. The Langfuse SDK owns the OpenTelemetry provider (`agentflow/observability.py`,
  initialised in `main.py` *before* `BedrockAgentCoreApp()`), so Strands'
  auto-instrumented spans (agent loop, generations, tool calls) attach to it;
  `run_trace` in `run.py` wraps each run in one root observation enriched with
  `user_id` (internal userId), `session_id` (conversationId), tags (agent/model)
  and metadata, and flushes at the end. AgentCore's own ADOT exporter is turned
  off with `DISABLE_ADOT_OBSERVABILITY=true` so spans are not double-exported.
  Config is opt-in via `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`/
  `LANGFUSE_BASE_URL` (no-op without keys; `LANGFUSE_BASE_URL` must contain
  "langfuse" so Strands emits Langfuse-friendly attributes), set from the
  `TF_VAR_langfuse_*` repo secrets. Traces are **not sampled** — every run is
  exported. The runtime's `XRay` IAM statement is unused once Langfuse is on.
- **Trace links.** Each run marks its trace public and stores its `traceId` +
  Langfuse `traceUrl` on the persisted turn (S3 transcript) and the conversation
  item (`lastTraceId`/`lastTraceUrl`). The public flag is stamped on **every**
  span by a custom OTEL span processor (`_install_public_processor`), because
  Langfuse only honors `langfuse.trace.public` from the observation it ingests
  first — our root ends last, so a child arriving before it would otherwise leave
  the trace private (and its IO would render empty in the public view).
  `user-api` never hands out the permanent public URL: it signs it into a
  **30-minute expiring link** (`TRACE_LINK_SECRET`, HMAC-SHA256) returned as a
  relative `traceUrl` on turns (`GET /v1/conversations/{id}`) and runs (`GET
  /v1/agents/{id}/runs` → `lastTraceUrl`). The **unauthenticated** `GET
  /v1/traces/{token}` route verifies the signature + expiry and 302-redirects to
  the Langfuse trace (410 once expired). The chat shows a "View trace" link under
  each answer and the builder History shows one per run.
- **Run feedback.** Every run can be rated (thumbs up/down) with an optional
  details dialog (predefined reasons per sentiment + free text). One small item
  per run (`USER#<userId>` / `FEEDBACK#<runId>`; `data/repositories/feedback.py`),
  addressed by the run id so it works identically in the chat and the builder
  History. `PUT /v1/feedback/{runId}` upserts (an empty `value` clears it), and
  the API mirrors it to Langfuse as a `user-feedback` score on the run's trace
  (best-effort, via `LANGFUSE_*`). Feedback is returned with conversation turns
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
- **Admin routes** (in `mcp-tester`, admin view): `GET /v1/admin/support`,
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

### Vault (encrypted user secrets)

- The **Vault** (`frontend/src/pages/VaultPage.tsx`, route `/vault`, sidebar
  section `manage`) stores a user's secrets — OpenAI-compatible provider keys
  (OpenAI/OpenCode/OpenRouter/Gemini/Groq/DeepSeek/Mistral/Together/xAI/
  Fireworks/Perplexity/Ollama/`custom`), MCP API keys, or any generic
  token/connection string. CRUD lives in **`user-api`**; backend test client is
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
  `VAULT_ALLOW_PRIVATE_URLS=true` (set locally so Ollama works; prod false).
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
  `budgetMicroUsd`, `spentMicroUsd`, `platformTokensIn/Out`, `platformRuns`, and
  `unlimited` (an optional manual override, default off, toggled from the admin
  console). A deliberate override stamps `unlimitedSetAt`; a `true` without it is
  a stale flag from the old "admins are unlimited" rule and is cleared once on
  the next login sync. Access via `data.repositories.quotas`
  (`get_budget`/`check_budget`/`charge_usage`/`set_budget_credits`/`set_unlimited`/`reset_spend`).
- **Admins grant credits** from the admin console (`/admin/users`, "AI Credits"):
  `GET /v1/admin/users` (a GSI3 `USERS#all` page — never a Scan),
  `POST /v1/admin/users/{userId}/credits` and `.../reset`, plus
  `POST /v1/admin/users/{userId}/unlimited` (`{unlimited: bool}`) to set or clear
  the override, served by the **`mcp-tester`** admin Lambda. Admins start on the
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
  per-trace view is Langfuse and is not shown in-app.

### Prompt Playground (trace replay)

- The **Playground** (`frontend/src/pages/PlaygroundPage.tsx`, route
  `/playground`, sidebar section `labs`) replays a real LLM call. It is opened
  from a trace row's **Replay** action on the **Traces page**
  (`/playground?trace=<traceId>`); the trace's **generation** observations are
  loaded from `GET /v1/lab/traces/{traceId}` and the first (or `?generation=`)
  one has its messages and model lifted into an editable prompt. Edit any
  message, change model/temperature/max tokens, and **Run**.
- `POST /v1/lab/playground/run` takes one prompt spec or a `runs[]` array (A/B
  up to 4 models, executed in parallel) and makes one OpenCode Go
  `/chat/completions` call per run (`src/evals/playground.py`), returning
  `{results: [{ok, model, output, usage, latencyMs}]}`; the UI shows the original
  trace output and each replay side by side. Models are limited to
  `PLAYGROUND_MODELS` (chat-completions only; the Responses-API model is
  excluded).
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
- **Datasets and their cases are Langfuse-native** (one item per case): a
  dataset is a Langfuse dataset named `u_<userId>/<name>` (lowercase-hyphen,
  ≤48 chars) and a case is a Langfuse dataset item with `input = {question}`,
  optional `expectedOutput`, and `metadata.expectedSources`. A **run**
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
  `GET /v1/evals/datasets/{id}/runs` (the Langfuse experiment runs that used the
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
  Ragas/Langfuse convention): deterministic `context_recall`,
  `context_precision`, `hit_rate`, `mrr` when the case declares expected
  sources; the LLM judge runs **in user-api** (not in Langfuse) with **one
  focused call per metric** — Ragas-aligned `faithfulness` (the answer is
  decomposed into atomic claims; score = supported / total) and
  `context_relevance` (every retrieved passage labelled relevant; score =
  relevant / total), plus `answer_relevance`, and `answer_correctness` when an
  expected answer exists. The unsupported claims and passage labels are kept in
  the S3 artifact and shown in the run's case detail (explainability). Ground
  truth is **optional per case** — metrics light up only when their inputs are
  present. Judges return strict JSON via OpenCode Go (`EVAL_ANSWER_MODEL` /
  `EVAL_JUDGE_MODEL`, defaults `deepseek-v4-flash-vision-exp`); scores are then
  pushed to Langfuse.
- A run stops persisting before the 300s Lambda timeout
  (`EVAL_RUN_BUDGET_SECONDS`, default 260) and marks remaining cases `skipped`.
  `user-api` now direct-invokes `knowledge-mcp`, so its role needs that
  `lambda:InvokeFunction` grant (`lambda_invoke_arns`).
- **Runs are Langfuse experiments**: the background worker loads the dataset's
  items from Langfuse and, per evaluated case, ingests one item trace via
  **OTLP/HTTP** (`POST /api/public/otel/v1/traces`) carrying the documented
  `langfuse.experiment.*` attributes (`experiment.id/name/dataset.id`,
  `experiment.item.id/root_observation_id/expected_output`) plus the observation
  input/output, then attaches the metric scores to that trace/observation
  (`POST /api/public/scores`). Datasets, experiment runs, traces and scores
  therefore all live in Langfuse; DynamoDB/S3 keep only the UI's run status,
  per-case results and artifacts. Raw `urllib`, no `langfuse` package in
  user-api; ingestion is best-effort (a Langfuse outage never fails a run).
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
  `AGENT_SERVICE_CLIENT_SECRET`, `AUTH0_AUDIENCE`, `AUTH0_TOKEN_URL` (defaults
  to `https://<auth0_domain>/oauth/token`); the agent runtime gets
  `SERVICE_AUTH_CLIENT_ID`. Auth0 setup: one Machine-to-Machine app authorised
  for the API audience, then set the TF vars.

#### Langfuse-native curation (traces page, datasets, annotation queues)

- The **curation** layer is Langfuse-native (option "one shared project, users
  never see Langfuse"): `user-api` proxies the Langfuse public API under
  **`/v1/lab/*`** using the same basic-auth helper as the score mirror. Every
  dataset / annotation-queue / score-config name is namespaced
  **`u_<userId>/<name>`**, and list endpoints filter to that prefix, so a user
  can only ever read or write their own objects even though the project is
  shared. Trace ids are Langfuse trace ids.
- **Traces page** (`frontend/src/pages/TracesPage.tsx`, route `/traces`, sidebar
  `labs`) is the only place a trace can be **added to a dataset or an annotation
  queue** — there are no such actions on the chat, builder, or evaluations
  screens. It lists the caller's traces (`GET /v1/lab/traces` →
  `GET /api/public/v2/traces?userId=<userId>`, with our own `eval*` traces
  hidden) and offers **Dataset** / **Queue** actions per row.
- Routes: `GET /v1/lab/traces`; `POST /v1/lab/traces/{traceId}/dataset`
  (creates a `dataset-item` with `sourceTraceId` + a deterministic item id so
  re-adding upserts); `POST /v1/lab/traces/{traceId}/queue` (ownership-checked,
  then `annotation-queues/{id}/items` with `objectType=TRACE`);
  `GET/POST /v1/lab/datasets`; `GET/POST /v1/lab/queues`; `GET/POST
  /v1/lab/score-configs`. All best-effort reads return `configured: false` when
  Langfuse is unset so the page shows a clean empty state.
- **Review queues work without Langfuse logins**: `GET
  /v1/lab/queues/{queueId}/items` (pending items), `GET
  /v1/lab/traces/{traceId}` (the full trace for rendering), and `POST
  /v1/lab/queues/{queueId}/items/{itemId}` (writes scores to the item's trace —
  categorical/boolean/text via `stringValue`, numeric via `value` — and
  optionally completes the item). Score configs are created or selected in the
  add-to-queue dialog, and the Traces page's **Review queues** tab opens the
  review surface (`QueueReviewDialog`).
- **Metrics page** (`frontend/src/pages/MetricsPage.tsx`, route `/metrics`) is
  populated from the Langfuse **v2 Metrics API** via `GET /v1/lab/metrics`
  (`GET /api/public/v2/metrics` with one `query` JSON). Observations scoped to
  the caller's `userId` + `isRootObservation=true` yield trace count, avg/p95
  latency, cost and total tokens (a daily series + totals), plus a per-model
  breakdown (`models[]`, grouped by `providedModelName`/`model`); a
  `scores-numeric` view yields per-score averages. `userId` is filter-only (not
  groupable) — the API forbids grouping by high-cardinality dimensions.
  Token/score/model queries are best-effort (measure/dimension names vary by
  version; a failed probe just yields an empty list).
- **Usage page** (`frontend/src/pages/UsagePage.tsx`, route `/usage`, sidebar
  `manage`) is the workspace-wide live view: the 30-day run/token/cost/latency
  KPIs and the per-model breakdown come from the same `/v1/lab/metrics` route
  (`configured:false` degrades to a "needs Langfuse" note), the **provider keys**
  card reads the real Vault (masked, with per-key use counts + test status and a
  Manage link), and the **Resources** tab aggregates the real limits already
  returned by `/v1/knowledge-bases`, `/v1/storage/files`, `/v1/agents`,
  `/v1/workflows`, `/v1/agent-skills`, `/v1/mcp/connections` and
  `/v1/vault/secrets`. There is **no billing/credit backend**, so no invoice or
  balance data is fabricated — every number on the page is server-derived.
- **`user-api` now receives the Langfuse env in prod** (`LANGFUSE_PUBLIC_KEY` /
  `LANGFUSE_SECRET_KEY` / `LANGFUSE_BASE_URL`) **and `TRACE_LINK_SECRET`** —
  these were previously only on the agent runtime, so trace links and score
  mirroring were dark in prod. Floci already had them.
- The eval lab is fully Langfuse-native today: datasets + items in Langfuse,
  runs ingested as Langfuse experiments (OTLP), scores attached to item traces.
  The worker can run either the RAG task or a saved **agent** end to end (service
  auth, above). Reading run aggregates straight from Langfuse (instead of our
  own run item) remains an optional future simplification.

### Remote MCP servers & connections

- `mcp-connections` (`backend/services/mcp-connections/`) is the **OAuth broker
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
  callback `<api>/v1/mcp/oauth/callback` and set `GITHUB_MCP_CLIENT_ID` /
  `GITHUB_MCP_CLIENT_SECRET`.
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
  - `require_admin` (admin view): `mcp-tester`.
  - No header → falls back to `admin` if the token has the admin role, else
    `user`.
- Admin code is kept separate: frontend UI under `frontend/src/admin/`, backend
  Lambda under `backend/services/mcp-tester/`.
- **`mcp-tester`** (`GET /v1/admin/mcp/tools`, `POST /v1/admin/mcp/call`) is the
  MCP *client*: it reads the admin claim + `sub`, resolves the caller's internal
  `userId`, builds MCP JSON-RPC, and invokes every MCP server in `MCP_FUNCTIONS`
  over their direct-invoke transports, merging their tool lists and routing each
  call to the owning server. It also serves the admin **AI-credit** routes
  (`GET /v1/admin/users`, `POST /v1/admin/users/{userId}/{credits|reset}`) — see
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

- API base URL: `http://get1agent.execute-api.localhost.floci.io:4566`
  (`localhost.floci.io` resolves to 127.0.0.1 on the host, and Floci's embedded
  DNS resolves it inside Lambda containers, so presigned S3 URLs work from both).
- Point the UI at it via the Vite dev proxy:
  `printf 'VITE_API_URL=/\nVITE_API_PROXY_TARGET=http://get1agent.execute-api.localhost.floci.io:4566\n' > frontend/.env.local`
- Auth: the HTTP API uses a JWT authorizer against the real Auth0 issuer, so the
  Floci container needs network access to `https://get1agent.us.auth0.com/`.
- Compose file: `infra/local/floci/docker-compose.yml`. Host env: the root
  `.env` (from `infra/local/floci/env.example`).
- `infra/local/floci/init/ready.d/10-provision.py` mirrors Terraform: DynamoDB
  table + GSIs, bucket + EventBridge notification (`raw/` prefix) → rule → SQS +
  DLQ → dispatcher → state machine → workers, plus the HTTP API + JWT authorizer
  + routes from `infra/terraform/envs/prod/api_gateway.tf`.
- The state machine definition is the same file Terraform deploys:
  `infra/terraform/modules/ingestion/statemachine.asl.json`.
- Ingestion runs with `EMBED_MODE=voyage` (the default): set `VOYAGE_API_KEY` in
  `.env` and the Floci Lambda containers reach `api.voyageai.com` directly. Set
  `EMBED_MODE=local` to embed offline with the Ollama container
  (`mxbai-embed-large`, pulled by `make floci`); the Voyage env is then unused
  but harmless.
- Retrieval runs with `VECTOR_STORE=local` (brute-force cosine over
  `index/<userId>/vectors.json`; S3 Vectors is not emulated) and
  `RERANK_MODE=voyage` (Voyage rerank; opt-in per request). Set
  `RERANK_MODE=local` to use the HuggingFace TEI `reranker` container instead;
  `make floci` then starts it and waits for `/health`.
- After changing Lambda code: `make floci-build` then `make floci-up`
  (provisioning is re-run on every boot), or `make floci-reload`.
- Local OAuth for remote MCP servers: providers reject plaintext-HTTP redirect
  URIs unless loopback, and Floci only serves the API on its own host. Run
  `make floci-oauth-proxy` (a stdlib loopback forwarder) and set
  `MCP_OAUTH_REDIRECT_URI=http://127.0.0.1:8765/v1/mcp/oauth/callback`.

### Migrations

None. There is no SQL database and no migration tooling — DynamoDB schemas are
created by Terraform (`infra/terraform/modules/dynamodb`) and by the Floci init
hook locally. Adding an attribute or GSI is a code/Terraform change, not a
migration.

## Commands

- Frontend: `npm run dev`, `npm run lint`, `npm run build`
- Backend tests: `make test` — integration tests in `backend/services/integration-tests/` using
  `moto` (DynamoDB) + an in-memory S3 double. No Docker, no AWS. Run a single
  file with `cd backend/services/integration-tests && uv run pytest test_search.py`.
- Per-lambda unit tests: `make test-unit` (or `make -C backend/services/web-search test`)
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

# AGENTS.md

Context and rules for AI coding agents working in this repository.
Edit this file freely — opencode loads it automatically as project context.

## Project

`get1agent` monorepo.

```
frontend/              React + TypeScript + Tailwind (Vite)
backend/
  services/            Lambda apps (user-api, knowledge-mcp, mcp-tester, ingestion-*,
                       web-search, code-interpreter)
  services/dependency-layers/   third-party Lambda layers (base, genai, extra-tools, ml)
  services/integration-tests/   moto + in-memory S3 integration tests
  agents/              AgentCore runtime (agentflow: single-agent; workflow later)
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
| `base` | `tzdata`, `python-dateutil` | user-api, knowledge-mcp, web-search, code-interpreter |
| `genai` | `awslabs.mcp-lambda-handler` (future: strands, AI SDKs) | knowledge-mcp, web-search, code-interpreter |
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
| Agent | `USER#<userId>` | `AGENT#<lowerName>` | `byId`; `byUser`; `byStatus` (`AGENTLIB#public`) |
| Storage file | `USER#<userId>` | `STORAGE#<fileId>` | — |
| Session (code-interp) | `USER#<userId>` | `CONV#<conversationId>` | — |
| Conversation | `USER#<userId>` | `CHAT#<globalId>` | `byId` (`CHATAGENT#<agentId>`); `byUser` (`CHAT#<updatedAt>#<id>`) |
| Conversation counter | `COUNTER#conversations` | `#SEQ` | — |
| MCP connection | `USER#<userId>` | `MCPCONN#<connId>` | — |
| MCP OAuth state | `USER#<userId>` | `MCPSTATE#<state>` | — (TTL, single-use) |

- **GSI1 `byId`** resolves a KB/document/skill/agent by UUID.
- **GSI2 `byUser`** lists a user's KBs/skills/agents/tags by prefix.
- **GSI3 `byStatus`** serves the watchdog (`DOCSTATUS#processing`), the recent
  events feed (`USER#<userId>#EVENT`) and the public agent library
  (`AGENTLIB#public`).
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
  (`POST /mcp/web-search`) and `code-interpreter` owns `code-interpreter`
  (`POST /mcp/code-interpreter`).
- Knowledge base names follow **S3-bucket-style rules** (lowercase letters,
  digits and hyphens; 3–63 chars; must start/end alphanumeric) and are unique
  per user (`uq_knowledge_bases_user_name`); the create handler returns `409` on
  a duplicate. Per-user limits: **30 knowledge bases, 50 files each, 100 MB
  storage** (`packages/data/.../repositories/quotas.py`).

### Code interpreter tool

- `code-interpreter` (`backend/services/code-interpreter/`) is its own MCP server
  Lambda (`POST /mcp/code-interpreter`) owning the `code-interpreter` tool. It
  runs LLM-generated Python in **Bedrock AgentCore Code Interpreter** sandboxes
  (`aws.codeinterpreter.v1`, available in `ap-south-1`). It is **outside the
  VPC** (AgentCore + DynamoDB are public endpoints).
- **Guard**: before any AWS call, `guard.py` runs an AST/literal pass blocking
  OS/shell, network/cloud SDKs, dynamic code and heavy ML. `BLOCKED_MODULES`/
  `ALLOWED_MODULES` extend/except the list. Every execution is also prefixed with
  an idempotent `sys.addaudithook` prelude. The microVM remains the real
  isolation boundary.
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

### Web search tool

- `web-search` (`backend/services/web-search/`) is its own MCP server Lambda
  (`POST /mcp/web-search`) owning the `web-search` tool. It calls the **Exa
  Search API** (`POST https://api.exa.ai/search`). It is **outside the VPC** and
  ships no third-party HTTP client — a stdlib `urllib` client.
- Token-aware defaults: `type=auto`, 5 results (cap 25), `maxAgeHours=24`, and
  **highlights only** (~400 chars each) — full page text is opt-in via
  `text=true`/`textMaxCharacters` (default 4000) so a search cannot flood the
  agent's context. Deep types can return zero results;
  the tool retries once with `type=auto`.
- Config: `EXA_API_KEY` (required), `EXA_API_BASE_URL`,
  `WEB_SEARCH_TIMEOUT_SECONDS`, `WEB_SEARCH_MAX_RESULTS`. There is **no local
  emulation branch** — Floci containers reach `api.exa.ai` directly using the
  host `EXA_API_KEY`; set it in `.env`.

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
  servers `code-interpreter` and `web-search` are offered to everyone;
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
  prompt, model, reasoning, output format, the referenced KB/skill/MCP ids, an
  optional schedule and the node/edge **graph**. KBs/skills/servers are stored
  by id, never embedded. Limits: **50 agents/user**, 256 KB config; names are
  lowercase-hyphen (1–64) and unique per user.
- Routes: `GET/POST /v1/agents`, `GET/PUT/DELETE /v1/agents/{id}`,
  `POST /v1/agents/{id}/verify`, `POST /v1/agents/{id}/publish`,
  `POST /v1/agents/{id}/unpublish`, `GET /v1/agents/library`,
  `POST /v1/agents/library/{id}/install`.
- **Test run = config dry-run.** `verify` checks the prompt/graph and that every
  referenced KB/skill/MCP server still exists and is usable, then stamps
  `verifiedAt`. There is no model call yet (no agent runtime). **Editing resets
  verification and unpublishes** — a verified flag is a promise about an exact
  configuration.
- **Publish to library** requires `verifiedAt`; it flips `visibility=public` and
  projects the agent onto GSI3 under `AGENTLIB#public` (`<publishedAt>#<agentId>`)
  so the library lists globally without a Scan. `install` clones a published
  agent into the caller's workspace with `source="library"` + `forkedFrom`, and
  strips owner-scoped references (KBs/skills/remote servers) since those are not
  shareable.
- **Schedule is stored, not executed** — the builder's schedule node writes
  `config.schedule` (`enabled`, `cron`, `timezone`); there is no scheduler
  engine yet.
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
  all options (agent prompt/model, the full KB/skill lists, per-MCP tool
  selection, custom cron, the full input message and output instructions). The
  **input card** also takes an optional **starter-questions** list
  (`config.defaultQuestions`, max 8) that the chat screen surfaces as one-tap
  prompts. Cards
  are **permanent and fixed** — equal size, no palette, no delete, and not
  draggable or re-connectable; every link is a static dotted curve. A right-hand
  **Agent** panel with **Response / History / Errors** tabs is the **run log** —
  it records agent run/test activity (test-run results, warnings, and
  save/publish/load milestones), never on-screen config edits. Edits autosave to
  localStorage; Save writes the config to DynamoDB.
  Selecting a skill auto-adds the MCP servers it declares. The library UI is
  `AgentStorePage.tsx`.

### Agent runtime (AgentCore + Strands)

- The runtime lives in **`backend/agents/`** — an **AgentCore Runtime container**
  (ARM64, port 8080, `POST /invocations` SSE + `GET /ping`) built on
  `BedrockAgentCoreApp`; the single-agent path is the **`agentflow/`** package
  (`main.py` dispatches on the payload). It is **not** a Lambda zip; `agents/` is
  excluded from the Lambda build. Multi-agent workflow orchestration (ordered
  pipeline + swarm) will be a sibling package.
- Invocation: the SPA calls a public **Function URL** (`backend/services/agent-run`,
  `InvokeMode=RESPONSE_STREAM`) which forwards the Auth0 `Authorization` header
  and body to the runtime and pipes SSE back. The runtime is configured with a
  **custom JWT authorizer** (Auth0 discovery URL + audience), so AgentCore
  validates the token; the entrypoint only decodes the verified `sub` → internal
  `userId` (`SUB#<sub>`), then loads `USER#<userId>` / `AGENT#<name>` and checks
  ownership. Local dev may pass `userId` in the payload.
- Models: **OpenCode Go** (`OPENCODE_API_KEY`, `OPENCODE_BASE_URL`). Most models
  use the OpenAI-compatible `/chat/completions` via Strands `OpenAIModel`;
  `gpt-5.6-luna` is served through the Responses API via Strands
  `OpenAIResponsesModel` (see `RESPONSES_MODELS`). Go requires a descriptive user
  agent and a stable `x-opencode-session` header on every request (sent by
  `agentflow/models.py`). The builder dropdown offers six curated cheap/strong Go
  models (see `AGENT_MODELS` / `SUPPORTED_AGENT_MODELS`): `mimo-v2.5`,
  `glm-5.3-flash`, `qwen3.8-flash`, `deepseek-v4-flash-vision-exp`,
  `gpt-5.6-luna`, `kimi-k2.6`.
- The runtime reads the **canonical `config`** (flat `prompt/model/input/output/
  knowledgeBaseIds/knowledgeRerank/skillIds/servers/memory` + `graph` for the UI)
  and builds tools from the MCP servers (built-ins via `core.mcp_client`, remote
  via the aggregator), the knowledge server's **real tools under their exact
  names** (`get-user-knowledge-bases` + `search-user-knowledge-bases`, scoped to
  the agent's attached KBs), and
  injects skills into the system prompt. `_make_tool` preserves hyphens in tool
  names (only characters the model API rejects are sanitized).
- **Sessions** persist in S3 (`S3SessionManager`, prefix
  `agent-sessions/<userId>/<agentId>/`). **User memory** is a custom Strands
  `MemoryStore` (`src/memory.py`) over DynamoDB items (`USER#<userId>` /
  `MEM#<agentId>#<memId>`) + S3 Vectors (`status="memory"`, so it never leaks
  into KB search) + Voyage embeddings.
- **Context management.** Every run restores the conversation's message history
  from the session and passes the **full text history** (user/assistant turns,
  capped to the last `AGENT_PLANNER_HISTORY_TURNS` = 6 turns) to the planner so
  follow-ups resolve references. Tool results are the dominant context cost, so
  the model is wrapped (`agentflow/context.py`) with a per-call view that
  truncates each **old** tool result to `AGENT_TOOL_RESULT_MAX_CHARS` (1500) and
  keeps the last `AGENT_TOOL_RESULT_KEEP_FULL` (2) intact — knowledge results are
  exempt. The session/transcript keep the full data; only the provider request is
  bounded. The agent uses Strands `SummarizingConversationManager` with proactive
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
  reasoning as a step. The plan is streamed (`plan.started` then
  `plan`) and folded into the agent's input so the run follows it
  (`execution_input`). A planner failure is non-fatal.
  Disable with `AGENT_PLANNER_ENABLED=false`.
- Streaming events are normalized in `agentflow/events.py` to
  `run.started|plan.started|plan|text|tool.start|tool.input|
  tool.stream|tool.result|run.completed|run.error`. Internal reasoning/thinking
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
  used by both the chat screen and the builder. **Test run** stays the config
  dry-run (`/verify`) that gates publishing. Set `VITE_AGENT_RUN_URL` to the
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
  the composer sits at
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
  `GET /v1/agents/{id}/runs`. Chat conversations use the `CHAT#` prefix (the
  code-interpreter already owns `CONV#`).
- Infra: `infra/terraform/modules/agent_runtime` (ECR, runtime role, AgentCore
  runtime, proxy Lambda + Function URL + CORS). Deploy with
  `bash infra/aws/deploy-agent-runtime.sh`: it creates the ECR repo, builds and
  pushes the ARM64 image, then applies the runtime with
  `agent_worker_image_uri`. Needs the `OPENCODE_API_KEY` repo secret
  (`TF_VAR_opencode_api_key`); the runtime/proxy are gated off until an image URI
  is supplied.

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
- **Tokens**: encrypted in the connection item; tool schemas cached in S3.
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
  call to the owning server.

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

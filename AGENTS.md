# AGENTS.md

Context and rules for AI coding agents working in this repository.
Edit this file freely — opencode loads it automatically as project context.

## Project

`get1agent` monorepo.

```
frontend/          React + TypeScript + Tailwind (Vite)
backend/
  services/        Python Lambdas + shared layers (user-api, knowledge-mcp, ingestion-*)
  tools/           MCP server Lambdas (web-search, code-interpreter)
  migrations/      (removed — there is no SQL database)
infra/             Terraform, deploy scripts, local Floci stack
```

## Current status

- Bedrock model quota limits are currently hit; a support ticket has been raised.
  Continue app development against the code we already have (local Floci with
  `EMBED_MODE=local`); do not block on Bedrock.

## Architecture

The backend is **serverless with no VPC and no RDS**:

- **DynamoDB** (single table `get1agent`) holds all operational data.
- **S3 Vectors** holds the semantic (embedding) index; **S3 objects** hold the
  keyword (BM25) index, parents, manifests and staged artifacts.
- **No Lambda joins a VPC.** Everything reaches DynamoDB, S3, S3 Vectors and
  Bedrock over public endpoints.
- The frontend talks to API Gateway only; never directly to DynamoDB or S3
  (uploads use presigned URLs).

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
| Session (code-interp) | `USER#<userId>` | `CONV#<conversationId>` | — |

- **GSI1 `byId`** resolves a KB/document/skill by UUID.
- **GSI2 `byUser`** lists a user's KBs/skills/tags by prefix.
- **GSI3 `byStatus`** serves the watchdog (`DOCSTATUS#processing`) and the recent
  events feed (`USER#<userId>#EVENT`).
- Table is on-demand (`PAY_PER_REQUEST`), TTL attribute `expiresAt`.
- Repository code lives in `backend/services/shared/dynamo/` (`client.py`,
  `keys.py`, `repositories/*`). The internal `userId` is a **short base32 id**
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
  Bedrock (or Ollama locally), writes `embeddings.json`; `ingestion-index` writes
  vectors (S3 Vectors / local), parent objects, term postings, catalog, stats and
  the manifest, then sets `documents.status=ready`.
- Pipeline code is shared in `backend/services/shared/ingestion/` (chunking,
  extractors, embeddings, pipeline). Heavy extractor deps (`pymupdf`,
  `python-docx`, `openpyxl`) ship in the worker zip, **not** the shared layer.
- Embeddings: **Titan Text V2** (`amazon.titan-embed-text-v2:0`) in production,
  Ollama `mxbai-embed-large` locally. Image embeddings are computed but not
  searched.
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
  `shared/ingestion/config.py`), so children fit every embedder window.
- **Rerank is opt-in** (`rerank: true`): Bedrock Rerank
  (`amazon.rerank-v1:0`, `us-west-2`) in production; locally `RERANK_MODE=local`
  calls a HuggingFace TEI cross-encoder (`reranker` container, `POST /rerank`).
  If it is unreachable the RRF order is returned instead of failing.
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
  storage** (`shared/dynamo/repositories/quotas.py`).

### Code interpreter tool

- `code-interpreter` (`backend/tools/code-interpreter/`) is its own MCP server
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

- `web-search` (`backend/tools/web-search/`) is its own MCP server Lambda
  (`POST /mcp/web-search`) owning the `web-search` tool. It calls the **Exa
  Search API** (`POST https://api.exa.ai/search`). It is **outside the VPC** and
  ships no third-party HTTP client — a stdlib `urllib` client.
- Cost-aware defaults: `type=auto`, 10 results (cap 25), `maxAgeHours=24`, and
  highlights + capped page text (4000 chars). Deep types can return zero results;
  the tool retries once with `type=auto`.
- Config: `EXA_API_KEY` (required), `EXA_API_BASE_URL`,
  `WEB_SEARCH_TIMEOUT_SECONDS`, `WEB_SEARCH_MAX_RESULTS`. There is **no local
  emulation branch** — Floci containers reach `api.exa.ai` directly using the
  host `EXA_API_KEY`; set it in `.env`.

### Agent skills

- `agent-skills` CRUD is part of **`user-api`** — a user's reusable skills in the
  **strands format**: YAML frontmatter (`name`, `description`, `allowed-tools`)
  plus a markdown body. Routes: `GET/POST /v1/agent-skills`,
  `GET /v1/agent-skills/tools`, `POST /v1/agent-skills/parse`,
  `GET/PUT/DELETE /v1/agent-skills/{id}`.
- Frontmatter fields are stored in **separate DynamoDB attributes** (`name`,
  `description`, `allowedTools`, `content`) so an agent can list cheap metadata
  and only fetch the full body when a skill applies. No S3 object. Limits:
  **50 skills/user, 100 KB per skill**; names are lowercase-hyphen (1–64) and
  unique per user (the item key `SKILL#<name>`).
- The parse/render/validation logic is shared in `shared/skills/` (data layer,
  no PyYAML). `POST /parse` is what the editor calls when a user uploads a `.md`.
- **allowed-tools** is a multi-select. Built-ins `code-interpreter` and
  `web-search` are offered to everyone; knowledge-base tools are internal and
  never shown.

### Admin console & strict role separation

- **Admin** is an Auth0 role. The Login Action copies `event.authorization.roles`
  onto namespaced custom claims: `https://get1agent.com/roles` and
  `https://get1agent.com/isAdmin`. Assign the `admin` role in Auth0; re-login
  refreshes the tokens.
- Shared role logic lives in the **`ai` Lambda layer**
  (`backend/services/layers/ai/ai/auth.py`): `is_admin_claims`, `require_admin`
  and `require_user`. The layer also holds the thin MCP JSON-RPC client
  (`ai/mcp_client.py`) and the shared MCP transport (`ai/mcp_server.py`).
- **View-based access, enforced server-side** — the frontend is only a UX gate.
  The SPA sends `x-active-view` (`user` | `admin`); the backend validates it
  against the token's real roles:
  - `require_user` (user view): `user-api` and the `knowledge-mcp` **HTTP** path.
    An admin who chose the user view is allowed.
  - `require_admin` (admin view): `mcp-tester`.
  - No header → falls back to `admin` if the token has the admin role, else
    `user`.
- Admin code is kept separate: frontend UI under `frontend/src/admin/`, backend
  Lambda under `backend/services/admin/mcp-tester/`.
- **`mcp-tester`** (`GET /v1/admin/mcp/tools`, `POST /v1/admin/mcp/call`) is the
  MCP *client*: it reads the admin claim + `sub`, resolves the caller's internal
  `userId`, builds MCP JSON-RPC, and invokes every MCP server in `MCP_FUNCTIONS`
  over their direct-invoke transports, merging their tool lists and routing each
  call to the owning server.

## Conventions

### Page loading states

Loading is handled in one place per concern — never hand-roll timers per page.

- **Route entry (all pages):** routes are lazy (`React.lazy` in `App.tsx`) and
  `RouteGate` in `layouts/MainLayout.tsx` shows a page-shaped skeleton only
  while the lazy route chunk loads. The shape comes from
  `components/ui/RouteSkeleton.tsx`. There is no minimum display time.
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
make floci-down       # stop and remove
```

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
- Ingestion runs with `EMBED_MODE=local`: real 1024-dim vectors from an Ollama
  container (`mxbai-embed-large`). `make floci` pulls the model.
- Retrieval runs with `VECTOR_STORE=local` (brute-force cosine over
  `index/<userId>/vectors.json`; S3 Vectors is not emulated) and `RERANK_MODE=local`
  (HuggingFace TEI `reranker`, `POST /rerank`). `make floci` starts it and waits
  for `/health`.
- After changing Lambda code: `make floci-build` then `make floci-up`
  (provisioning is re-run on every boot), or `make floci-reload`.

### Migrations

None. There is no SQL database and no migration tooling — DynamoDB schemas are
created by Terraform (`infra/terraform/modules/dynamodb`) and by the Floci init
hook locally. Adding an attribute or GSI is a code/Terraform change, not a
migration.

## Commands

- Frontend: `npm run dev`, `npm run lint`, `npm run build`
- Backend tests: `make test` — integration tests in `backend/tests/` using
  `moto` (DynamoDB) + an in-memory S3 double. No Docker, no AWS. Run a single
  file with `cd backend/tests && uv run pytest test_search.py`.
- Local Lambdas / infra: see "Local development" above (`make floci-*`).
- Backend Lambdas: `make -C backend/services/<name> package`;
  `bash infra/aws/deploy-backend.sh <name|group> [package|deploy]`. The
  `Backend` workflow deploys by group (`user-apis`, `knowledge-mcp`,
  `admin-apis`, `mcp-tools`, `ingestion-apis`), defined by the `group` field in
  `backend/services/registry.json`.

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
  AWS; deployment happens via GitHub Actions.
- Never commit secrets or `.env*` files.
- Do not edit generated files (`dist/`, `node_modules/`, `.terraform/`).
- One primary action per page. Render each primary CTA (e.g. "New Knowledge
  Base") in exactly one place — the page header (`PageHeader` `action`). Do not
  duplicate the same action in empty states, cards, or secondary sections;
  empty states should point to the existing header action instead.

## Do not touch

<!-- Paths agents must never modify. -->

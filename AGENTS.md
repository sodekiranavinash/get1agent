# AGENTS.md

Context and rules for AI coding agents working in this repository.
Edit this file freely — opencode loads it automatically as project context.

## Project

`get1agent` monorepo.

```
frontend/          React + TypeScript + Tailwind (Vite)
backend/
  services/        Python Lambdas + shared layers (health-check, etc.)
  migrations/      Alembic migrations
infra/             Terraform, deploy scripts, local Floci stack + migrations
```

## Current status

- Bedrock model quota limits are currently hit; a support ticket has been raised.
  Continue app development against the code we already have (local Floci with
  `EMBED_MODE=local`); do not block on Bedrock.

## Architecture

- Frontend talks to API Gateway only; never directly to RDS.
- Lambdas share code via `backend/services/shared/` (bundled into the `data` layer).
- Each lambda is one service; that service's logic lives in its `src/handler.py`.

### Document ingestion

Uploads flow: browser PUTs to S3 via a presigned URL, then calls
`POST /v1/knowledge-bases/{id}/documents/{docId}/complete`.

- **Production**: S3 `ObjectCreated` → EventBridge → SQS
  (`ingestion-docs` + DLQ) → `ingestion-dispatcher` (batch 5, partial batch
  failures) → **Step Functions Standard** (`ingest-{docId}-{eventToken}`) →
  `ingestion-extract` → `ingestion-embed` → `ingestion-index` (any stage failure
  → `ingestion-mark-failed`). Each stage is its own Lambda for per-stage
  memory/timeout/IAM and clear failure visibility. There is no in-process
  ingestion path.
- **VPC split**: `ingestion-extract`, `ingestion-index` and
  `ingestion-mark-failed` run in the VPC because they write RDS; `ingestion-embed`
  and `ingestion-dispatcher` run **outside** the VPC. `ingestion-extract` chunks
  text and stages `chunks.json` in S3 (it owns the per-KB config + timeline);
  `ingestion-embed` reads it, calls Bedrock over the public internet, and writes
  `embeddings.json` back to S3; `ingestion-index` reads that and persists to
  pgvector. Keeping the Bedrock call out of the VPC removes the need for a
  Bedrock interface endpoint (PrivateLink).
- **Local**: the Floci stack runs this exact path; see "Local development".
- Pipeline code is shared: `backend/services/shared/ingestion/` (chunking, extractors,
  embeddings, pipeline). Heavy extractor deps (`pymupdf`, `python-docx`,
  `openpyxl`) ship in the worker zip, **not** the shared layer.
- Embeddings: **Titan Text V2** (`amazon.titan-embed-text-v2:0`) for text chunks
  and **Titan Multimodal G1** (`amazon.titan-embed-image-v1`) for images. They
  are different vector spaces → separate `chunks` and `document_images` tables.
- pgvector runs on the existing RDS; enable via migration `0003_ingestion`.
- Ingestion config (embedding model + chunk size/overlap) is **per knowledge
  base**, set at creation (`knowledge_bases` columns); the page-level
  "Workspace defaults" card only pre-fills the create dialog. Changing it after
  documents exist means re-indexing.
- `ingestion_events` is the append-only timeline the UI reads
  (`GET /v1/knowledge-bases/events`). The worker updates `documents.status`
  (`processing`/`ready`/`failed`) and `knowledge_bases.status` follows.
- The VPC has no NAT: the in-VPC workers reach S3 through the free gateway
  endpoint and RDS over the VPC network. The Bedrock call lives in
  `ingestion-embed`, outside the VPC, so no Bedrock interface endpoint
  (PrivateLink) is needed; the dispatcher is outside the VPC too (it only calls
  Step Functions).

### Ingestion observability

- Workers emit one JSON log line per stage (`shared/observability.py`) with
  `documentId` / `knowledgeBaseId` / `stage`, so CloudWatch Logs Insights can
  query by document: `fields @timestamp, message | filter documentId = "…"`.
- `ingestion_events` is the UI timeline; `documents.status` is the terminal
  state. The UI shows a **Stalled** badge when a document stops advancing.
- A scheduled `ingestion-watchdog` (EventBridge `rate(10 minutes)`, in the VPC)
  fails any document left in `processing` past `STALL_THRESHOLD_MINUTES`
  (default 75), so an aborted execution can never stay silently stuck. The
  threshold exceeds the state machine `TimeoutSeconds` (3600s) so it never races
  a still-running execution.
- No CloudWatch alarms are provisioned (monitoring will live in an admin panel).
- X-Ray (`enable_xray`, default true) traces the ingestion workers + state
  machine. Lambda log retention is 7 days (`log_retention_days`).

### Retrieval & MCP tools

- Two agent tools, plus an internal worker, share code in
  `backend/services/shared/retrieval/` (bundled in the data layer):
  - `get-user-knowledge-bases` (in VPC) — resolves the caller's knowledge bases
    by name/id and returns KBs, documents, and tags. Metadata only, no search.
  - `search-user-knowledge-bases` (**outside** VPC) — embeds the query (Titan V2
    prod / Ollama local), invokes `retrieval-query`, optionally reranks, and
    shapes chunks + sources.
  - `retrieval-query` (in VPC) — internal only; resolves the user + KBs and runs
    hybrid search. Never exposed to the agent.
- **Hybrid search is always on**: a pgvector cosine leg (`chunks.embedding`,
  HNSW) and a Postgres FTS leg (`chunks.content_tsv`, generated `tsvector` +
  GIN) are fused with Reciprocal Rank Fusion, then hydrated with `ts_headline`
  snippets. `documents.status = 'ready'` is always required. The lexical leg
  builds an **OR/prefix** tsquery (`personal:* | project:*`); the default
  `websearch_to_tsquery` ANDs every term and effectively disables the leg for
  natural-language questions.
- **Small-to-big retrieval**: only the small child chunks are embedded and
  searched. Each child points at a `document_parents` row — a PDF source page
  (a huge page becomes several parents sharing the page number), or a
  fixed-size window for non-paginated formats. Results return the parent's full
  `content` for context, the precise `matchedContent` child, and the child's
  highlighted `snippet`; parents are deduplicated per document/page. Default
  child size is **384 tokens** with 64 overlap, so children always fit every
  embedder window (`mxbai-embed-large` truncates past 512).
- **Rerank is opt-in** (`rerank: true`) and uses Bedrock Rerank
  (`amazon.rerank-v1:0`, `us-west-2` — not available in `ap-south-1`) from the
  outside-VPC orchestrator. Locally `RERANK_MODE=local` calls a HuggingFace TEI
  cross-encoder (`reranker` container, `POST /rerank`); if it is unreachable the
  RRF order is returned instead of failing the search.
- **Identity is passed in the event** (`auth0Sub`), not a JWT: the tools are
  invoked directly via `lambda:InvokeFunction` (no API Gateway routes). Only the
  caller's IAM role may invoke them.
- `knowledge-mcp` is the MCP server (`awslabs.mcp-lambda-handler`, stateless)
  exposing both tools over `POST /mcp` behind the Auth0 JWT authorizer, and via
  the direct Lambda invoke transport. It reads `auth0Sub` from the JWT claims
  and forwards it to the tool Lambdas.
- Knowledge base names follow **S3-bucket-style rules** (lowercase letters,
  digits and hyphens; 3–63 chars; must start/end alphanumeric) and are unique
  per user (`uq_knowledge_bases_user_name`); the create handler returns `409` on
  a duplicate. Per-user limits: **30 knowledge bases, 50 files each, 100 MB
  storage** (`shared/models/user_quota.py`, migration `0007_quota_limits`).

### Admin console & strict role separation

- **Admin** is an Auth0 role. The Login Action copies `event.authorization.roles`
  onto namespaced custom claims on both tokens:
  `https://get1agent.com/roles` and `https://get1agent.com/isAdmin`. Assign the
  `admin` role to a user in Auth0; re-login refreshes the tokens.
- Shared role logic lives in the **`ai` Lambda layer**
  (`backend/services/layers/ai/ai/auth.py`): `is_admin_claims`, `require_admin`
  (admin Lambdas) and `require_user` (user Lambdas). The layer also holds the
  thin MCP JSON-RPC client (`ai/mcp_client.py`).
- **View-based access, enforced server-side** — the frontend is only a UX gate.
  A user with several roles (e.g. `admin`) picks a **view** after login; the
  SPA sends it on every request as `x-active-view` (`user` | `admin`), and the
  backend validates it against the token's real roles:
  - `require_user` (user view): `knowledge-bases`, `account-settings`, and the
    `knowledge-mcp` **HTTP** path. An admin who chose the user view is allowed,
    which is how they add data before testing it.
  - `require_admin` (admin view): `mcp-tester`. A normal user can never set the
    admin view.
  - No header → falls back to `admin` if the token has the admin role, else
    `user` (keeps direct invokes/curl working).
- Admin code is kept separate: frontend UI under `frontend/src/admin/`, backend
  Lambda under `backend/services/admin/mcp-tester/`. The shared role/view logic
  lives in `frontend/src/auth/` and `backend/services/layers/ai/ai/auth.py`.
- Frontend routing (`frontend/src/App.tsx`): `RequireAuth` → `SelectViewPage`
  (`/select-view`, shown when more than one view is available) → `RequireUser`
  (main app) or `RequireAdmin` (`/admin`). `RoleRedirect` sends `/` and
  `/administration` to the selected view's home. A fresh Auth0 login clears the
  stored view; reloads keep it. The account menu has **Switch view**.
- **`mcp-tester`** (`GET /v1/admin/mcp/tools`, `POST /v1/admin/mcp/call`) is the
  MCP *client*: it reads the admin claim + `sub`, builds MCP JSON-RPC, and
  invokes `knowledge-mcp` over its direct-invoke transport. The admin UI
  (`frontend/src/admin/pages/AdminIntegrationsPage.tsx`) lists tools via
  `tools/list`, renders an argument form from each tool's `inputSchema`, and
  shows the raw request/response.
- The `ai` layer has **no third-party dependencies** (stdlib + boto3 from the
  runtime), so `knowledge-mcp` stays lightweight while gaining role checks.

## Conventions

<!-- Coding style, naming, libraries. Example:
- Python: ruff, type hints required.
- TypeScript: strict mode, no default exports.
-->

### Page loading states

Loading is handled in one place per concern — never hand-roll timers per page.

- **Route entry (all pages):** routes are lazy (`React.lazy` in `App.tsx`) and
  `RouteGate` in `layouts/MainLayout.tsx` shows a page-shaped skeleton only
  while the lazy route chunk loads. The shape comes from
  `components/ui/RouteSkeleton.tsx`. There is no minimum display time — loading
  is driven purely by how long the chunk and the page's data actually take.
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
- Stops after 10 minutes of active polling and shows a manual **Refresh** so a
  stuck document cannot poll forever.
- Tune it in exactly one spot: the `useAdaptivePoll` call in
  `frontend/src/pages/KnowledgeBasesPage.tsx`.

## Local development

Everything runs locally on **Floci** — a free, LocalStack-compatible AWS
emulator (no AWS account, no auth token). Lambda, API Gateway, S3, SQS,
EventBridge and Step Functions run in Docker; Postgres + pgvector run alongside.
There is no custom local emulation: the same Lambda code, the same state machine
definition and the same API routes as production run against Floci, configured
only by environment variables.

```bash
make floci            # build + start + provision + migrate; prints the API URL
make ui               # React app -> http://localhost:5173
make floci-logs       # follow Floci logs
make floci-down       # stop and remove
```

- API base URL: `http://get1agent.execute-api.localhost.floci.io:4566`
  (`localhost.floci.io` resolves to 127.0.0.1 on the host, and Floci's embedded
  DNS resolves it inside Lambda containers, so presigned S3 URLs work from both).
- Point the UI at it via the Vite dev proxy (Floci only sends CORS headers on
  the preflight, not on proxied API Gateway responses):
  `printf 'VITE_API_URL=/\nVITE_API_PROXY_TARGET=http://get1agent.execute-api.localhost.floci.io:4566\n' > frontend/.env.local`
  (or just run `make floci`, which prints this). `VITE_API_URL=/` keeps the
  browser same-origin; the dev server forwards `/v1` to Floci.
- Auth: the HTTP API uses a JWT authorizer against the real Auth0 issuer, so the
  Floci container needs network access to `https://get1agent.us.auth0.com/`
  (OIDC discovery + JWKS). Configure via `AUTH0_ISSUER` / `AUTH0_AUDIENCE`.
- Compose file: `infra/local/floci/docker-compose.yml`. Host env: the root `.env`
  (from `infra/local/floci/env.example`).
- `infra/local/floci/init/ready.d/10-provision.py` mirrors Terraform: bucket +
  EventBridge notification → rule → SQS + DLQ → dispatcher → state machine →
  workers, plus the HTTP API + JWT authorizer + routes from
  `infra/terraform/envs/prod/api_gateway.tf`.
- The state machine definition is the same file Terraform deploys:
  `infra/terraform/modules/ingestion/statemachine.asl.json`.
- Ingestion runs with `EMBED_MODE=local`: real 1024-dim vectors from an Ollama
  container (`mxbai-embed-large`), so no Bedrock is needed. `make floci` pulls
  the model; `EMBED_MODE=bedrock` (production) uses Titan instead.
- Rerank runs with `RERANK_MODE=local`: a HuggingFace TEI container
  (`reranker`, `POST /rerank`) scores candidates with a cross-encoder
  (`cross-encoder/ms-marco-MiniLM-L6-v2` by default, configurable via
  `LOCAL_RERANK_MODEL`). `make floci` starts it and waits for `/health`.
  `RERANK_MODE=bedrock` (production) uses Amazon Rerank instead.
- After changing Lambda code: `make floci-build` then `make floci-up`
  (provisioning is re-run on every boot).
- `infra/scripts/migrate.sh` still handles generic local migrations; `make
  floci-migrate` / `make floci-migrate-down` point it at the Floci Postgres.

### Migrations

- **Local (Floci):** `make floci-migrate` (upgrade to head) and
  `make floci-migrate-down` (downgrade one revision). The script is
  `infra/local/floci/migrate.sh`; pass an explicit revision with
  `bash infra/local/floci/migrate.sh upgrade <rev>`.
- **Production:** run the **Migrate** GitHub Actions workflow
  (`.github/workflows/migrate.yml`) — pick `upgrade`/`downgrade` and an optional
  revision. It packages `backend/migrations` + `backend/services/shared`, uploads them to
  S3, and runs Alembic on the jumpbox EC2 (inside the VPC) over SSM. There is no
  migration Lambda.

## Commands

- Frontend: `npm run dev`, `npm run lint`, `npm run build`
- Local Lambdas / migrations: see "Local development" above.

## Rules

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

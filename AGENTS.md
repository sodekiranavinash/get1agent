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

## Architecture

- Frontend talks to API Gateway only; never directly to RDS.
- Lambdas share code via `backend/services/shared/` (bundled into the `data` layer).
- Each lambda is one service; that service's logic lives in its `src/handler.py`.

### Document ingestion

Uploads flow: browser PUTs to S3 via a presigned URL, then calls
`POST /v1/knowledge-bases/{id}/documents/{docId}/complete`.

- **Production**: S3 `ObjectCreated` → EventBridge → SQS
  (`ingestion-docs` + DLQ) → `ingestion-dispatcher` (batch 5, partial batch
  failures) → **Step Functions Express** (`ingest-{docId}-{contentHash}`) →
  `ingestion-extract` → `ingestion-index` (any stage failure →
  `ingestion-mark-failed`). Each stage is its own Lambda for per-stage
  memory/timeout/IAM and clear failure visibility. There is no in-process
  ingestion path.
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
- The VPC has no NAT; the worker reaches Bedrock through a VPC interface
  endpoint, and the dispatcher runs outside the VPC (it only calls Step
  Functions).

### Ingestion observability

- Workers emit one JSON log line per stage (`shared/observability.py`) with
  `documentId` / `knowledgeBaseId` / `stage`, so CloudWatch Logs Insights can
  query by document: `fields @timestamp, message | filter documentId = "…"`.
- `ingestion_events` is the UI timeline; `documents.status` is the terminal
  state. The UI shows a **Stalled** badge when a document stops advancing.
- No CloudWatch alarms are provisioned (monitoring will live in an admin panel).
- X-Ray (`enable_xray`, default true) traces the ingestion workers + state
  machine. Lambda log retention is 7 days (`log_retention_days`).

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

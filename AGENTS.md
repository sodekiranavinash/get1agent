# AGENTS.md

Context and rules for AI coding agents working in this repository.
Edit this file freely — opencode loads it automatically as project context.

## Project

`get1agent` monorepo.

```
frontend/   React + TypeScript + Tailwind (Vite)
backend/    Python Lambdas + shared layers (health-check, etc.)
infra/      Terraform + deploy scripts (API Gateway, RDS, S3)
tools/      Go Lambda tools
```

## Architecture

<!-- Describe components, data flow, key boundaries. Example:
- Frontend talks to API Gateway only; never directly to RDS.
- Lambdas share code via backend/shared/ layers.
- Each lambda is one service all that service logic is written there
-->

## Conventions

<!-- Coding style, naming, libraries. Example:
- Python: ruff, type hints required.
- TypeScript: strict mode, no default exports.
-->

### Page loading states

Loading is handled in one place per concern — never hand-roll timers per page.

- **Route entry (all pages):** routes are lazy (`React.lazy` in `App.tsx`) and
  `RouteGate` in `layouts/MainLayout.tsx` shows a page-shaped skeleton for at
  least `PAGE_SKELETON_MIN_MS` before revealing the page. The shape comes from
  `components/ui/RouteSkeleton.tsx`. Tune the timing in exactly one spot:
  `frontend/src/hooks/usePageQuery.ts`. If the page's data is ready sooner, the
  skeleton is dropped immediately (no waiting out the remaining time).
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

## Local development

Everything runs locally with the root `Makefile` + `local/` scripts. No Docker,
no AWS, no Lambda deployment needed to test.

```bash
cp .env.example .env.local      # sets DATABASE_URL (+ DB_NAME)
make dev                        # ALL local Lambdas + gateway -> http://localhost:9000
make ui                         # React app        -> http://localhost:5173
make gateway                    # path-routing proxy only
make account-settings           # Lambda over HTTP -> http://localhost:9001
make health-check               # Lambda over HTTP -> http://localhost:9003

# Migrations are a separate script (not a make target):
bash scripts/migrate.sh up|down|current|history|revision
bash scripts/migrate.sh lambda up|down|stamp   # invoke cloud migration-runner
```

- `local/run.sh` starts each Lambda with its own `uv`-managed env (no layer, no Docker).
- `local/run_lambda.py` is the HTTP→Lambda shim (decodes the Bearer JWT into
  `requestContext.authorizer.jwt.claims`, adds CORS).
- `local/dev.sh` starts every Lambda in `local/routes.json` + `local/gateway.py`,
  a path-prefix reverse proxy (like API Gateway) so the UI talks to one base URL.
- `scripts/migrate.sh` handles local migrations (`DATABASE_URL`) and, with the
  `lambda` mode, invoking the deployed migration-runner.
- To test the UI against the local API, set `VITE_API_URL=http://localhost:9000`
  in `frontend/.env.local`.

## Commands

- Frontend: `npm run dev`, `npm run lint`, `npm run build`
- Local Lambdas / migrations: see "Local development" above.

## Rules

- NEVER run Lambda functions via AWS or Docker locally. Test with the `make`
  targets / `local/` scripts / `scripts/migrate.sh`.
- Do not deploy from a local machine; deployment happens via GitHub Actions.
- Never commit secrets or `.env*` files (except `.env.example`).
- Do not edit generated files (`dist/`, `node_modules/`, `.terraform/`).
- One primary action per page. Render each primary CTA (e.g. "New Knowledge
  Base") in exactly one place — the page header (`PageHeader` `action`). Do not
  duplicate the same action in empty states, cards, or secondary sections;
  empty states should point to the existing header action instead.

## Do not touch

<!-- Paths agents must never modify. -->

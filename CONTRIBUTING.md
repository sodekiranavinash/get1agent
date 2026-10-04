# Contributing to get1agent

Thanks for your interest in improving get1agent! This project is open to contributions of all
kinds — bug reports, documentation, tests, and features. This guide explains how to get set up and
how to send a change.

By participating, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).

## Ways to contribute

- **Report a bug** — open a [bug report](https://github.com/sodekiranavinash/get1agent/issues/new?template=bug_report.yml).
- **Request a feature** — open a [feature request](https://github.com/sodekiranavinash/get1agent/issues/new?template=feature_request.yml).
- **Improve docs** — typos, clarity, and examples are genuinely valuable.
- **Send code** — fixes and features via pull request.

If you are planning a large change, please open an issue (or a draft PR) first so we can agree on
the approach before you invest a lot of time.

## Development setup

The entire platform runs locally on **Floci**, a free, LocalStack-compatible AWS emulator. No AWS
account or auth token is required.

**Prerequisites:** Docker (Compose v2), Node.js 22+, `make`, and — for the tests — Python 3.13+ with
[`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/sodekiranavinash/get1agent.git
cd get1agent

cp infra/local/floci/env.example .env
make floci            # build + start + provision; prints the API URL
printf 'VITE_API_URL=/\nVITE_API_PROXY_TARGET=http://get1agent.execute-api.localhost.floci.io:4566\n' \
  > frontend/.env.local
make ui               # React app -> http://localhost:5173
```

See the [README](README.md#quick-start) for the full command reference, and
[`AGENTS.md`](AGENTS.md) for the architecture, data-access rules, and conventions.

## Project conventions

A few rules keep the codebase consistent and fast. The important ones:

- **Data access is non-negotiable.** One item per entity in DynamoDB, small metadata only, and
  `GetItem`/`Query` only — **no `Scan` on the request path, no N+1**. Vectors go to S3 Vectors;
  bulky artifacts go to S3. See [`docs/design/data-access.md`](docs/design/data-access.md) and
  [`AGENTS.md`](AGENTS.md).
- **Local development goes through Floci.** Do not add custom local emulation or Floci-specific
  branches to application code — configure the stack with environment variables instead.
- **Shared code lives in `backend/packages/`** and is bundled into each Lambda, along with each
  app's third-party dependencies — there are no Lambda layers. Each app declares its deps in its own
  `pyproject.toml`.
- **Frontend** uses the loading conventions in [`AGENTS.md`](AGENTS.md) (shaped skeletons,
  `usePageQuery`, `useAdaptivePoll`).
- **Match the surrounding code** — structure, naming, and style.

## Running tests

```bash
make test          # integration suite: moto DynamoDB + in-memory S3 (no Docker, no AWS)
make test-unit     # per-Lambda unit tests
```

Both are run by the [`Backend tests`](.github/workflows/backend-tests.yml) workflow on every push
and pull request that touches `backend/**`. Frontend changes should pass `npm run lint` and
`npm run build` inside `frontend/`.

Please add or update tests for the behavior you change.

## Submitting a pull request

1. **Fork** the repository and create a branch from `main`. Use a descriptive prefix:
   `feat/`, `fix/`, `docs/`, `refactor/`, or `test/`.
2. **Keep the change focused.** One logical change per pull request is much easier to review.
3. **Write a clear PR description** covering *what* changed and *why*. Link the issue it closes
   (`Closes #123`). The pull request template will guide you.
4. **Make sure checks pass** — the `Backend tests` workflow must be green.
5. **Never commit secrets.** No credentials, tokens, or `.env*` files.

A maintainer will review as soon as they can. Reviews may request changes; that is normal and part
of keeping the project healthy.

## Style

- **Python** — standard library first; keep Lambda handlers thin and put logic in `src/`.
- **TypeScript/React** — function components, ES modules, and the existing UI primitives.
- **Commits** — clear, imperative subject lines (for example, `fix: refresh rotated MCP token`).

## Reporting security issues

Do **not** open a public issue for a security vulnerability. Follow the process in
[`SECURITY.md`](SECURITY.md).

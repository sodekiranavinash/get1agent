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
-->

## Conventions

<!-- Coding style, naming, libraries. Example:
- Python: ruff, type hints required.
- TypeScript: strict mode, no default exports.
-->

## Commands

<!-- Build/test/lint commands agents should run. Example:
- Frontend: `npm run dev`, `npm run lint`, `npm run test`
- Backend: `pytest`
- Infra: `bash infra/aws/deploy-all.sh`
-->

## Rules

<!-- Hard constraints. Example:
- Never commit secrets or .env files.
- Do not edit generated files.
-->

## Do not touch

<!-- Paths agents must never modify. -->

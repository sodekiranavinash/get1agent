# Infra — rules

Full deployment guide: [`infra/DEPLOY.md`](../infra/DEPLOY.md).

## Overview

- **Region: `ap-south-1` (Mumbai)** for all AWS resources (API, DynamoDB, S3,
  S3 Vectors, Lambdas, web S3, Terraform state).
- **UI:** S3 + Cloudflare (`infra/terraform/envs/web`) — deploy via the
  **Frontend** workflow.
- **API:** AWS API Gateway HTTP API (`infra/terraform/modules/api_gateway`) +
  Auth0 JWT. Domain `api.get1agent.com` → Cloudflare CNAME → API Gateway.
- **Data:** DynamoDB single table (`infra/terraform/modules/dynamodb`) + S3
  Vectors (`infra/terraform/modules/s3_vectors`) + S3 objects.
- **No VPC, no RDS, no NAT.**
- **Backend Lambdas:** `infra/terraform/modules/lambda_function` (Python in
  `backend/services/`, AgentCore runtime apps in `backend/agents/`, shared code
  in `backend/packages/`, dependency layers in
  `backend/services/dependency-layers/`, canonical registry
  `backend/registry.json`).
- **API routes:** `infra/terraform/envs/prod/api_gateway.tf`.
- There is **no `/health` route** (API Gateway HTTP APIs only allow
  `AWS_PROXY`/`HTTP_PROXY` integrations, so a MOCK route is not possible).

## GitHub Actions

- **Infra** — `web` / `api_gateway` / `lambdas` (state bucket auto-created; runs
  the apply). This is what creates DynamoDB, S3 Vectors and the Lambdas.
- **Frontend** — build + sync to S3 (separate from Infra).
- **Backend** — deploy Lambda **code**, grouped into checkboxes:
  `user-apis`, `knowledge-mcp`, `admin-apis`, `mcp-tools`, `ingestion-apis`
  (the `group` field in `registry.json`).
- **Backend tests** — runs `make test` on pushes/PRs touching `backend/**`.

## Deploy scripts

- `infra/aws/deploy-all.sh` — full infra apply.
- `infra/aws/deploy-infra.sh` — Terraform only (bootstrap + web + full prod).
- `infra/aws/apply-prod.sh` — targeted prod apply (used by the Infra workflow).
- `infra/aws/deploy-backend.sh` — package/deploy backend Lambdas by
  `<name|group>`.

## GitHub secrets

- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `EXA_API_KEY`.

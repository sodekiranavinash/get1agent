# Infra — rules

Full deployment guide: [`infra/DEPLOY.md`](../../infra/DEPLOY.md).

## Overview

- **Region: `ap-south-1` (Mumbai)** for all AWS resources (API, DynamoDB, S3,
  S3 Vectors, Lambdas, KMS, web S3, Terraform state). Two things are deliberately
  cross-region: **Bedrock Rerank** (`amazon.rerank-v1:0`, not offered in
  `ap-south-1`) and the **AgentCore Web Search** connector run in `us-west-2`.
- **UI:** S3 website bucket + Cloudflare (`infra/terraform/envs/web`) — deploy via
  the **Frontend** workflow.
- **API:** AWS API Gateway HTTP API (`infra/terraform/modules/api_gateway`) +
  Auth0 JWT. Domain `api.get1agent.com` → Cloudflare CNAME → API Gateway.
- **Data:** DynamoDB single table (`infra/terraform/modules/dynamodb`) + S3
  Vectors (`infra/terraform/modules/s3_vectors`) + S3 objects
  (`infra/terraform/modules/knowledge_storage`).
- **Secrets:** KMS (`infra/terraform/modules/kms`) backs the Vault and the
  MCP-connection encryption context.
- **Agent runtime:** `infra/terraform/modules/agent_runtime` — ECR, the
  AgentCore runtime role + runtime, the control-plane Lambda and its Function
  URL, and the Lambda MicroVM image + streaming proxy. Deployed by
  `bash infra/aws/deploy-agent-runtime.sh` (build + push the ARM64 image, then
  apply with `agent_worker_image_uri`). The runtime reaches Amazon Bedrock with
  its task role (SigV4) — no model API key.
- **Managed and serverless:** DynamoDB, S3, S3 Vectors, Lambda and AgentCore on
  public HTTPS endpoints.
- **Backend Lambdas:** `infra/terraform/modules/lambda_function` (Python in
  `backend/services/`, AgentCore runtime apps in `backend/agents/`, shared code
  in `backend/packages/`, canonical registry `backend/registry.json`).
  **There are no Lambda layers** — shared application code (`core`, `data`,
  `retrieval`, `ingestion`) and third-party dependencies are bundled into each
  app's zip by its `Makefile` (per-app deps in each `pyproject.toml`).
- **API routes:** `infra/terraform/envs/prod/api_gateway.tf`.
- There is **no `/health` route** (API Gateway HTTP APIs only allow
  `AWS_PROXY`/`HTTP_PROXY` integrations, so a MOCK route is not possible).

## GitHub Actions

- **Infra** — checkboxes `web` / `api_gateway` / `lambdas`. The `lambdas` job
  also packages and deploys the **agent-run** control plane + MicroVM and applies
  the AgentCore runtime (`bash infra/aws/deploy-agent-runtime.sh`).
- **Frontend** — build + sync to S3 (separate from Infra).
- **Backend** — deploy Lambda **code**, grouped into checkboxes:
  `user-apis`, `knowledge-mcp`, `admin-apis`, `mcp-tools`, `scheduler`,
  `ingestion-apis` (the `group` field in `backend/registry.json`).
- **Backend tests** — runs `make test` on pushes/PRs touching `backend/**`.

## Deploy scripts

- `infra/aws/deploy-all.sh` — full infra apply.
- `infra/aws/deploy-infra.sh` — Terraform only (bootstrap + web + full prod).
- `infra/aws/apply-prod.sh` — targeted prod apply (used by the Infra workflow).
- `infra/aws/deploy-backend.sh` — package/deploy backend Lambdas by
  `<name|group>`.
- `infra/aws/deploy-agent-runtime.sh` — build + push the AgentCore runtime image
  and apply `module.agent_runtime`.

## GitHub secrets / Terraform variables

- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` — deploy credentials.
- `AGENT_SERVICE_CLIENT_ID` / `AGENT_SERVICE_CLIENT_SECRET` — Auth0 M2M app for
  server-side agent runs (scheduler + evaluations).
- `AUTH_MGMT_CLIENT_ID` / `AUTH_MGMT_CLIENT_SECRET` — Auth0 Management API M2M
  (`delete:users`) so account deletion erases the Auth0 identity (optional; blank
  falls back to the manual step).
- `VAULT_KMS_KEY_ARN` — Vault / MCP-connection encryption key (Terraform creates
  it; not a GitHub secret).
- There is **no `WEB_SEARCH_API_KEY`**: web search is the AgentCore Gateway's
  built-in connector and needs only `bedrock-agentcore:InvokeWebSearch`.

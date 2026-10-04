# Deploy get1agent on AWS

**API Gateway HTTP API** handles `api.get1agent.com` with Auth0 JWT, CORS, and
throttling. The backend runs on managed AWS: **DynamoDB** (operational data), **S3**
(documents + keyword index), **S3 Vectors** (embeddings), **Amazon Bedrock**
(inference, embeddings, rerank, Guardrails) and **AgentCore** (runtime, memory,
policy, gateway, identity, registry, evaluations, browser) — all scaled
automatically and billed per request.

| Stack | Region | Resources |
|-------|--------|-----------|
| **All AWS infra** | `ap-south-1` (Mumbai) | DynamoDB, S3, S3 Vectors, API Gateway, Lambdas, KMS, web S3, Terraform state |
| **AgentCore runtime** | `ap-south-1` | ECR image, AgentCore Runtime, control-plane Lambda + Function URL, Lambda MicroVM proxy, Gateway, Memory, Policy, Identity, Registry, Browser |
| **Cross-region calls** | `us-west-2` | Bedrock Rerank (`amazon.rerank-v1:0`) and the AgentCore Web Search connector (not offered in `ap-south-1`) |

---

## Quick start

```bash
bash infra/aws/deploy-all.sh
```

Or via GitHub Actions: run the **Infra** workflow.

---

## One-time setup

### 1) Auth0 API

In Auth0 Dashboard → **APIs** → Create API:

| Field | Value |
|-------|--------|
| Name | get1agent API |
| Identifier | `https://api.get1agent.com` |

This must match `auth_audience` in Terraform and the frontend `audience` param.

### 2) Cloudflare DNS for API (`api.get1agent.com`)

**No A record needed** — use **CNAME** records only (grey cloud / DNS only).

1. Set `enable_api_custom_domain = true` in `infra/terraform/envs/prod/terraform.tfvars`
2. Run `terraform apply` (or Infra GitHub Action)
3. Get DNS values:

```bash
cd infra/terraform/envs/prod
terraform output acm_validation_records   # step A
terraform output api_gateway_cname_target # step B
```

| Step | Cloudflare record | Notes |
|------|-------------------|--------|
| **A** | ACM validation **CNAME** | Copy `name` + `value` from `acm_validation_records` (usually `_xxxx.api` → `_xxxx.acm-validations.aws`) |
| **B** | `api` **CNAME** → API Gateway target | Copy from `api_gateway_cname_target` (looks like `d-xxxxx.execute-api.ap-south-1.amazonaws.com`) |
| **C** | Delete old records | Remove any stale `api` **A** record if present |

### 3) Verify

```bash
curl -s -o /dev/null -w "%{http_code}\n" https://api.get1agent.com/v1/knowledge-bases
# 401 — the route exists and requires a bearer token
```

---

## Architecture

```
Browser → Cloudflare → API Gateway (JWT) → Lambda services
                                          ├─ user-api (control plane)
                                          ├─ knowledge-mcp / code-interpreter / http-fetch / custom-tools / mcp-connections / browser
                                          ├─ ingestion-* (EventBridge → SQS → Step Functions)
                                          ├─ scheduler
                                          ├─ DynamoDB (single table + 3 sparse GSIs)
                                          ├─ S3 + S3 Vectors (artifacts + embeddings)
                                          ├─ KMS (Vault + MCP credentials)
                                          └─ Amazon Bedrock (models, embeddings, rerank, Guardrails)

Agent run: browser → API Gateway → agent-run control plane → Lambda MicroVM
           → AgentCore Runtime (agentflow | workflow) → AgentCore Gateway
           → MCP servers + AgentCore Memory/Policy → Bedrock + CloudWatch/X-Ray
```

| Component | Role |
|-----------|------|
| **API Gateway** | Auth0 JWT, CORS, per-route + stage throttling, access logs |
| **DynamoDB** | Single table `get1agent` — one item per entity (users, KBs, documents, tags, skills, agents, workflows, storage, vault, conversations, evals, support, notifications, feedback) |
| **S3** | Document uploads, derived artifacts, keyword (BM25) index, parents, manifests, transcripts, storage files, custom tools, sessions |
| **S3 Vectors** | One vector index per user (`idx-<userId>`) for knowledge + memory + semantic cache |
| **KMS** | Vault secrets and MCP connection credentials (per-`{userId, id, field}` encryption context) |
| **Amazon Bedrock** | Titan Text Embeddings V2 + Titan Multimodal G1, opt-in Bedrock Rerank (`amazon.rerank-v1:0`, `us-west-2`), the curated model gateway (Nova/DeepSeek/Qwen/GLM/Nemotron), Guardrails, prompt caching, structured outputs |
| **AgentCore** | Runtime (agentflow + workflow), Memory, Policy, Gateway, Identity, Registry, Evaluations, Optimization, Browser, Code Interpreter |
| **Agent-run proxy** | Control-plane Lambda + Lambda MicroVM streaming proxy (SSE) in front of the runtime |
| **Observability** | OpenTelemetry → CloudWatch + X-Ray (ADOT collector) |

---

## API Gateway features (configured)

| Feature | Config |
|---------|--------|
| **JWT auth** | Auth0 issuer + audience `https://api.get1agent.com` |
| **CORS** | `www.get1agent.com`, `localhost:5173` |
| **Stage throttling** | 50 req/s, burst 100 (adjust in `api_gateway` module) |
| **Per-route throttling** | Set on each `lambda_routes` entry |
| **Access logs** | CloudWatch, 7-day retention |

---

## Backend Lambdas (Python)

Registry: `backend/registry.json` — lists **apps** (each with
`dir`, `packages: [...]` and `layers: []`). **There are no Lambda layers**:
shared application code and third-party dependencies are bundled into each app's
zip.

| App | Route(s) / trigger | Packages | Purpose |
|--------|----------|--------|---------|
| `user-api` | `/v1/*` (control plane) | `core`, `data`, `retrieval` | KBs, documents, skills, agents, workflows, storage, vault, conversations, evals, support, privacy |
| `knowledge-mcp` | `POST /mcp` | `core`, `data`, `retrieval` | Knowledge MCP tools + hybrid retrieval |
| `code-interpreter` | `POST /mcp/code-interpreter` | `core`, `data` | AgentCore code sandbox |
| `http-fetch` | `POST /mcp/http-fetch` | `core`, `data`, `retrieval` | SSRF-guarded fetch + user storage access |
| `custom-tools` | `POST /mcp/custom-tools` | `core`, `data` | user-built Python MCP tools |
| `mcp-connections` | `/v1/mcp/*`, `POST /mcp/remote` | `core`, `data` | Remote MCP OAuth broker + aggregator |
| `browser` | `POST /mcp/browser` | `core`, `data` | AgentCore Browser sessions (domain allowlist) |
| `mcp-tester` | `/v1/admin/*` | `core`, `data` | Admin: MCP client, AI credits, support, security |
| `scheduler` | EventBridge `rate(1 minute)` | `core`, `data` | Runs due agent/workflow schedules |
| `ingestion-dispatcher` | SQS | `core`, `data`, `ingestion` | Parse `raw/` events, start Step Functions |
| `ingestion-extract` | Step Functions | `core`, `data`, `ingestion` | extract + chunk (heavy deps bundled: `pymupdf`, `python-docx`, `openpyxl`) |
| `ingestion-embed` | Step Functions | `core`, `data`, `retrieval`, `ingestion` | Bedrock Titan embeddings |
| `ingestion-index` | Step Functions | `core`, `data`, `retrieval`, `ingestion` | vectors, postings, catalog, manifest |
| `ingestion-mark-failed` | Step Functions | `core`, `data`, `ingestion` | Mark a document failed |
| `ingestion-watchdog` | EventBridge `rate(10 minutes)` | `core`, `data`, `ingestion` | Fail stalled documents |

There is **no `web-search` Lambda** — web search is the AgentCore Gateway's
built-in connector. `backend/services/agent-run/` is a Node Lambda (control
plane + MicroVM proxy) and `backend/agents/` is the AgentCore runtime container;
both are excluded from the Python Lambda build.

**Dependencies:**
- Each app declares its own third-party deps in `pyproject.toml` and installs them
  with `uv sync` at build time; the `Makefile` copies `handler.py`, `src/`, the
  shared packages it uses and all third-party deps to the zip root.
- Shared application code lives once in `backend/packages/` (`core`, `data`,
  `retrieval`, `ingestion`) and is bundled into each zip.

```bash
# Package + upload handler code
make -C backend/services/apis/user-api package
bash infra/aws/deploy-backend.sh user-api deploy
```

GitHub Actions: **Backend** workflow — pick one or more **groups** to deploy handler code:

| Checkbox | Lambdas |
|----------|---------|
| `user-apis` | `user-api` |
| `knowledge-mcp` | `knowledge-mcp` |
| `admin-apis` | `mcp-tester` |
| `mcp-tools` | `code-interpreter`, `http-fetch`, `custom-tools`, `mcp-connections`, `browser` |
| `scheduler` | `scheduler` |
| `ingestion-apis` | `ingestion-dispatcher`, `ingestion-extract`, `ingestion-embed`, `ingestion-index`, `ingestion-mark-failed`, `ingestion-watchdog` |

Groups come from the `group` field in `backend/registry.json`. The CLI
takes the same names: `bash infra/aws/deploy-backend.sh mcp-tools deploy`.

---

## Adding Lambda routes

Edit `infra/terraform/envs/prod/api_gateway.tf`:

```hcl
lambda_routes = {
  my_service = {
    method               = "POST"
    path                 = "/my-path"
    lambda_invoke_arn    = module.my_lambda.invoke_arn
    lambda_function_name = module.my_lambda.function_name
    authorization_type   = "JWT"
    throttle_rate_limit  = 10
    throttle_burst_limit = 20
  }
}
```

Lambdas must handle **API Gateway HTTP API v2** events (not raw JSON).

---

## Data access

DynamoDB and S3 are public endpoints, so there is no jumpbox and no tunnel.
Inspect data with the AWS CLI:

```bash
aws dynamodb scan --table-name get1agent --max-items 20
aws s3 ls s3://get1agent-prod-knowledge-bases/
```

---

## GitHub Actions

Four workflows — each has checkboxes to run only what you need:

| Workflow | Components (checkboxes) |
|----------|-------------------------|
| **Infra** | Web, API Gateway, Lambdas (DynamoDB + S3 Vectors + state bucket created automatically). The `lambdas` job also packages the agent-run control plane + MicroVM and applies the AgentCore runtime via `infra/aws/deploy-agent-runtime.sh`. |
| **Frontend** | Build + sync to S3 (separate from Infra) |
| **Backend** | grouped checkboxes (`user-apis`, `knowledge-mcp`, `admin-apis`, `mcp-tools`, `scheduler`, `ingestion-apis`) = deploy Lambda **code** |
| **Backend tests** | `make test` on pushes/PRs touching `backend/**` |

Push to `main` under `frontend/**` auto-runs **Frontend**.

Terraform state lives in a dedicated S3 bucket (created automatically before any
apply). **Web** is a separate bucket for the static site (`www.get1agent.com`).
After changing the agent runtime code, rebuild + push the ARM64 image and re-apply
`module.agent_runtime` (`bash infra/aws/deploy-agent-runtime.sh`).

---

## Cost notes (free tier friendly)

| Service | Cost |
|---------|------|
| API Gateway HTTP API | 1M requests/month (12 months) |
| Lambda | 1M requests/month |
| DynamoDB (on-demand) | pay per request; no idle floor |
| S3 | $0.023/GB-month |
| S3 Vectors | $0.06/GB-month; no idle floor |
| CloudWatch logs | 5 GB ingestion |

No WAF by default (adds ~$5/month if needed later). No always-on RDS instance.

---

## Troubleshooting

### ACM certificate stuck

Add validation CNAME from `terraform output acm_validation_records`, then re-run apply.

### 401 on API routes

Ensure Auth0 API identifier matches `https://api.get1agent.com` and frontend
requests include `Authorization: Bearer <token>` with correct audience.

### Terraform state lock

```bash
cd infra/terraform/envs/prod
terraform force-unlock <LOCK_ID>
```

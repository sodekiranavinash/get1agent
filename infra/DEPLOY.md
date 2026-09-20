# Deploy get1agent on AWS

**API Gateway HTTP API** handles `api.get1agent.com` with Auth0 JWT, CORS, and
throttling. The backend is serverless: **DynamoDB** (operational data), **S3**
(documents + keyword index), **S3 Vectors** (embeddings) and **Voyage AI**. There
is no VPC and no RDS.

| Stack | Region | Resources |
|-------|--------|-----------|
| **All AWS infra** | `ap-south-1` (Mumbai) | DynamoDB, S3, S3 Vectors, API Gateway, Lambdas, web S3, Terraform state |

Future **AgentCore** agents can stay in `us-east-1` when you add them (separate from this repo).

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

This must match `auth0_audience` in Terraform and the frontend `audience` param.

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
Browser → Cloudflare → API Gateway (JWT) → Lambda functions
                                          ├─ DynamoDB (single table + GSIs)
                                          ├─ S3 (raw/derived/index artifacts)
                                          ├─ S3 Vectors (per-user embedding index)
                                          └─ Voyage AI (embeddings)
```

| Component | Role |
|-----------|------|
| **API Gateway** | Auth0 JWT, CORS, per-route + stage throttling, access logs |
| **DynamoDB** | Single table `get1agent` (users, KBs, documents, tags, skills, events, quotas, sessions) |
| **S3** | Document uploads, derived artifacts, keyword index, parents, manifests |
| **S3 Vectors** | One vector index per user (`idx-<userId>`) |
| **Voyage AI** | Text + multimodal embeddings and opt-in rerank (`voyage-4-large` / `voyage-multimodal-3.5` / `rerank-3`); key via `TF_VAR_voyage_api_key` |

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

Registry: `backend/registry.json` — lists **layers** and **apps**
(each with `packages: [...]` and `layers: [...]`).

| App | Route(s) | Layers | Purpose |
|--------|----------|--------|---------|
| `user-api` | `/v1/knowledge-bases*`, `/v1/agent-skills*`, `/v1/user/settings` | `base` | All user CRUD |
| `knowledge-mcp` | `POST /mcp` | `base`, `genai` | Knowledge MCP tools + hybrid retrieval |
| `web-search` | `POST /mcp/web-search` | `base`, `genai` | Exa web search |
| `code-interpreter` | `POST /mcp/code-interpreter` | `base`, `genai` | AgentCore code sandbox |
| `mcp-tester` | `/v1/admin/mcp/*` | — | Admin MCP client |
| `ingestion-extract` | (Step Functions) | `extra-tools` | extract + chunk |
| `ingestion-*` | (SQS / Step Functions) | — | embed → index (+ mark-failed, watchdog, dispatcher) |

| Layer | Contents (third-party only) |
|-------|----------|
| `base` | `tzdata`, `python-dateutil` |
| `genai` | `awslabs.mcp-lambda-handler` (future: strands, AI SDKs) |
| `extra-tools` | `pymupdf`, `python-docx`, `openpyxl` |
| `ml` | *(future)* torch/transformers/… |

Shared application code lives once in `backend/packages/` (`core`,
`.data`, `.retrieval`, `.ingestion`) and is **bundled into each app's zip**.
App zips hold only app code + those packages; layers hold only third-party deps.
`agents/` is AgentCore runtime and is excluded from the Lambda build.

```bash
# Build layers + handler zips locally
bash infra/aws/build-backend-layers.sh
make -C backend/services/user-api package

# Package + upload handler code (after Infra created the function + layer)
bash infra/aws/deploy-backend.sh user-api deploy
```

Layer updates require an **Infra** apply (Terraform publishes a new layer version).

GitHub Actions: **Backend** workflow — pick one or more **groups** to deploy handler code:

| Checkbox | Lambdas |
|----------|---------|
| `user-apis` | `user-api` |
| `knowledge-mcp` | `knowledge-mcp` |
| `admin-apis` | `mcp-tester` |
| `mcp-tools` | `web-search`, `code-interpreter` |
| `ingestion-apis` | `ingestion-dispatcher`, `ingestion-extract`, `ingestion-embed`, `ingestion-index`, `ingestion-mark-failed`, `ingestion-watchdog` |

Groups come from the `group` field in `backend/services/registry.json`. The CLI
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

Three workflows — each has checkboxes to run only what you need:

| Workflow | Components (checkboxes) |
|----------|-------------------------|
| **Infra** | Web, API Gateway, Lambdas (DynamoDB + S3 Vectors + state bucket created automatically) |
| **Frontend** | Build + sync to S3 (separate from Infra) |
| **Backend** | grouped checkboxes (`user-apis`, `knowledge-mcp`, `admin-apis`, `mcp-tools`, `ingestion-apis`) = deploy Lambda **code** |

Push to `main` under `frontend/**` auto-runs **Frontend**.

Terraform state lives in a dedicated S3 bucket (created automatically before any
apply). **Web** is a separate bucket for the static site (`www.get1agent.com`).

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

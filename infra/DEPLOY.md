# Deploy get1agent on AWS

**API Gateway HTTP API** handles `api.get1agent.com` with Auth0 JWT, CORS, and throttling. **EC2 jumpbox** is SSM-only for RDS tunneling. **Lambdas** are added as API routes in Terraform.

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
| **B** | `api` **CNAME** → API Gateway target | Copy from `api_gateway_cname_target` (looks like `d-xxxxx.execute-api.us-east-1.amazonaws.com`) |
| **C** | Delete old records | Remove any `api` **A** record and `kong` **A** record if present |

### 3) Verify

```bash
curl -s https://api.get1agent.com/health
# {"status":"ok","service":"get1agent-api"}

curl -s https://api.get1agent.com/health/db
# {"status":"ok","database":"get1agent"}
```

---

## Architecture

```
Browser → Cloudflare → API Gateway (JWT) → Lambda functions
DBeaver → SSM tunnel → EC2 jumpbox → RDS PostgreSQL (private)
```

| Component | Role |
|-----------|------|
| **API Gateway** | Auth0 JWT, CORS, per-route + stage throttling, access logs |
| **EC2 jumpbox** | SSM only — no public ports, no Kong |
| **RDS** | `get1agent` database for app/Lambdas |

---

## API Gateway features (configured)

| Feature | Config |
|---------|--------|
| **JWT auth** | Auth0 issuer + audience `https://api.get1agent.com` |
| **CORS** | `www.get1agent.com`, `localhost:5173` |
| **Stage throttling** | 50 req/s, burst 100 (adjust in `api_gateway` module) |
| **Per-route throttling** | Set on each `lambda_routes` entry |
| **Access logs** | CloudWatch, 7-day retention |
| **Health** | `GET /health` (no auth) |
| **DB health** | `GET /health/db` (no auth, RDS IAM check) |

---

## Backend Lambdas (TypeScript)

Registry: `backend/registry.json`

| Lambda | Route | Purpose |
|--------|-------|---------|
| `health-check` | `GET /health/db` | RDS IAM `SELECT 1` |

```bash
# Package locally
make -C backend/health-check package

# Package + upload code (after Infra created the function)
bash infra/aws/deploy-backend.sh health-check deploy
```

GitHub Actions: **Backend — deploy Lambda** workflow (`lambda_name`: `health-check`, `get1agent-prod-health-check`, or `all`).

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

## DBeaver (SSM tunnel)

```bash
bash infra/aws/db-tunnel.sh --show-creds
bash infra/aws/db-tunnel.sh
```

Connect DBeaver to `localhost:15432` (master user from Secrets Manager).

---

## GitHub Actions

| Workflow | Purpose |
|----------|---------|
| **Infra** | Terraform: API Gateway + jumpbox + RDS + Lambdas |
| **Backend — deploy Lambda** | Package + upload `backend/*` Lambdas |
| **Tools — deploy Lambda** | Package + upload `tools/*` Lambdas |
| **Deploy frontend** | S3 static site |

---

## Cost notes (free tier friendly)

| Service | Free tier |
|---------|-----------|
| API Gateway HTTP API | 1M requests/month (12 months) |
| Lambda | 1M requests/month |
| EC2 `t4g.micro` | 750 hours/month |
| RDS `db.t4g.micro` | 750 hours/month |
| CloudWatch logs | 5 GB ingestion |

No WAF by default (adds ~$5/month if needed later).

---

## Troubleshooting

### ACM certificate stuck

Add validation CNAME from `terraform output acm_validation_records`, then re-run apply.

### 401 on API routes

Ensure Auth0 API identifier matches `https://api.get1agent.com` and frontend requests include `Authorization: Bearer <token>` with correct audience.

### Terraform state lock

```bash
cd infra/terraform/envs/prod
terraform force-unlock <LOCK_ID>
```

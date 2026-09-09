# Deploy get1agent on AWS

**API Gateway HTTP API** handles `api.get1agent.com` with Auth0 JWT, CORS, and throttling. **On-demand EC2 jumpbox** gets a public IPv4 only while you use `db-access.sh` (stopped when idle). **Lambdas** are added as API routes in Terraform.

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
Browser → Cloudflare → API Gateway (JWT) → Lambda functions → RDS PostgreSQL (private VPC)
EC2 jumpbox (on-demand, public IPv4 only while running) → RDS PostgreSQL
```

| Component | Role |
|-----------|------|
| **API Gateway** | Auth0 JWT, CORS, per-route + stage throttling, access logs |
| **EC2 jumpbox** | Started by `db-access.sh`; SSM tunnel to RDS; **stopped on exit** (no IPv4 bill while idle) |
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

GitHub Actions: **Backend** workflow — check `health-check` to deploy.

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

## Local DB access (on-demand, minimal cost)

Public IPv4 costs **~$0.005/hr only while the jumpbox is running**. The script stops EC2 when you exit (releases the IP).

```bash
# Credentials (no EC2 start)
bash infra/aws/db-access.sh --show-creds

# Start jumpbox → tunnel localhost:15432 → RDS → stop jumpbox on Ctrl+C
bash infra/aws/db-access.sh
```

**DBeaver:** host `localhost`, port `15432`, SSH tab **OFF**, SSL require.

```bash
# Stop jumpbox manually if needed
bash infra/aws/db-access.sh --stop
```

RDS is **private** — reachable from VPC Lambdas and the jumpbox while it is running.

---

## GitHub Actions

Four workflows — each has checkboxes to run only what you need:

| Workflow | Components (checkboxes) |
|----------|-------------------------|
| **Infra** | Web, VPC, RDS, API Gateway, Lambdas (state S3 bucket is created automatically) — always apply |
| **Frontend** | Build + sync to S3 (separate from Infra) |
| **Backend** | `health-check` — one checkbox = deploy Lambda **code** |
| **Tools** | `challan-extractor` — one checkbox = deploy Lambda **code** |

Push to `main` under `frontend/**` auto-runs **Frontend**.

Terraform state lives in a dedicated S3 bucket (created automatically before any apply). **Web** is a separate bucket for the static site (`www.get1agent.com`).

---

## Cost notes (free tier friendly)

| Service | Free tier |
|---------|-----------|
| API Gateway HTTP API | 1M requests/month (12 months) |
| Lambda | 1M requests/month |
| EC2 `t4g.micro` (stop when idle via `db-access.sh`) | 750 hours/month |
| RDS `db.t4g.micro` | 750 hours/month |
| Public IPv4 | ~$0.005/hr **only while jumpbox is running** |
| CloudWatch logs | 5 GB ingestion |
| SSM Parameter Store (SecureString) | Standard parameters are free |

No WAF by default (adds ~$5/month if needed later).

DB credentials live in **SSM Parameter Store** (not Secrets Manager — saves ~$0.80/month).

### Remove Kong-era leftovers

After migrating from Kong, run once:

```bash
bash infra/aws/cleanup-legacy-aws.sh
```

Removes orphaned Kong security groups, Elastic IPs, and old Secrets Manager secrets.

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

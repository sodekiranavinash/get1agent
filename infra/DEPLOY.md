# Deploy get1agent on AWS

**EC2** runs `control_plane` (FastAPI). **RDS** is private. The app connects with **IAM** (no DB password). Master password is **DBeaver / SSM tunnel only**.

---

## Quick start (from your Mac)

### 1) One-time setup

```bash
aws configure
brew install --cask session-manager-plugin   # for DBeaver DB tunnel
```

### 2) Deploy everything

```bash
bash infra/aws/deploy-all.sh
```

Or step by step:

```bash
bash infra/aws/deploy-infra.sh apply
bash infra/aws/deploy-control-plane.sh
```

### 3) Verify

```bash
curl -s https://api.get1agent.com/health
```

---

## API domain (Cloudflare)

nginx on EC2 listens on **port 80** and proxies to FastAPI on **localhost:8000**.

| Step | Action |
|------|--------|
| 1 | `terraform output app_public_ip` |
| 2 | Cloudflare DNS: **A** record `api` → that IP, **Proxied** (orange cloud) |
| 3 | Cloudflare SSL/TLS → **Flexible** (same as www S3 site) |
| 4 | `bash infra/aws/deploy-control-plane.sh` (syncs nginx + app) |

Terraform opens **port 80** to [Cloudflare IPs](https://www.cloudflare.com/ips/) only. Port **22 (SSH) is closed**. Port **8000** is localhost only.

| Port | Who can connect |
|------|-----------------|
| **80** | Cloudflare IPs only |
| **8000** | localhost only (nginx proxy) |
| **5432** | EC2 only (RDS private) |

Admin access to EC2 and RDS uses **AWS SSM** (no SSH keys, no home IP allowlist).

---

## GitHub Actions (alternative)

### Secrets (Settings → Actions)

| Secret | Example |
|--------|---------|
| `AWS_ACCESS_KEY_ID` | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | `...` |

### Workflows

1. **Infra** — Terraform (EC2 + RDS + ECR)
2. **Deploy control_plane** — builds `control_plane/` → ECR → EC2 via SSM

---

## Auth model

| Who | How it connects to Postgres |
|-----|----------------------------|
| **control_plane on EC2** | IAM role → `rds-db:connect` → user `get1agent_app` (no password) |
| **DBeaver / you** | SSM tunnel → master user `get1agent` + password from Secrets Manager |

---

## DBeaver setup (SSM tunnel)

### 1) Get DB credentials

```bash
bash infra/aws/db-tunnel.sh --show-creds
```

### 2) Start the tunnel (keep terminal open)

```bash
bash infra/aws/db-tunnel.sh
```

### 3) DBeaver connection

**Main tab**

| Field | Value |
|-------|--------|
| Host | `localhost` |
| Port | `5432` |
| Database | `get1agent` |
| Username | `get1agent` (master) |
| Password | from `--show-creds` |

**SSL** → enable, mode `require`

**SSH tab** → **disabled** (do not use SSH tunnel in DBeaver)

Test connection → Finish.

### Session Manager plugin

If `db-tunnel.sh` fails with a plugin error:

```bash
brew install --cask session-manager-plugin
```

---

## Scripts

| Script | Purpose |
|--------|---------|
| `infra/aws/deploy-infra.sh` | Terraform: EC2 + RDS + ECR |
| `infra/aws/deploy-control-plane.sh` | Docker build → ECR → EC2 (via SSM) |
| `infra/aws/sync-ec2-api.sh` | Upload nginx/deploy scripts and restart API on EC2 |
| `infra/aws/deploy-all.sh` | Both in one command |
| `infra/aws/db-tunnel.sh` | SSM tunnel to RDS for DBeaver |
| `infra/aws/db-tunnel.sh --show-creds` | Print DBeaver credentials |

---

## Troubleshooting: `/health` not reachable

**Symptom:** `curl https://api.get1agent.com/health` → timeout.

| Symptom | Likely cause |
|---------|----------------|
| Connection **refused** | nginx or container not running |
| **Timeout** | Cloudflare DNS or security group port **80** |

### Step 1 — Connect to EC2 via Session Manager

AWS Console → **EC2** → select the app instance → **Connect** → **Session Manager** → **Connect**.

### Step 2 — Check if the container is running

```bash
sudo docker ps -a
sudo docker logs get1agent-api --tail 50
sudo systemctl status nginx
curl -s localhost:8000/health
curl -s localhost/health
```

**If container is missing:**

```bash
sudo /opt/get1agent/deploy-api.sh
```

Or re-run:

```bash
bash infra/aws/deploy-control-plane.sh
```

---

## Troubleshooting: Terraform Infra job

### Stuck on "Acquiring state lock"

A previous run left the lock file in S3. Cancel the stuck job, then:

```bash
cd infra/terraform/envs/dev
terraform init
terraform force-unlock <LOCK_ID>
# or: aws s3 rm s3://get1agent-terraform-state-us-east-1/envs/dev/terraform.tfstate.tflock
```

### Duplicate security group rule

If apply fails with `InvalidPermission.Duplicate` on postgres port 5432, pull latest `main` — postgres ingress is managed inline on the SG, not as a separate rule.

---

## Local development

Uses password auth (not IAM):

```bash
cd control_plane
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

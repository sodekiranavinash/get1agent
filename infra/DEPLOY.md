# Deploy get1agent on AWS

**EC2** runs `control_plane` (FastAPI). **RDS** is private. The app connects with **IAM** (no DB password). Master password is **DBeaver / tunnel only**.

---

## Quick start (from your Mac)

### 1) One-time setup

```bash
aws configure
# Get your IP:
curl -s ifconfig.me
```

### 2) Deploy everything

```bash
DATA_PLANE_SSH_CIDR=YOUR.IP/32 bash infra/aws/deploy-all.sh
```

Or step by step:

```bash
DATA_PLANE_SSH_CIDR=YOUR.IP/32 bash infra/aws/deploy-infra.sh apply
bash infra/aws/deploy-control-plane.sh
```

### 3) Verify

```bash
curl -s http://<app-ip>/health
curl -s http://<app-ip>/ready    # DB via IAM — should show database: ok
```

After Cloudflare DNS (`api` A record → app IP, proxied):

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

Terraform opens **port 80** on the app security group. Port **8000** is not exposed publicly (FastAPI binds to localhost only).

---

## GitHub Actions (alternative)

### Secrets (Settings → Actions)

| Secret | Example |
|--------|---------|
| `AWS_ACCESS_KEY_ID` | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | `...` |
| `DATA_PLANE_SSH_CIDR` | `203.0.113.10` or `203.0.113.10/32` (your public IP) |

### Workflows

1. **Infra** — Terraform (EC2 + RDS + ECR)
2. **Deploy control_plane** — builds `control_plane/` → ECR → EC2

---

## Auth model

| Who | How it connects to Postgres |
|-----|----------------------------|
| **control_plane on EC2** | IAM role → `rds-db:connect` → user `get1agent_app` (no password) |
| **DBeaver / you** | SSH tunnel via EC2 → master user `get1agent` + password from Secrets Manager |

---

## DBeaver setup

### Save SSH key (once)

```bash
cd infra/terraform/envs/dev && terraform init
bash ../../../aws/fetch-app-ssh-key.sh
```

### Get DB password (master user — not used by the app)

```bash
bash infra/aws/db-tunnel.sh --show-creds
```

### DBeaver connection

**Main tab**

| Field | Value |
|-------|--------|
| Host | RDS host from secret |
| Port | `5432` |
| Database | `get1agent` |
| Username | `get1agent` (master) |
| Password | from secret |

**SSL** → enable, mode `require`

**SSH tab**

| Field | Value |
|-------|--------|
| Use SSH Tunnel | ✓ |
| Host | App EC2 public IP |
| Port | `22` |
| User | `ec2-user` |
| Private key | `~/.ssh/get1agent-dev-app.pem` |

Test connection → Finish.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `infra/aws/deploy-infra.sh` | Terraform: EC2 + RDS + ECR |
| `infra/aws/deploy-control-plane.sh` | Docker build → ECR → EC2 (nginx + API via SSM) |
| `infra/aws/sync-ec2-api.sh` | Upload nginx/deploy scripts and restart API on EC2 |
| `infra/aws/deploy-all.sh` | Both in one command |
| `infra/aws/db-tunnel.sh --show-creds` | Print DBeaver credentials |
| `infra/aws/fetch-app-ssh-key.sh` | Save SSH key for DBeaver |

---

## Troubleshooting: `/health` not reachable

**Symptom:** `curl http://<app-ip>/health` → *connection refused* or timeout.

| Symptom | Likely cause |
|---------|----------------|
| Connection **refused** | nginx or container not running |
| **Timeout** | Security group — check port **80** inbound and Elastic IP |

### Step 1 — Confirm the IP

```bash
cd infra/terraform/envs/dev && terraform init
terraform output api_base_url
```

Use that IP in your browser/curl.

### Step 2 — Connect to EC2 (no SSH key needed)

AWS Console → **EC2** → select the app instance → **Connect** → **Session Manager** → **Connect**.

### Step 3 — Check if the container is running

```bash
sudo docker ps -a
sudo docker logs get1agent-api --tail 50
sudo systemctl status nginx
curl -s localhost:8000/health
curl -s localhost/health
```

**If logs show `exec format error`:** the image was built for the wrong CPU (amd64 on ARM t4g). Re-run deploy after the ARM64 build fix:

```bash
bash infra/aws/deploy-control-plane.sh
```

Or re-run the **Deploy control_plane** GitHub Action.

**If container is missing:** run deploy manually on the instance:

```bash
sudo /opt/get1agent/deploy-api.sh
```

### Step 4 — Check security group (only if timeout, not refused)

EC2 → instance → **Security** tab → inbound rules must include **TCP 80** from your network (default `0.0.0.0/0`).

---

## Local development

Uses password auth (not IAM):

```bash
cd control_plane
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

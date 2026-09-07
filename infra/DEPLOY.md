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
curl -s http://<app-ip>:8000/health
curl -s http://<app-ip>:8000/ready    # DB via IAM — should show database: ok
```

---

## GitHub Actions (alternative)

### Secrets (Settings → Actions)

| Secret | Example |
|--------|---------|
| `AWS_ACCESS_KEY_ID` | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | `...` |
| `DATA_PLANE_SSH_CIDR` | `203.0.113.10/32` |

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
| `infra/aws/deploy-control-plane.sh` | Docker build → ECR → SSM restart |
| `infra/aws/deploy-all.sh` | Both in one command |
| `infra/aws/db-tunnel.sh --show-creds` | Print DBeaver credentials |
| `infra/aws/fetch-app-ssh-key.sh` | Save SSH key for DBeaver |

---

## Local development

Uses password auth (not IAM):

```bash
cd control_plane
cp .env.example .env
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

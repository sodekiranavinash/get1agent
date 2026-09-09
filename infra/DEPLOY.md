# Deploy get1agent on AWS

**Kong Gateway OSS** runs on EC2 and routes traffic from `api.get1agent.com` to backend services (Lambdas added later). **RDS** is private. Kong connects to Postgres with **IAM auth** (user `kong_app`, database `kong`). Master password is **DBeaver / SSM tunnel only**.

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
bash infra/aws/deploy-kong.sh
```

### 3) Cloudflare DNS

Point both records to the Kong EC2 Elastic IP (`terraform output app_public_ip`):

| Record | Type | Target | Proxied |
|--------|------|--------|---------|
| `api` | A | Kong EC2 IP | Yes (orange cloud) |
| `kong` | A | Kong EC2 IP | Yes (orange cloud) |

Cloudflare SSL/TLS → **Flexible** (same as www S3 site).

### 4) Get Kong Manager UI credentials

```bash
bash infra/aws/kong-admin-creds.sh
```

Open **https://kong.get1agent.com** and sign in with the `admin` username and password from Secrets Manager.

---

## Architecture

```
Internet
  → Cloudflare (api.get1agent.com, kong.get1agent.com)
  → EC2 Elastic IP (port 80, Cloudflare IPs only)
  → Kong Gateway OSS (:80 proxy, :8001 admin, :8002 manager)
  → RDS PostgreSQL (private, databases: get1agent + kong)
```

| Port | Who can connect |
|------|-----------------|
| **80** | Cloudflare IPs only (Kong proxy) |
| **8001** | localhost only (Kong Admin API) |
| **8002** | localhost only (Kong Manager; exposed via route on kong.get1agent.com) |
| **5432** | EC2 only (RDS private) |

No nginx. Kong listens on port 80 directly.

Admin access to EC2 and RDS uses **AWS SSM** (no SSH keys, no home IP allowlist).

---

## GitHub Actions (alternative)

### Secrets (Settings → Actions)

| Secret | Example |
|--------|---------|
| `AWS_ACCESS_KEY_ID` | `AKIA...` |
| `AWS_SECRET_ACCESS_KEY` | `...` |

### Workflows

1. **Infra** — Terraform (Kong EC2 + RDS)
2. **Deploy Kong** — sync scripts and restart Kong on EC2 via SSM

---

## Auth model

| Who | How it connects to Postgres |
|-----|----------------------------|
| **Kong on EC2** | IAM role → `rds-db:connect` → user `kong_app` on database `kong` |
| **Future Lambdas** | IAM → `rds-db:connect` → user `get1agent_app` on database `get1agent` |
| **DBeaver / you** | SSM tunnel → master user `get1agent` + password from Secrets Manager |

Kong Manager UI is protected with **basic-auth** (credentials in `get1agent-dev/kong-admin-credentials`).

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

Default local port is **15432**.

### 3) DBeaver connection

| Field | Value |
|-------|--------|
| Host | `localhost` |
| Port | `15432` |
| Database | `get1agent` or `kong` |
| Username | `get1agent` (master) |
| Password | from `--show-creds` |

**SSH tab** → disabled. **SSL** → `require`.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `infra/aws/deploy-infra.sh` | Terraform: Kong EC2 + RDS |
| `infra/aws/deploy-kong.sh` | Sync Kong scripts and restart on EC2 |
| `infra/aws/deploy-all.sh` | Both in one command |
| `infra/aws/kong-admin-creds.sh` | Print Kong Manager UI login |
| `infra/aws/db-tunnel.sh` | SSM tunnel to RDS for DBeaver |

---

## Adding API routes (later)

Configure services and routes in **Kong Manager** at https://kong.get1agent.com, or via the Admin API on the EC2 instance (`curl http://127.0.0.1:8001/...` via SSM).

Example: route `api.get1agent.com/my-service` → Lambda function URL or ALB.

---

## Troubleshooting

### Kong not reachable

```bash
# SSM into EC2, then:
sudo docker ps -a
sudo docker logs get1agent-kong --tail 50
curl -s http://127.0.0.1:8001/status
sudo systemctl status get1agent-kong
```

Restart:

```bash
bash infra/aws/deploy-kong.sh
```

### Terraform stuck on state lock

```bash
cd infra/terraform/envs/dev
terraform init
terraform force-unlock <LOCK_ID>
```

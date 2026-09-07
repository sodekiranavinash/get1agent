#!/usr/bin/env bash
# Compare your public IP with the EC2 security group admin allowlist (SSH + HTTP).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TFVARS="$ROOT/infra/terraform/envs/dev/terraform.tfvars"
ENV_DIR="$ROOT/infra/terraform/envs/dev"

CURRENT_IP="$(curl -sf --max-time 10 ifconfig.me || curl -sf --max-time 10 api.ipify.org)"
if [[ -z "$CURRENT_IP" ]]; then
  echo "Could not detect your public IP." >&2
  exit 1
fi

echo "Your public IP:     $CURRENT_IP"

if [[ ! -f "$TFVARS" ]]; then
  echo "terraform.tfvars:   (missing)"
  echo ""
  echo "Fix: DATA_PLANE_SSH_CIDR=${CURRENT_IP}/32 bash infra/aws/deploy-infra.sh apply"
  exit 1
fi

ALLOWED="$(grep -E 'data_plane_ssh_cidr_blocks' "$TFVARS" || true)"
echo "terraform.tfvars:   $ALLOWED"

if grep -q "${CURRENT_IP}/32" "$TFVARS" || grep -q "\"${CURRENT_IP}\"" "$TFVARS"; then
  echo "Status:             IP is allowed for SSH (port 22) and direct HTTP (port 80)"
else
  echo "Status:             IP is NOT in the allowlist — SSH/DBeaver will time out"
  echo ""
  echo "Fix: bash infra/aws/update-admin-ip.sh"
fi

cd "$ENV_DIR"
if terraform output -raw app_public_ip &>/dev/null; then
  APP_IP="$(terraform output -raw app_public_ip)"
  echo ""
  echo "DBeaver SSH host:   $APP_IP  (NOT api.get1agent.com)"
  echo "API via Cloudflare: https://$(terraform output -raw api_public_hostname 2>/dev/null || echo api.get1agent.com)"
fi

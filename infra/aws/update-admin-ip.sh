#!/usr/bin/env bash
# Update EC2 security group to allow your current public IP (SSH + HTTP).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

CURRENT_IP="$(curl -sf --max-time 10 ifconfig.me || curl -sf --max-time 10 api.ipify.org)"
if [[ -z "$CURRENT_IP" ]]; then
  echo "Could not detect your public IP." >&2
  exit 1
fi

echo "Adding ${CURRENT_IP}/32 to admin allowlist (SSH port 22 + HTTP port 80) ..."
DATA_PLANE_SSH_CIDR="${CURRENT_IP}/32" bash "$ROOT/infra/aws/deploy-infra.sh" apply

echo ""
echo "DBeaver SSH host (EC2 IP, not api.get1agent.com):"
cd "$ROOT/infra/terraform/envs/dev" && terraform output -raw app_public_ip

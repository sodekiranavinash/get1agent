#!/usr/bin/env bash
# Restart Kong on EC2 via SSM (pull latest image, refresh IAM token, re-run bootstrap).
#
# Usage:
#   bash infra/aws/deploy-kong.sh
#
# Requires infra deployed first (deploy-infra.sh or GitHub Infra workflow).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
AWS_REGION="${AWS_REGION:-us-east-1}"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

if ! terraform output -raw app_instance_id >/dev/null 2>&1; then
  echo "Data plane not found. Run: bash infra/aws/deploy-infra.sh apply" >&2
  exit 1
fi

INSTANCE_ID="$(terraform output -raw app_instance_id)"
API_URL="$(terraform output -raw api_base_url)"
API_HOST="$(terraform output -raw api_public_hostname)"
KONG_UI="$(terraform output -raw kong_ui_hostname)"

echo "Instance: $INSTANCE_ID"
echo "Syncing Kong scripts and restarting..."

bash "$ROOT/infra/aws/sync-ec2-kong.sh"

echo ""
echo "=== Kong deployed ==="
echo "API proxy:  https://${API_HOST}"
echo "Kong UI:    https://${KONG_UI}"
echo "Admin creds: bash infra/aws/kong-admin-creds.sh"
echo ""
echo "Verify: curl -s ${API_URL} (expect Kong 'no Route matched' until services are added)"

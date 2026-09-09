#!/usr/bin/env bash
# Deploy AWS infrastructure (Terraform): bootstrap + web + dev (Kong EC2, RDS).
#
# Usage:
#   bash infra/aws/deploy-infra.sh plan
#   bash infra/aws/deploy-infra.sh apply
#
# Requires AWS CLI configured.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODE="${1:-apply}"
TFVARS="$ROOT/infra/terraform/envs/dev/terraform.tfvars"

if [[ "$MODE" != "plan" && "$MODE" != "apply" ]]; then
  echo "usage: $0 <plan|apply>" >&2
  exit 2
fi

cat >"$TFVARS" <<EOF
aws_region   = "us-east-1"
package_path = "../../../../tools/challan-extractor/dist/function.zip"
enable_data_plane = true
EOF

if [[ ! -s "$ROOT/tools/challan-extractor/dist/function.zip" ]]; then
  echo "Packaging challan-extractor Lambda zip..."
  make -C "$ROOT/tools/challan-extractor" package
fi

bash "$ROOT/infra/aws/run-terraform.sh" bootstrap "$MODE"
bash "$ROOT/infra/aws/run-terraform.sh" web "$MODE"
bash "$ROOT/infra/aws/run-terraform.sh" dev "$MODE"

if [[ "$MODE" == "apply" ]]; then
  cd "$ROOT/infra/terraform/envs/dev"
  terraform init -input=false >/dev/null
  echo ""
  echo "=== Infra deployed ==="
  echo "Kong IP:     $(terraform output -raw app_public_ip 2>/dev/null || echo n/a)"
  echo "API domain:  $(terraform output -raw api_public_hostname 2>/dev/null || echo n/a)"
  echo "Kong UI:     $(terraform output -raw kong_ui_hostname 2>/dev/null || echo n/a)"
  echo "RDS host:    $(terraform output -raw postgres_endpoint 2>/dev/null || echo n/a)"
  echo "DB tunnel:   bash infra/aws/db-tunnel.sh"
  echo ""
  echo "Cloudflare DNS (both proxied A records -> Kong IP above):"
  echo "  api  -> api.get1agent.com"
  echo "  kong -> kong.get1agent.com"
  echo ""
  echo "Kong admin:  bash infra/aws/kong-admin-creds.sh"
  echo "Next:        bash infra/aws/deploy-kong.sh"
fi

#!/usr/bin/env bash
# Deploy AWS infrastructure (Terraform): bootstrap + web + prod.
#
# Usage:
#   bash infra/aws/deploy-infra.sh plan
#   bash infra/aws/deploy-infra.sh apply
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODE="${1:-apply}"
TFVARS="$ROOT/infra/terraform/envs/prod/terraform.tfvars"

if [[ "$MODE" != "plan" && "$MODE" != "apply" ]]; then
  echo "usage: $0 <plan|apply>" >&2
  exit 2
fi

cat >"$TFVARS" <<EOF
aws_region               = "us-east-1"
package_path             = "../../../../tools/challan-extractor/dist/function.zip"
enable_data_plane        = true
enable_api_custom_domain = true
EOF

if [[ ! -s "$ROOT/tools/challan-extractor/dist/function.zip" ]]; then
  echo "Packaging challan-extractor Lambda zip..."
  make -C "$ROOT/tools/challan-extractor" package
fi

if [[ ! -s "$ROOT/backend/health-check/dist/function.zip" ]]; then
  echo "Packaging backend health-check Lambda zip..."
  make -C "$ROOT/backend/health-check" package
fi

bash "$ROOT/infra/aws/run-terraform.sh" bootstrap "$MODE"
bash "$ROOT/infra/aws/run-terraform.sh" web "$MODE"
bash "$ROOT/infra/aws/run-terraform.sh" prod "$MODE"

if [[ "$MODE" == "apply" ]]; then
  cd "$ROOT/infra/terraform/envs/prod"
  terraform init -input=false >/dev/null
  echo ""
  echo "=== Infra deployed ==="
  echo "API URL:     $(terraform output -raw api_url 2>/dev/null || echo n/a)"
  echo "API CNAME:   $(terraform output -raw api_gateway_cname_target 2>/dev/null || echo n/a)"
  echo "RDS host:    $(terraform output -raw postgres_endpoint 2>/dev/null || echo n/a)"
  echo "DB tunnel:   bash infra/aws/db-tunnel.sh"
  echo ""
  echo "Auth0 API identifier: https://api.get1agent.com"
fi

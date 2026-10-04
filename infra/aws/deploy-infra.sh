#!/usr/bin/env bash
# Deploy AWS infrastructure (Terraform): bootstrap + web + full prod.
#
# Usage:
#   bash infra/aws/deploy-infra.sh plan
#   bash infra/aws/deploy-infra.sh apply
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODE="${1:-apply}"

if [[ "$MODE" != "plan" && "$MODE" != "apply" ]]; then
  echo "usage: $0 <plan|apply>" >&2
  exit 2
fi

bash "$ROOT/infra/aws/write-prod-tfvars.sh"

# Note: Lambda layers are deprecated. Dependencies are now bundled with each Lambda.
# See MIGRATION_SUMMARY.md for details.

# Package every backend Lambda zip that is missing. Paths come from
# backend/registry.json, so moving a service never requires editing this script.
while IFS= read -r dir; do
  if [[ ! -s "$ROOT/$dir/dist/function.zip" ]]; then
    echo "Packaging $dir Lambda zip..."
    make -C "$ROOT/$dir" package
  fi
done < <(python3 -c "
import json, os
with open(os.path.join('$ROOT', 'backend', 'registry.json'), encoding='utf-8') as f:
    for app in json.load(f)['apps']:
        print(app['dir'])
")

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
  echo "DynamoDB:    $(terraform output -raw dynamodb_table_name 2>/dev/null || echo n/a)"
  echo "Vectors:     $(terraform output -raw vector_bucket_name 2>/dev/null || echo n/a)"
  echo ""
  echo "Auth0 API identifier: https://api.get1agent.com"
fi

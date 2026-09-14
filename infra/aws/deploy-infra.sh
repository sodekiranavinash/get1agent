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

if [[ ! -s "$ROOT/backend/services/layers/data/dist/layer.zip" ]]; then
  echo "Building backend data Lambda layer..."
  bash "$ROOT/infra/aws/build-backend-layers.sh"
fi

if [[ ! -s "$ROOT/backend/services/layers/ai/dist/layer.zip" ]]; then
  echo "Building backend ai Lambda layer..."
  bash "$ROOT/infra/aws/build-backend-layers.sh" ai
fi

for service in user-api knowledge-mcp ingestion-dispatcher ingestion-extract \
  ingestion-embed ingestion-index ingestion-mark-failed ingestion-watchdog; do
  if [[ ! -s "$ROOT/backend/services/$service/dist/function.zip" ]]; then
    echo "Packaging backend $service Lambda zip..."
    make -C "$ROOT/backend/services/$service" package
  fi
done

if [[ ! -s "$ROOT/backend/services/admin/mcp-tester/dist/function.zip" ]]; then
  echo "Packaging backend mcp-tester Lambda zip..."
  make -C "$ROOT/backend/services/admin/mcp-tester" package
fi

if [[ ! -s "$ROOT/backend/tools/code-interpreter/dist/function.zip" ]]; then
  echo "Packaging code-interpreter Lambda zip..."
  make -C "$ROOT/backend/tools/code-interpreter" package
fi

if [[ ! -s "$ROOT/backend/tools/web-search/dist/function.zip" ]]; then
  echo "Packaging web-search Lambda zip..."
  make -C "$ROOT/backend/tools/web-search" package
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
  echo "DynamoDB:    $(terraform output -raw dynamodb_table_name 2>/dev/null || echo n/a)"
  echo "Vectors:     $(terraform output -raw vector_bucket_name 2>/dev/null || echo n/a)"
  echo ""
  echo "Auth0 API identifier: https://api.get1agent.com"
fi

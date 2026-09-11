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

if [[ ! -s "$ROOT/tools/challan-extractor/dist/function.zip" ]]; then
  echo "Packaging challan-extractor Lambda zip..."
  make -C "$ROOT/tools/challan-extractor" package
fi

if [[ ! -s "$ROOT/backend/layers/data/dist/layer.zip" ]]; then
  echo "Building backend data Lambda layer..."
  bash "$ROOT/infra/aws/build-backend-layers.sh"
fi

if [[ ! -s "$ROOT/backend/health-check/dist/function.zip" ]]; then
  echo "Packaging backend health-check Lambda zip..."
  make -C "$ROOT/backend/health-check" package
fi

if [[ ! -s "$ROOT/backend/migration-runner/dist/function.zip" ]]; then
  echo "Packaging backend migration-runner Lambda zip..."
  make -C "$ROOT/backend/migration-runner" package
fi

if [[ ! -s "$ROOT/backend/account-settings/dist/function.zip" ]]; then
  echo "Packaging backend account-settings Lambda zip..."
  make -C "$ROOT/backend/account-settings" package
fi

if [[ ! -s "$ROOT/backend/knowledge-bases/dist/function.zip" ]]; then
  echo "Packaging backend knowledge-bases Lambda zip..."
  make -C "$ROOT/backend/knowledge-bases" package
fi

if [[ ! -s "$ROOT/backend/ingestion-dispatcher/dist/function.zip" ]]; then
  echo "Packaging backend ingestion-dispatcher Lambda zip..."
  make -C "$ROOT/backend/ingestion-dispatcher" package
fi

if [[ ! -s "$ROOT/backend/ingestion-extract/dist/function.zip" ]]; then
  echo "Packaging backend ingestion-extract Lambda zip..."
  make -C "$ROOT/backend/ingestion-extract" package
fi

if [[ ! -s "$ROOT/backend/ingestion-index/dist/function.zip" ]]; then
  echo "Packaging backend ingestion-index Lambda zip..."
  make -C "$ROOT/backend/ingestion-index" package
fi

if [[ ! -s "$ROOT/backend/ingestion-mark-failed/dist/function.zip" ]]; then
  echo "Packaging backend ingestion-mark-failed Lambda zip..."
  make -C "$ROOT/backend/ingestion-mark-failed" package
fi

bash "$ROOT/infra/aws/run-terraform.sh" bootstrap "$MODE"
bash "$ROOT/infra/aws/run-terraform.sh" web "$MODE"
bash "$ROOT/infra/aws/run-terraform.sh" prod "$MODE"

if [[ "$MODE" == "apply" ]]; then
  bash "$ROOT/infra/aws/bootstrap-db-iam-user.sh" || true
  cd "$ROOT/infra/terraform/envs/prod"
  terraform init -input=false >/dev/null
  echo ""
  echo "=== Infra deployed ==="
  echo "API URL:     $(terraform output -raw api_url 2>/dev/null || echo n/a)"
  echo "API CNAME:   $(terraform output -raw api_gateway_cname_target 2>/dev/null || echo n/a)"
  echo "RDS host:    $(terraform output -raw postgres_endpoint 2>/dev/null || echo n/a)"
  echo "DB access:   bash infra/aws/db-access.sh  (starts jumpbox only while in use)"
  JUMPBOX_ID="$(terraform output -raw jumpbox_instance_id 2>/dev/null || true)"
  if [[ -n "$JUMPBOX_ID" ]]; then
    echo "Jumpbox ${JUMPBOX_ID} left running. Access: bash infra/aws/db-access.sh"
  fi
  echo ""
  echo "Auth0 API identifier: https://api.get1agent.com"
fi

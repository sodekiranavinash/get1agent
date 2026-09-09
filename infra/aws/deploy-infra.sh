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
    aws ec2 stop-instances --region "${AWS_REGION:-ap-south-1}" --instance-ids "$JUMPBOX_ID" >/dev/null 2>&1 || true
  fi
  echo ""
  echo "Auth0 API identifier: https://api.get1agent.com"
fi

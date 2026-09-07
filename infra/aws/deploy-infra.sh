#!/usr/bin/env bash
# Deploy AWS infrastructure (Terraform): bootstrap + web + dev (EC2, RDS, ECR).
#
# Usage:
#   bash infra/aws/deploy-infra.sh plan
#   bash infra/aws/deploy-infra.sh apply
#
# Requires:
#   - AWS CLI configured
#   - DATA_PLANE_SSH_CIDR in environment OR infra/terraform/envs/dev/terraform.tfvars
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
MODE="${1:-apply}"

if [[ "$MODE" != "plan" && "$MODE" != "apply" ]]; then
  echo "usage: $0 <plan|apply>" >&2
  exit 2
fi

if [[ -z "${DATA_PLANE_SSH_CIDR:-}" && ! -f "$ROOT/infra/terraform/envs/dev/terraform.tfvars" ]]; then
  echo "Set DATA_PLANE_SSH_CIDR or create infra/terraform/envs/dev/terraform.tfvars" >&2
  echo "Example: DATA_PLANE_SSH_CIDR=203.0.113.10/32 $0 apply" >&2
  exit 1
fi

if [[ -n "${DATA_PLANE_SSH_CIDR:-}" ]]; then
  mapfile -t ALLOWED < <(bash "$ROOT/infra/aws/tfvars-ssh-cidr.sh" "$DATA_PLANE_SSH_CIDR")
  echo "Updated terraform.tfvars admin IPs: ${ALLOWED[*]}"
fi

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
  echo "App IP:      $(terraform output -raw app_public_ip 2>/dev/null || echo n/a)"
  echo "API URL:     $(terraform output -raw api_base_url 2>/dev/null || echo n/a)"
  echo "API domain:  $(terraform output -raw api_public_hostname 2>/dev/null || echo n/a)"
  echo "RDS host:    $(terraform output -raw postgres_endpoint 2>/dev/null || echo n/a)"
  echo ""
  echo "Next: bash infra/aws/deploy-control-plane.sh"
fi

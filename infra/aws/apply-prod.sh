#!/usr/bin/env bash
# Targeted prod apply. Set any of these to "true" to include that component:
#   APPLY_NETWORK APPLY_RDS APPLY_API_GATEWAY APPLY_BACKEND_LAMBDAS APPLY_TOOL_LAMBDAS
# If none are set, runs a full prod apply.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

bash "$ROOT/infra/aws/write-prod-tfvars.sh"

TARGETS=()
[[ "${APPLY_NETWORK:-false}" == "true" ]] && TARGETS+=(-target=module.network)
[[ "${APPLY_RDS:-false}" == "true" ]] && {
  TARGETS+=(-target=module.rds)
  TARGETS+=(-target=module.network)
}
[[ "${APPLY_API_GATEWAY:-false}" == "true" ]] && TARGETS+=(-target=module.api_gateway)
[[ "${APPLY_BACKEND_LAMBDAS:-false}" == "true" ]] && {
  TARGETS+=(-target=module.health_check)
  TARGETS+=(-target=module.network)
  TARGETS+=(-target=module.rds)
}
[[ "${APPLY_TOOL_LAMBDAS:-false}" == "true" ]] && TARGETS+=(-target=module.challan_extractor)

need_tool_zip=false
need_health_zip=false
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  need_tool_zip=true
  need_health_zip=true
else
  [[ "${APPLY_BACKEND_LAMBDAS:-false}" == "true" ]] && need_health_zip=true
  [[ "${APPLY_TOOL_LAMBDAS:-false}" == "true" ]] && need_tool_zip=true
fi

if [[ "$need_tool_zip" == true && ! -s "$ROOT/tools/challan-extractor/dist/function.zip" ]]; then
  make -C "$ROOT/tools/challan-extractor" package
fi
if [[ "$need_health_zip" == true && ! -s "$ROOT/backend/health-check/dist/function.zip" ]]; then
  make -C "$ROOT/backend/health-check" package
fi

export PROD_TARGETS="${TARGETS[*]}"
bash "$ROOT/infra/aws/run-terraform.sh" prod apply

if [[ "${APPLY_RDS:-false}" == "true" || ${#TARGETS[@]} -eq 0 ]]; then
  bash "$ROOT/infra/aws/bootstrap-db-iam-user.sh"
fi

if [[ "${APPLY_NETWORK:-false}" == "true" || ${#TARGETS[@]} -eq 0 ]]; then
  cd "$ROOT/infra/terraform/envs/prod"
  terraform init -input=false >/dev/null
  JUMPBOX_ID="$(terraform output -raw jumpbox_instance_id 2>/dev/null || true)"
  if [[ -n "$JUMPBOX_ID" ]]; then
    aws ec2 stop-instances --region "${AWS_REGION:-us-east-1}" --instance-ids "$JUMPBOX_ID" >/dev/null 2>&1 || true
  fi
fi

#!/usr/bin/env bash
# Targeted prod apply. Set any of these to "true" to include that component:
#   APPLY_NETWORK APPLY_RDS APPLY_API_GATEWAY APPLY_BACKEND_LAMBDAS
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
# health-check only needs existing VPC/RDS in state — do not -target module.network (pulls jumpbox).
[[ "${APPLY_BACKEND_LAMBDAS:-false}" == "true" ]] && {
  TARGETS+=(-target='module.layer_data[0]')
  TARGETS+=(-target='module.health_check[0]')
  TARGETS+=(-target='module.account_settings[0]')
  TARGETS+=(-target='module.knowledge_storage[0]')
  TARGETS+=(-target='module.knowledge_bases[0]')
  TARGETS+=(-target='module.ingestion_extract[0]')
  TARGETS+=(-target='module.ingestion_embed[0]')
  TARGETS+=(-target='module.ingestion_index[0]')
  TARGETS+=(-target='module.ingestion_mark_failed[0]')
  TARGETS+=(-target='module.ingestion_watchdog[0]')
  TARGETS+=(-target='module.ingestion[0]')
  TARGETS+=(-target='module.ingestion_dispatcher[0]')
}

need_backend_artifacts=false
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  need_backend_artifacts=true
else
  [[ "${APPLY_BACKEND_LAMBDAS:-false}" == "true" ]] && need_backend_artifacts=true
fi

if [[ "$need_backend_artifacts" == true ]]; then
  if [[ ! -s "$ROOT/backend/services/layers/data/dist/layer.zip" ]]; then
    bash "$ROOT/infra/aws/build-backend-layers.sh"
  fi
  if [[ ! -s "$ROOT/backend/services/health-check/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/health-check" package
  fi
  if [[ ! -s "$ROOT/backend/services/account-settings/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/account-settings" package
  fi
  if [[ ! -s "$ROOT/backend/services/knowledge-bases/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/knowledge-bases" package
  fi
  if [[ ! -s "$ROOT/backend/services/ingestion-dispatcher/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/ingestion-dispatcher" package
  fi
  if [[ ! -s "$ROOT/backend/services/ingestion-extract/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/ingestion-extract" package
  fi
  if [[ ! -s "$ROOT/backend/services/ingestion-embed/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/ingestion-embed" package
  fi
  if [[ ! -s "$ROOT/backend/services/ingestion-index/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/ingestion-index" package
  fi
  if [[ ! -s "$ROOT/backend/services/ingestion-mark-failed/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/ingestion-mark-failed" package
  fi
  if [[ ! -s "$ROOT/backend/services/ingestion-watchdog/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/ingestion-watchdog" package
  fi
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
    echo "Jumpbox ${JUMPBOX_ID} left running. Access: bash infra/aws/db-access.sh"
  fi
fi

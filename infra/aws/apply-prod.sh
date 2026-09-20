#!/usr/bin/env bash
# Targeted prod apply. Set any of these to "true" to include that component:
#   APPLY_API_GATEWAY APPLY_BACKEND_LAMBDAS
# If none are set, runs a full prod apply.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

bash "$ROOT/infra/aws/write-prod-tfvars.sh"

TARGETS=()
[[ "${APPLY_API_GATEWAY:-false}" == "true" ]] && TARGETS+=(-target=module.api_gateway)
[[ "${APPLY_BACKEND_LAMBDAS:-false}" == "true" ]] && {
  TARGETS+=(-target='module.layer_base[0]')
  TARGETS+=(-target='module.layer_genai[0]')
  TARGETS+=(-target='module.layer_extra_tools[0]')
  TARGETS+=(-target='module.database[0]')
  TARGETS+=(-target='module.vectors[0]')
  TARGETS+=(-target='module.knowledge_storage[0]')
  TARGETS+=(-target='module.user_api[0]')
  TARGETS+=(-target='module.knowledge_mcp[0]')
  TARGETS+=(-target='module.ingestion_extract[0]')
  TARGETS+=(-target='module.ingestion_embed[0]')
  TARGETS+=(-target='module.ingestion_index[0]')
  TARGETS+=(-target='module.ingestion_mark_failed[0]')
  TARGETS+=(-target='module.ingestion_watchdog[0]')
  TARGETS+=(-target='module.ingestion[0]')
  TARGETS+=(-target='module.ingestion_dispatcher[0]')
  TARGETS+=(-target='module.mcp_tester[0]')
  TARGETS+=(-target='module.code_interpreter[0]')
  TARGETS+=(-target='module.web_search[0]')
  TARGETS+=(-target='module.mcp_connections_kms[0]')
  TARGETS+=(-target='module.mcp_connections[0]')
}

need_backend_artifacts=false
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  need_backend_artifacts=true
else
  [[ "${APPLY_BACKEND_LAMBDAS:-false}" == "true" ]] && need_backend_artifacts=true
fi

if [[ "$need_backend_artifacts" == true ]]; then
  for layer in base genai extra-tools; do
    if [[ ! -s "$ROOT/backend/services/dependency-layers/$layer/dist/layer.zip" ]]; then
      bash "$ROOT/infra/aws/build-backend-layers.sh"
      break
    fi
  done
  for service in user-api knowledge-mcp ingestion-dispatcher ingestion-extract \
    ingestion-embed ingestion-index ingestion-mark-failed ingestion-watchdog; do
    if [[ ! -s "$ROOT/backend/services/$service/dist/function.zip" ]]; then
      make -C "$ROOT/backend/services/$service" package
    fi
  done
  if [[ ! -s "$ROOT/backend/services/mcp-tester/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/mcp-tester" package
  fi
  if [[ ! -s "$ROOT/backend/services/code-interpreter/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/code-interpreter" package
  fi
  if [[ ! -s "$ROOT/backend/services/web-search/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/web-search" package
  fi
  if [[ ! -s "$ROOT/backend/services/mcp-connections/dist/function.zip" ]]; then
    make -C "$ROOT/backend/services/mcp-connections" package
  fi
fi

export PROD_TARGETS="${TARGETS[*]:-}"
bash "$ROOT/infra/aws/run-terraform.sh" prod apply

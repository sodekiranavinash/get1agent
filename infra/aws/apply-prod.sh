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
  # No Lambda layers: dependencies are bundled per Lambda (see registry.json).
  # The agent runtime is intentionally NOT targeted here — it needs a pushed
  # container image and is applied by deploy-agent-runtime.sh (which passes
  # agent_worker_image_uri); targeting it without that var would destroy it.
  TARGETS+=(-target='module.database[0]')
  TARGETS+=(-target='module.vectors[0]')
  TARGETS+=(-target='module.knowledge_storage[0]')
  TARGETS+=(-target='module.vault_kms[0]')
  TARGETS+=(-target='module.mcp_connections_kms[0]')
  TARGETS+=(-target='module.user_api[0]')
  TARGETS+=(-target='module.knowledge_mcp[0]')
  TARGETS+=(-target='module.mcp_tester[0]')
  TARGETS+=(-target='module.code_interpreter[0]')
  TARGETS+=(-target='module.http_fetch[0]')
  TARGETS+=(-target='module.custom_tools[0]')
  TARGETS+=(-target='module.browser[0]')
  TARGETS+=(-target='module.mcp_connections[0]')
  TARGETS+=(-target='module.scheduler[0]')
  TARGETS+=(-target='module.ingestion[0]')
  TARGETS+=(-target='module.ingestion_dispatcher[0]')
  TARGETS+=(-target='module.ingestion_extract[0]')
  TARGETS+=(-target='module.ingestion_embed[0]')
  TARGETS+=(-target='module.ingestion_index[0]')
  TARGETS+=(-target='module.ingestion_mark_failed[0]')
  TARGETS+=(-target='module.ingestion_watchdog[0]')
}

need_backend_artifacts=false
if [[ ${#TARGETS[@]} -eq 0 ]]; then
  need_backend_artifacts=true
else
  [[ "${APPLY_BACKEND_LAMBDAS:-false}" == "true" ]] && need_backend_artifacts=true
fi

if [[ "$need_backend_artifacts" == true ]]; then
  # Note: Lambda layers are deprecated. Dependencies are now bundled with each Lambda.
  # See MIGRATION_SUMMARY.md for details.
  # Paths come from backend/registry.json, so moving a service never requires
  # editing this script.
  while IFS= read -r dir; do
    if [[ ! -s "$ROOT/$dir/dist/function.zip" ]]; then
      make -C "$ROOT/$dir" package
    fi
  done < <(python3 -c "
import json, os
with open(os.path.join('$ROOT', 'backend', 'registry.json'), encoding='utf-8') as f:
    for app in json.load(f)['apps']:
        print(app['dir'])
")
fi

export PROD_TARGETS="${TARGETS[*]:-}"
bash "$ROOT/infra/aws/run-terraform.sh" prod apply

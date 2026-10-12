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
  TARGETS+=(-target='module.admin_console[0]')
  TARGETS+=(-target='module.code_interpreter[0]')
  TARGETS+=(-target='module.http_fetch[0]')
  TARGETS+=(-target='module.storage[0]')
  TARGETS+=(-target='module.custom_tools[0]')
  # New root resources introduced with the MCP Builder network + storage split:
  # the custom Code Interpreter (PUBLIC network) and the gateway targets map.
  TARGETS+=(-target='aws_bedrockagentcore_code_interpreter.mcp_tools')
  TARGETS+=(-target='aws_bedrockagentcore_gateway_target.mcp')
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

  # --- Avi (the in-product assistant) -----------------------------------------
  # Included so Avi deploys as part of a normal prod apply instead of needing
  # `deploy-avi.sh` run by hand.
  #
  # avi_guest / avi_session are gated only on enable_avi. avi_runtime is ALSO
  # gated on `avi_microvm_zip != ""`, and that gate is destructive: targeting it
  # with an empty value collapses count to 0 and plans the entire module (ECR
  # repo, MicroVM image, both IAM roles, the artifact) for DELETION. So it is
  # targeted only when the artifact is genuinely present on this runner, which
  # infra.yml arranges by building it in the step before this one.
  if [[ -z "${TF_VAR_avi_microvm_zip:-}" || ! -f "${TF_VAR_avi_microvm_zip}" ]]; then
    echo "TF_VAR_avi_microvm_zip is not set to an existing file." >&2
    echo "The Avi agent image + MicroVM artifact must be built first (infra.yml does" >&2
    echo "this in the step before this apply). Refusing to skip it silently, because" >&2
    echo "targeting module.avi_runtime without it would DELETE the deployed runtime." >&2
    exit 1
  fi
  TARGETS+=(-target='module.avi_guest[0]')
  TARGETS+=(-target='module.avi_session[0]')
  TARGETS+=(-target='module.avi_runtime[0]')

  if [[ -z "${TF_VAR_avi_session_secret:-}" ]]; then
    echo "WARNING: TF_VAR_avi_session_secret is empty; Avi would be deployed unable" >&2
    echo "         to mint session tokens. Set AVI_SESSION_SECRET in the prod env." >&2
  fi
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

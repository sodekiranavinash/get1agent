#!/usr/bin/env bash
# CI / laptop helper. Usage: run-terraform.sh <bootstrap|prod|web> <plan|apply>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STACK="${1:-}"
MODE="${2:-}"
BUCKET="${TF_STATE_BUCKET:-get1agent-terraform-state-ap-south-1}"

if [[ "$STACK" != "bootstrap" && "$STACK" != "prod" && "$STACK" != "web" ]]; then
  echo "usage: $0 <bootstrap|prod|web> <plan|apply>" >&2
  exit 2
fi
if [[ "$MODE" != "plan" && "$MODE" != "apply" ]]; then
  echo "usage: $0 <bootstrap|prod|web> <plan|apply>" >&2
  exit 2
fi

bucket_exists() {
  local err rc
  set +e
  err="$(aws s3api head-bucket --bucket "$BUCKET" 2>&1)"
  rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    return 0
  fi
  if grep -qiE '404|Not Found|NoSuchBucket|NotFound' <<<"$err"; then
    return 1
  fi
  echo "$err" >&2
  echo "Cannot determine if s3://$BUCKET exists (refusing to continue)." >&2
  exit 1
}

init_s3() {
  terraform init -input=false -no-color -reconfigure
}

# First-time bootstrap: S3 backend cannot init until the bucket exists.
# Override to local, create the bucket, then migrate state onto S3.
enable_local_backend_override() {
  cat > backend_override.tf <<'EOF'
terraform {
  backend "local" {
    path = "terraform.tfstate"
  }
}
EOF
}

disable_local_backend_override() {
  rm -f backend_override.tf
}

run_bootstrap() {
  cd "$ROOT/infra/terraform/bootstrap"

  if bucket_exists; then
    disable_local_backend_override
    init_s3
    if [[ "$MODE" == "apply" ]]; then
      terraform apply -input=false -no-color -auto-approve -lock-timeout=5m
    else
      terraform plan -input=false -no-color -out=tfplan
    fi
    return
  fi

  echo "State bucket s3://$BUCKET does not exist yet; using local backend for first create."
  enable_local_backend_override
  terraform init -input=false -no-color -reconfigure

  if [[ "$MODE" != "apply" ]]; then
    terraform plan -input=false -no-color -out=tfplan
    echo "Skipping envs/prod until the bootstrap apply creates the state bucket."
    disable_local_backend_override
    return
  fi

  terraform apply -input=false -no-color -auto-approve -lock-timeout=5m

  echo "Migrating bootstrap state to s3://$BUCKET"
  disable_local_backend_override
  terraform init -migrate-state -force-copy -input=false -no-color
  terraform apply -input=false -no-color -auto-approve -lock-timeout=5m
}

# check_zip <path> <label> <build-command>
check_zip() {
  local path="$1" label="$2" command="$3"
  if [[ "$need_backend" == true && ! -s "$path" ]]; then
    echo "Backend $label zip missing or empty: $path" >&2
    echo "Run: $command" >&2
    exit 1
  fi
  [[ "$need_backend" == true ]] && echo "$label zip: $path ($(wc -c <"$path") bytes)"
}

run_env() {
  local env_name="$1"
  cd "$ROOT/infra/terraform/envs/$env_name"

  if ! bucket_exists; then
    if [[ "$MODE" == "apply" ]]; then
      echo "State bucket s3://$BUCKET is missing; bootstrap apply must run first." >&2
      exit 1
    fi
    echo "Skipping envs/$env_name plan: state bucket s3://$BUCKET does not exist yet."
    return
  fi

  if [[ "$env_name" == "prod" ]]; then
    need_backend=false

    if [[ -z "${PROD_TARGETS:-}" ]]; then
      need_backend=true
    else
      case "$PROD_TARGETS" in
        *user_api*|*knowledge_mcp*|*ingestion*|*admin_console*|*code_interpreter*|*http_fetch*|*custom_tools*|*mcp_connections*|*browser*|*scheduler*)
          need_backend=true
          ;;
      esac
    fi

    # Note: Lambda layers are deprecated. Dependencies are now bundled with each Lambda.
    # See MIGRATION_SUMMARY.md for details.
    check_zip "$ROOT/backend/services/apis/user-api/dist/function.zip" "user-api" "make -C backend/services/apis/user-api package"
    check_zip "$ROOT/backend/services/mcp/knowledge-mcp/dist/function.zip" "knowledge-mcp" "make -C backend/services/mcp/knowledge-mcp package"
    check_zip "$ROOT/backend/services/ingestion/ingestion-dispatcher/dist/function.zip" "ingestion-dispatcher" "make -C backend/services/ingestion/ingestion-dispatcher package"
    check_zip "$ROOT/backend/services/ingestion/ingestion-extract/dist/function.zip" "ingestion-extract" "make -C backend/services/ingestion/ingestion-extract package"
    check_zip "$ROOT/backend/services/ingestion/ingestion-embed/dist/function.zip" "ingestion-embed" "make -C backend/services/ingestion/ingestion-embed package"
    check_zip "$ROOT/backend/services/ingestion/ingestion-index/dist/function.zip" "ingestion-index" "make -C backend/services/ingestion/ingestion-index package"
    check_zip "$ROOT/backend/services/ingestion/ingestion-mark-failed/dist/function.zip" "ingestion-mark-failed" "make -C backend/services/ingestion/ingestion-mark-failed package"
    check_zip "$ROOT/backend/services/ingestion/ingestion-watchdog/dist/function.zip" "ingestion-watchdog" "make -C backend/services/ingestion/ingestion-watchdog package"
    check_zip "$ROOT/backend/services/admin/admin-console/dist/function.zip" "admin-console" "make -C backend/services/admin/admin-console package"
    check_zip "$ROOT/backend/services/mcp/code-interpreter/dist/function.zip" "code-interpreter" "make -C backend/services/mcp/code-interpreter package"
    check_zip "$ROOT/backend/services/mcp/http-fetch/dist/function.zip" "http-fetch" "make -C backend/services/mcp/http-fetch package"
    check_zip "$ROOT/backend/services/mcp/mcp-connections/dist/function.zip" "mcp-connections" "make -C backend/services/mcp/mcp-connections package"

    # Never let an unset image URI destroy a deployed AgentCore runtime. An empty
    # `agent_worker_image_uri` makes module.agent_runtime plan its container-side
    # resources for destruction (user_api/scheduler depend on that module), so
    # reuse the currently deployed image unless the caller set one explicitly
    # (deploy-agent-runtime.sh passes the fresh image with `-var`, which wins).
    if [[ -z "${TF_VAR_agent_worker_image_uri:-}" ]]; then
      local region="${AWS_REGION:-ap-south-1}" rid img
      rid="$(aws bedrock-agentcore-control list-agent-runtimes --region "$region" \
        --query "agentRuntimes[?agentRuntimeName=='get1agent_prod_agent_worker'].agentRuntimeId | [0]" \
        --output text 2>/dev/null || true)"
      if [[ -n "$rid" && "$rid" != "None" ]]; then
        img="$(aws bedrock-agentcore-control get-agent-runtime --region "$region" \
          --agent-runtime-id "$rid" \
          --query 'agentRuntimeArtifact.containerConfiguration.containerUri' \
          --output text 2>/dev/null || true)"
        if [[ -n "$img" && "$img" != "None" ]]; then
          export TF_VAR_agent_worker_image_uri="$img"
          echo "Preserving deployed agent runtime image: $img"
        fi
      fi
    fi
  fi

  init_s3
  if [[ "$MODE" == "apply" ]]; then
    if [[ "$env_name" == "prod" && -n "${PROD_TARGETS:-}" ]]; then
      read -ra TARGET_ARR <<<"$PROD_TARGETS"
      terraform apply -input=false -no-color -auto-approve -lock-timeout=5m "${TARGET_ARR[@]}"
    else
      terraform apply -input=false -no-color -auto-approve -lock-timeout=5m
    fi
  else
    terraform plan -input=false -no-color -out=tfplan -lock-timeout=5m
  fi
}

if [[ "$STACK" == "bootstrap" ]]; then
  run_bootstrap
else
  run_env "$STACK"
fi

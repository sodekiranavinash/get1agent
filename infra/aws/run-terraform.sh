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
        *layer_base*|*layer_genai*|*layer_extra_tools*|*user_api*|*knowledge_mcp*|*ingestion*|*mcp_tester*|*code_interpreter*|*web_search*|*mcp_connections*)
          need_backend=true
          ;;
      esac
    fi

    check_zip "$ROOT/backend/services/dependency-layers/base/dist/layer.zip" "base layer" "bash infra/aws/build-backend-layers.sh"
    check_zip "$ROOT/backend/services/dependency-layers/genai/dist/layer.zip" "genai layer" "bash infra/aws/build-backend-layers.sh"
    check_zip "$ROOT/backend/services/dependency-layers/extra-tools/dist/layer.zip" "extra-tools layer" "bash infra/aws/build-backend-layers.sh"
    check_zip "$ROOT/backend/services/user-api/dist/function.zip" "user-api" "make -C backend/services/user-api package"
    check_zip "$ROOT/backend/services/knowledge-mcp/dist/function.zip" "knowledge-mcp" "make -C backend/services/knowledge-mcp package"
    check_zip "$ROOT/backend/services/ingestion-dispatcher/dist/function.zip" "ingestion-dispatcher" "make -C backend/services/ingestion-dispatcher package"
    check_zip "$ROOT/backend/services/ingestion-extract/dist/function.zip" "ingestion-extract" "make -C backend/services/ingestion-extract package"
    check_zip "$ROOT/backend/services/ingestion-embed/dist/function.zip" "ingestion-embed" "make -C backend/services/ingestion-embed package"
    check_zip "$ROOT/backend/services/ingestion-index/dist/function.zip" "ingestion-index" "make -C backend/services/ingestion-index package"
    check_zip "$ROOT/backend/services/ingestion-mark-failed/dist/function.zip" "ingestion-mark-failed" "make -C backend/services/ingestion-mark-failed package"
    check_zip "$ROOT/backend/services/ingestion-watchdog/dist/function.zip" "ingestion-watchdog" "make -C backend/services/ingestion-watchdog package"
    check_zip "$ROOT/backend/services/mcp-tester/dist/function.zip" "mcp-tester" "make -C backend/services/mcp-tester package"
    check_zip "$ROOT/backend/services/code-interpreter/dist/function.zip" "code-interpreter" "make -C backend/services/code-interpreter package"
    check_zip "$ROOT/backend/services/web-search/dist/function.zip" "web-search" "make -C backend/services/web-search package"
    check_zip "$ROOT/backend/services/mcp-connections/dist/function.zip" "mcp-connections" "make -C backend/services/mcp-connections package"
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

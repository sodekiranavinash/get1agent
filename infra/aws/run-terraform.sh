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
    local tool_zip="$ROOT/tools/challan-extractor/dist/function.zip"
    local layer_zip="$ROOT/backend/layers/data/dist/layer.zip"
    local health_zip="$ROOT/backend/health-check/dist/function.zip"
    local migration_zip="$ROOT/backend/migration-runner/dist/function.zip"
    local account_zip="$ROOT/backend/account-settings/dist/function.zip"
    local knowledge_zip="$ROOT/backend/knowledge-bases/dist/function.zip"
    local dispatcher_zip="$ROOT/backend/ingestion-dispatcher/dist/function.zip"
    local extract_zip="$ROOT/backend/ingestion-extract/dist/function.zip"
    local index_zip="$ROOT/backend/ingestion-index/dist/function.zip"
    local fail_zip="$ROOT/backend/ingestion-mark-failed/dist/function.zip"
    local need_tool=false need_backend=false

    if [[ -z "${PROD_TARGETS:-}" ]]; then
      need_tool=true
      need_backend=true
    else
      [[ "$PROD_TARGETS" == *challan_extractor* ]] && need_tool=true
      [[ "$PROD_TARGETS" == *layer_data* || "$PROD_TARGETS" == *health_check* || "$PROD_TARGETS" == *knowledge_bases* || "$PROD_TARGETS" == *ingestion* ]] && need_backend=true
    fi

    if [[ "$need_tool" == true && ! -s "$tool_zip" ]]; then
      echo "Lambda zip missing or empty: $tool_zip" >&2
      echo "Run: make -C tools/challan-extractor package" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$layer_zip" ]]; then
      echo "Backend data layer zip missing or empty: $layer_zip" >&2
      echo "Run: bash infra/aws/build-backend-layers.sh" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$health_zip" ]]; then
      echo "Backend health-check zip missing or empty: $health_zip" >&2
      echo "Run: make -C backend/health-check package" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$migration_zip" ]]; then
      echo "Backend migration-runner zip missing or empty: $migration_zip" >&2
      echo "Run: make -C backend/migration-runner package" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$account_zip" ]]; then
      echo "Backend account-settings zip missing or empty: $account_zip" >&2
      echo "Run: make -C backend/account-settings package" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$knowledge_zip" ]]; then
      echo "Backend knowledge-bases zip missing or empty: $knowledge_zip" >&2
      echo "Run: make -C backend/knowledge-bases package" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$dispatcher_zip" ]]; then
      echo "Backend ingestion-dispatcher zip missing or empty: $dispatcher_zip" >&2
      echo "Run: make -C backend/ingestion-dispatcher package" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$extract_zip" ]]; then
      echo "Backend ingestion-extract zip missing or empty: $extract_zip" >&2
      echo "Run: make -C backend/ingestion-extract package" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$index_zip" ]]; then
      echo "Backend ingestion-index zip missing or empty: $index_zip" >&2
      echo "Run: make -C backend/ingestion-index package" >&2
      exit 1
    fi
    if [[ "$need_backend" == true && ! -s "$fail_zip" ]]; then
      echo "Backend ingestion-mark-failed zip missing or empty: $fail_zip" >&2
      echo "Run: make -C backend/ingestion-mark-failed package" >&2
      exit 1
    fi
    [[ "$need_tool" == true ]] && echo "Tool Lambda zip: $tool_zip ($(wc -c <"$tool_zip") bytes)"
    [[ "$need_backend" == true ]] && echo "Data layer zip: $layer_zip ($(wc -c <"$layer_zip") bytes)"
    [[ "$need_backend" == true ]] && echo "Health-check zip: $health_zip ($(wc -c <"$health_zip") bytes)"
    [[ "$need_backend" == true ]] && echo "Knowledge-bases zip: $knowledge_zip ($(wc -c <"$knowledge_zip") bytes)"
    [[ "$need_backend" == true ]] && echo "Ingestion-dispatcher zip: $dispatcher_zip ($(wc -c <"$dispatcher_zip") bytes)"
    [[ "$need_backend" == true ]] && echo "Ingestion-extract zip: $extract_zip ($(wc -c <"$extract_zip") bytes)"
    [[ "$need_backend" == true ]] && echo "Ingestion-index zip: $index_zip ($(wc -c <"$index_zip") bytes)"
    [[ "$need_backend" == true ]] && echo "Ingestion-mark-failed zip: $fail_zip ($(wc -c <"$fail_zip") bytes)"
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

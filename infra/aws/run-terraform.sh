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
    local health_zip="$ROOT/backend/health-check/dist/function.zip"
    local need_tool=false need_health=false

    if [[ -z "${PROD_TARGETS:-}" ]]; then
      need_tool=true
      need_health=true
    else
      [[ "$PROD_TARGETS" == *challan_extractor* ]] && need_tool=true
      [[ "$PROD_TARGETS" == *health_check* ]] && need_health=true
    fi

    if [[ "$need_tool" == true && ! -s "$tool_zip" ]]; then
      echo "Lambda zip missing or empty: $tool_zip" >&2
      echo "Run: make -C tools/challan-extractor package" >&2
      exit 1
    fi
    if [[ "$need_health" == true && ! -s "$health_zip" ]]; then
      echo "Backend health-check zip missing or empty: $health_zip" >&2
      echo "Run: make -C backend/health-check package" >&2
      exit 1
    fi
    [[ "$need_tool" == true ]] && echo "Tool Lambda zip: $tool_zip ($(wc -c <"$tool_zip") bytes)"
    [[ "$need_health" == true ]] && echo "Health-check zip: $health_zip ($(wc -c <"$health_zip") bytes)"
  fi

  init_s3
  if [[ "$MODE" == "apply" ]]; then
    if [[ "$env_name" == "prod" ]]; then
      # Orphaned SG references from past renames block terraform destroy for minutes.
      bash "$ROOT/infra/aws/cleanup-stale-security-groups.sh" || true
    fi

    if [[ "$env_name" == "prod" && -n "${PROD_TARGETS:-}" ]]; then
      read -ra TARGET_ARR <<<"$PROD_TARGETS"
      terraform apply -input=false -no-color -auto-approve -lock-timeout=5m "${TARGET_ARR[@]}"
    else
      terraform apply -input=false -no-color -auto-approve -lock-timeout=5m
    fi

    if [[ "$env_name" == "prod" ]]; then
      bash "$ROOT/infra/aws/cleanup-stale-security-groups.sh" || true
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

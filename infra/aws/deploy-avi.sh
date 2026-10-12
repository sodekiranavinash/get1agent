#!/usr/bin/env bash
# Build, push and deploy Avi (the in-product assistant).
#
# Three artifacts, in dependency order:
#
#   1. the **agent container** (`backend/avi/Dockerfile`) → ECR. It carries the
#      Python service, LangChain Deep Agents and the Node streaming proxy.
#   2. the **MicroVM artifact** — the Dockerfile that pulls (1) plus the proxy,
#      zipped to S3, which Lambda builds into a MicroVM image.
#   3. the **guest Lambda** zip + the **control-plane Lambda** zip, which
#      `deploy-backend.sh` packages from `backend/registry.json`.
#
# Usage:
#   bash infra/aws/deploy-avi.sh                 # everything
#   bash infra/aws/deploy-avi.sh image           # just the container
#   bash infra/aws/deploy-avi.sh microvm         # just the MicroVM artifact + apply
#   bash infra/aws/deploy-avi.sh lambdas deploy   # just the two Lambdas
#
# Requires: docker (buildx), aws credentials with ECR push + Terraform apply.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
STEP="${1:-all}"
LAMBDA_MODE="${2:-deploy}"
AWS_REGION="${AWS_REGION:-ap-south-1}"
ECR_REPO="${AVI_ECR_REPOSITORY:-get1agent-prod-avi-agent}"
ARTIFACT_BUCKET="${AVI_ARTIFACT_BUCKET:-}"
IMAGE_TAG="${AVI_IMAGE_TAG:-$(date -u +%Y%m%d%H%M%S)}"
TF_DIR="$ROOT/infra/terraform/envs/prod"

log() { printf '\n=== %s\n' "$*"; }

account_id() {
  aws sts get-caller-identity --query Account --output text
}

# --- 0. bootstrap: image URI + ECR repository --------------------------------

compute_image() {
  local account
  account="$(account_id)"
  echo "${account}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"
}

# The MicroVM artifact is just a Dockerfile (templated with the agent image URI)
# plus the Node proxy, so it can be built BEFORE the image exists. That matters:
# the avi_runtime module is gated on `microvm_zip != ""`, so the module — and
# therefore the ECR repository inside it — cannot be created until the artifact
# exists. Creating the repository needs a targeted apply, which needs the zip.
# This is the chicken-and-egg that made the previous ordering impossible.
ensure_ecr() {
  local image="$1" zip_path="$2"
  if aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$ECR_REPO" >/dev/null 2>&1; then
    return 0
  fi
  log "creating the ECR repository (targeted apply: repository only)"
  terraform -chdir="$TF_DIR" apply \
    -var "enable_avi=true" \
    -var "avi_agent_image_uri=${image}" \
    -var "avi_microvm_zip=${zip_path}" \
    -target='module.avi_runtime[0].aws_ecr_repository.agent' \
    -auto-approve
}

# --- 1. agent container ------------------------------------------------------

build_image() {
  log "building the Avi agent image (linux/arm64)"
  local account image
  account="$(account_id)"
  image="${account}.dkr.ecr.${AWS_REGION}.amazonaws.com/${ECR_REPO}:${IMAGE_TAG}"

  aws ecr describe-repositories --region "$AWS_REGION" --repository-names "$ECR_REPO" \
    >/dev/null 2>&1 || {
      echo "ECR repository ${ECR_REPO} does not exist yet." >&2
      echo "Run 'bash infra/aws/deploy-avi.sh microvm' (it creates it), then retry." >&2
      exit 1
    }

  aws ecr get-login-password --region "$AWS_REGION" \
    | docker login --username AWS --password-stdin "${account}.dkr.ecr.${AWS_REGION}.amazonaws.com"

  # Build context is backend/ so the shared packages are available.
  docker buildx build \
    --platform linux/arm64 \
    --provenance=false \
    --file "$ROOT/backend/avi/Dockerfile" \
    --tag "$image" \
    --push \
    "$ROOT/backend"

  echo "$image"
}

# --- 2. MicroVM artifact -----------------------------------------------------

build_microvm_artifact() {
  local agent_image="$1"
  log "packaging the MicroVM artifact"

  local build_dir zip_path dockerfile
  build_dir="$(mktemp -d)"
  trap 'rm -rf "$build_dir"' RETURN
  dockerfile="$build_dir/Dockerfile"

  # The Lambda MicroVM image resource reads this Dockerfile from S3 and supports no
  # build args, so the base image is templated in here.
  sed "s|__AVI_AGENT_IMAGE__|${agent_image}|" \
    "$ROOT/backend/services/avi/microvm/Dockerfile" > "$dockerfile"

  cp "$ROOT/backend/services/avi/microvm/app.mjs" "$build_dir/"
  cp "$ROOT/backend/services/avi/microvm/package.json" "$build_dir/"

  zip_path="$ROOT/backend/services/avi/microvm/dist/microvm.zip"
  mkdir -p "$(dirname "$zip_path")"
  rm -f "$zip_path"
  (cd "$build_dir" && zip -qXr "$zip_path" .)

  echo "$zip_path"
}

upload_artifact() {
  local zip_path="$1" key="${AVI_MICROVM_ARTIFACT_KEY:-microvms/avi.zip}"
  if [[ -z "$ARTIFACT_BUCKET" ]]; then
    echo "AVI_ARTIFACT_BUCKET is not set; upload the artifact to the Terraform bucket and re-apply." >&2
    return 0
  fi
  log "uploading the artifact to s3://${ARTIFACT_BUCKET}/${key}"
  aws s3 cp "$zip_path" "s3://${ARTIFACT_BUCKET}/${key}" --region "$AWS_REGION"
}

apply_infra() {
  log "applying module.avi_runtime"
  # `avi_session_secret` MUST be supplied: it defaults to "", and an empty HMAC
  # secret means the control plane cannot mint a token the agent will verify
  # (minting fails loudly, so Avi would simply be dead). It must also be the same
  # value on every deploy, so it lives in the environment / GitHub secrets rather
  # than being generated here.
  if [[ -z "${AVI_SESSION_SECRET:-}" ]]; then
    echo "AVI_SESSION_SECRET is not set. Refusing to deploy Avi with an empty session secret." >&2
    echo "Export it (see .env) or add it as a GitHub secret." >&2
    exit 1
  fi
  terraform -chdir="$TF_DIR" apply \
    -var "enable_avi=true" \
    -var "avi_agent_image_uri=${1}" \
    -var "avi_microvm_zip=${2}" \
    -var "avi_session_secret=${AVI_SESSION_SECRET}" \
    -target=module.avi_runtime \
    -auto-approve
}

# --- 3. Lambdas --------------------------------------------------------------

deploy_lambdas() {
  log "packaging + deploying avi-guest and avi-session"
  bash "$ROOT/infra/aws/deploy-backend.sh" avi "$LAMBDA_MODE"
}

# --- orchestration -----------------------------------------------------------

case "$STEP" in
  image)
    build_image
    ;;
  # Both artifact flows bootstrap ECR first, in this order:
  #   compute the image URI (just a string) -> build the MicroVM artifact from it
  #   -> targeted apply to create the ECR repository -> build and push the image
  #   -> full module apply (the MicroVM image resource can now pull the agent image).
  # The module uploads the artifact itself via aws_s3_object, so there is no
  # separate upload step and no AVI_ARTIFACT_BUCKET to set.
  microvm)
    image="$(compute_image)"
    zip_path="$(build_microvm_artifact "$image")"
    ensure_ecr "$image" "$zip_path"
    build_image >/dev/null
    apply_infra "$image" "$zip_path"
    ;;
  lambdas)
    deploy_lambdas
    ;;
  all)
    image="$(compute_image)"
    zip_path="$(build_microvm_artifact "$image")"
    ensure_ecr "$image" "$zip_path"
    build_image >/dev/null
    apply_infra "$image" "$zip_path"
    deploy_lambdas
    log "done"
    echo "Next: make avi-bootstrap && make avi-upload   (index the corpus)"
    echo "      then open /admin/avi to confirm the widget is Live."
    ;;
  *)
    echo "usage: $0 [all|image|microvm|lambdas] [package|deploy]" >&2
    exit 2
    ;;
esac

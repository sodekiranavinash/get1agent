#!/usr/bin/env bash
# Build + push the agent worker image and deploy the AgentCore runtime.
#
# Two-phase, because the AgentCore runtime needs a container image that only
# exists after the ECR repo does:
#   1. targeted apply  -> create the ECR repo
#   2. build + push    -> ARM64 worker image
#   3. targeted apply  -> create the AgentCore runtime + streaming proxy
#
# Usage: bash infra/aws/deploy-agent-runtime.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/prod"
REGION="${AWS_REGION:-ap-south-1}"
REPO_NAME="${AGENT_WORKER_REPO:-get1agent-prod-agent-worker}"
TAG="${IMAGE_TAG:-$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo latest)}"

if [[ ! -s "$ROOT/backend/services/agent-run/dist/function.zip" ]]; then
  make -C "$ROOT/backend/services/agent-run" package
fi

cd "$ENV_DIR"
terraform init -input=false -no-color -reconfigure

echo "==> Ensuring the ECR repository exists"
terraform apply -input=false -no-color -auto-approve -lock-timeout=5m \
  -target='module.agent_runtime[0].aws_ecr_repository.worker'

ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"
REGISTRY="$ACCOUNT.dkr.ecr.$REGION.amazonaws.com"
IMAGE_URI="$REGISTRY/$REPO_NAME:$TAG"

echo "==> Building + pushing $IMAGE_URI"
aws ecr get-login-password --region "$REGION" \
  | docker login --username AWS --password-stdin "$REGISTRY"
docker build --platform linux/arm64 \
  -f "$ROOT/backend/agents/Dockerfile" \
  -t "$IMAGE_URI" \
  "$ROOT/backend"
docker push "$IMAGE_URI"

echo "==> Deploying the AgentCore runtime + streaming proxy"
terraform apply -input=false -no-color -auto-approve -lock-timeout=5m \
  -target='module.agent_runtime[0]' \
  -var "agent_worker_image_uri=$IMAGE_URI"

echo "==> Agent runtime deployed: $IMAGE_URI"

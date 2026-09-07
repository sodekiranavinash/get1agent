#!/usr/bin/env bash
# Build control_plane, push to ECR, restart container on EC2 via SSM.
#
# Usage:
#   bash infra/aws/deploy-control-plane.sh
#
# Requires infra deployed first (deploy-infra.sh or GitHub Infra workflow).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
AWS_REGION="${AWS_REGION:-us-east-1}"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

if ! terraform output -raw ecr_repository_url >/dev/null 2>&1; then
  echo "Data plane not found. Run: bash infra/aws/deploy-infra.sh apply" >&2
  exit 1
fi

ECR_URL="$(terraform output -raw ecr_repository_url)"
INSTANCE_ID="$(terraform output -raw app_instance_id)"
API_URL="$(terraform output -raw api_base_url)"

echo "ECR:      $ECR_URL"
echo "Instance: $INSTANCE_ID"
echo "Building control_plane Docker image..."

aws ecr get-login-password --region "$AWS_REGION" | docker login --username AWS --password-stdin "${ECR_URL%/*}"

# EC2 is t4g (ARM64). GitHub/Intel Mac runners build amd64 by default — use buildx.
if ! docker buildx inspect get1agent-builder >/dev/null 2>&1; then
  docker buildx create --name get1agent-builder --use >/dev/null
else
  docker buildx use get1agent-builder
fi

docker buildx build \
  --platform linux/arm64 \
  -t "$ECR_URL:latest" \
  --push \
  "$ROOT/control_plane"

echo "Deploying on EC2 via SSM..."
bash "$ROOT/infra/aws/sync-ec2-api.sh"

echo ""
echo "=== control_plane deployed ==="
echo "Health:  ${API_URL}/health"
echo "Ready:   ${API_URL}/ready   (checks DB via IAM)"
echo "Docs:    ${API_URL}/docs"
echo "Public:  https://api.get1agent.com (after Cloudflare A record -> app IP)"
echo ""
echo "Verify: curl -s ${API_URL}/health"

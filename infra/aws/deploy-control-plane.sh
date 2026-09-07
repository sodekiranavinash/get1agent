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
docker build -t "$ECR_URL:latest" "$ROOT/control_plane"
docker push "$ECR_URL:latest"

echo "Deploying on EC2 via SSM..."
COMMAND_ID="$(aws ssm send-command \
  --region "$AWS_REGION" \
  --instance-ids "$INSTANCE_ID" \
  --document-name AWS-RunShellScript \
  --comment "Deploy get1agent control_plane" \
  --parameters commands='["/opt/get1agent/deploy-api.sh"]' \
  --query Command.CommandId \
  --output text)"

aws ssm wait command-executed --command-id "$COMMAND_ID" --instance-id "$INSTANCE_ID" --region "$AWS_REGION"

aws ssm get-command-invocation \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --region "$AWS_REGION" \
  --query StandardOutputContent \
  --output text

STATUS="$(aws ssm get-command-invocation \
  --command-id "$COMMAND_ID" \
  --instance-id "$INSTANCE_ID" \
  --region "$AWS_REGION" \
  --query Status \
  --output text)"

if [[ "$STATUS" != "Success" ]]; then
  aws ssm get-command-invocation \
    --command-id "$COMMAND_ID" \
    --instance-id "$INSTANCE_ID" \
    --region "$AWS_REGION" \
    --query StandardErrorContent \
    --output text >&2
  exit 1
fi

echo ""
echo "=== control_plane deployed ==="
echo "Health:  ${API_URL}/health"
echo "Ready:   ${API_URL}/ready   (checks DB via IAM)"
echo "Docs:    ${API_URL}/docs"
echo ""
echo "Verify: curl -s ${API_URL}/health"

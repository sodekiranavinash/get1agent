#!/bin/bash
set -euo pipefail

REGION="__REGION__"
ECR_URL="__ECR_URL__"
API_PORT="__API_PORT__"
DB_HOST="__DB_HOST__"
DB_NAME="__DB_NAME__"
DB_IAM_USER="__DB_IAM_USER__"
CONTAINER_NAME="get1agent-api"

/opt/get1agent/setup-nginx.sh

/opt/get1agent/bootstrap-db-iam-user.sh

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "$ECR_URL"

IMAGE="$ECR_URL:latest"
docker pull "$IMAGE"

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --network host \
  -e AWS_REGION="$REGION" \
  -e DATABASE_USE_IAM=true \
  -e DATABASE_HOST="$DB_HOST" \
  -e DATABASE_NAME="$DB_NAME" \
  -e DATABASE_IAM_USER="$DB_IAM_USER" \
  -e PORT="$API_PORT" \
  -e HOST=127.0.0.1 \
  "$IMAGE"

docker image prune -f >/dev/null 2>&1 || true
echo "Deployed $IMAGE with IAM database auth on port $API_PORT (nginx :80 -> localhost:$API_PORT)"

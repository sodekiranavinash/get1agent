#!/bin/bash
# Deploy Kong Gateway OSS with RDS IAM auth. No nginx — Kong listens on :80 directly.
set -euo pipefail

REGION="__REGION__"
KONG_IMAGE="__KONG_IMAGE__"
DB_HOST="__DB_HOST__"
KONG_DB_NAME="__KONG_DB_NAME__"
KONG_IAM_USER="__KONG_IAM_USER__"
API_HOSTNAME="__API_HOSTNAME__"
KONG_UI_HOSTNAME="__KONG_UI_HOSTNAME__"
CONTAINER_NAME="get1agent-kong"

/opt/get1agent/bootstrap-db.sh

# RDS IAM auth token (valid ~15 min; systemd timer refreshes)
PG_PASSWORD="$(aws rds generate-db-auth-token \
  --hostname "$DB_HOST" \
  --port 5432 \
  --username "$KONG_IAM_USER" \
  --region "$REGION")"

docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true

# Bootstrap migrations (idempotent)
docker run --rm \
  --network host \
  -e KONG_DATABASE=postgres \
  -e KONG_PG_HOST="$DB_HOST" \
  -e KONG_PG_PORT=5432 \
  -e KONG_PG_DATABASE="$KONG_DB_NAME" \
  -e KONG_PG_USER="$KONG_IAM_USER" \
  -e KONG_PG_PASSWORD="$PG_PASSWORD" \
  -e KONG_PG_SSL=on \
  "$KONG_IMAGE" \
  kong migrations bootstrap 2>/dev/null || \
docker run --rm \
  --network host \
  -e KONG_DATABASE=postgres \
  -e KONG_PG_HOST="$DB_HOST" \
  -e KONG_PG_PORT=5432 \
  -e KONG_PG_DATABASE="$KONG_DB_NAME" \
  -e KONG_PG_USER="$KONG_IAM_USER" \
  -e KONG_PG_PASSWORD="$PG_PASSWORD" \
  -e KONG_PG_SSL=on \
  "$KONG_IMAGE" \
  kong migrations up

docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  --network host \
  -e KONG_DATABASE=postgres \
  -e KONG_PG_HOST="$DB_HOST" \
  -e KONG_PG_PORT=5432 \
  -e KONG_PG_DATABASE="$KONG_DB_NAME" \
  -e KONG_PG_USER="$KONG_IAM_USER" \
  -e KONG_PG_PASSWORD="$PG_PASSWORD" \
  -e KONG_PG_SSL=on \
  -e KONG_PROXY_LISTEN=0.0.0.0:80 \
  -e KONG_ADMIN_LISTEN=127.0.0.1:8001 \
  -e KONG_ADMIN_GUI_LISTEN=127.0.0.1:8002 \
  -e KONG_ADMIN_GUI_URL="https://${KONG_UI_HOSTNAME}" \
  -e KONG_ADMIN_GUI_PATH=/ \
  -e KONG_LOG_LEVEL=info \
  "$KONG_IMAGE"

for attempt in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8001/status" >/dev/null 2>&1; then
    break
  fi
  echo "Waiting for Kong Admin API ($attempt/30)..."
  sleep 2
done

/opt/get1agent/bootstrap-kong-admin.sh

docker image prune -f >/dev/null 2>&1 || true
echo "Kong deployed: proxy :80 (${API_HOSTNAME}), Manager UI via ${KONG_UI_HOSTNAME}"

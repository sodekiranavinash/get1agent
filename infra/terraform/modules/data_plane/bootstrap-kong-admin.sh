#!/bin/bash
# Expose Kong Manager OSS at kong.get1agent.com with basic-auth admin login.
set -euo pipefail

REGION="__REGION__"
KONG_ADMIN_SECRET_ARN="__KONG_ADMIN_SECRET_ARN__"
KONG_UI_HOSTNAME="__KONG_UI_HOSTNAME__"
MARKER="/opt/get1agent/.kong_admin_bootstrapped"
ADMIN_API="http://127.0.0.1:8001"

if [[ -f "$MARKER" ]]; then
  echo "Kong admin UI route already configured"
  exit 0
fi

for attempt in $(seq 1 30); do
  if curl -sf "$ADMIN_API/status" >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

SECRET_JSON="$(aws secretsmanager get-secret-value \
  --region "$REGION" \
  --secret-id "$KONG_ADMIN_SECRET_ARN" \
  --query SecretString \
  --output text)"

ADMIN_USER="$(echo "$SECRET_JSON" | jq -r '.username')"
ADMIN_PASS="$(echo "$SECRET_JSON" | jq -r '.password')"

# Admin consumer + basic-auth credential
curl -sf -X POST "$ADMIN_API/consumers" \
  -d "username=${ADMIN_USER}" >/dev/null 2>&1 || true

curl -sf -X POST "$ADMIN_API/consumers/${ADMIN_USER}/basic-auth" \
  -d "username=${ADMIN_USER}" \
  -d "password=${ADMIN_PASS}" >/dev/null 2>&1 || true

# Route kong.get1agent.com -> Kong Manager (localhost:8002)
curl -sf -X POST "$ADMIN_API/services" \
  -d "name=kong-manager" \
  -d "url=http://127.0.0.1:8002" >/dev/null 2>&1 || true

ROUTE_ID="$(curl -sf "$ADMIN_API/services/kong-manager/routes" | jq -r '.data[0].id // empty')"
if [[ -z "$ROUTE_ID" ]]; then
  ROUTE_ID="$(curl -sf -X POST "$ADMIN_API/services/kong-manager/routes" \
    -d "name=kong-manager-ui" \
    -d "hosts[]=${KONG_UI_HOSTNAME}" | jq -r '.id')"
fi

# Basic-auth on the Manager route
PLUGIN_EXISTS="$(curl -sf "$ADMIN_API/routes/${ROUTE_ID}/plugins" | jq -r '.data[] | select(.name=="basic-auth") | .id' | head -1)"
if [[ -z "$PLUGIN_EXISTS" ]]; then
  curl -sf -X POST "$ADMIN_API/routes/${ROUTE_ID}/plugins" \
    -d "name=basic-auth" \
    -d "config.hide_credentials=true"
fi

touch "$MARKER"
echo "Kong Manager UI: https://${KONG_UI_HOSTNAME} (user: ${ADMIN_USER})"

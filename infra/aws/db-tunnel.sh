#!/usr/bin/env bash
# SSM port forward to prod RDS (for DBeaver). No SSH key or home IP required.
#
# Usage:
#   bash infra/aws/db-tunnel.sh              # tunnel on localhost:15432
#   bash infra/aws/db-tunnel.sh --show-creds # print DBeaver credentials
#   bash infra/aws/db-tunnel.sh --port 5432  # only if 15432 is taken
#
# Requires: AWS CLI, Session Manager plugin (brew install --cask session-manager-plugin)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/prod"
LOCAL_PORT="${LOCAL_PORT:-15432}"
MODE="tunnel"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --show-creds) MODE="creds"; shift ;;
    --port)
      LOCAL_PORT="$2"
      shift 2
      ;;
    -h | --help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 2
      ;;
  esac
done

cd "$ENV_DIR"

if ! terraform output -raw app_instance_id &>/dev/null; then
  echo "Data plane not found. Run: bash infra/aws/deploy-infra.sh apply" >&2
  exit 1
fi

INSTANCE_ID="$(terraform output -raw app_instance_id)"
RDS_HOST="$(terraform output -raw postgres_endpoint)"
CONN_SECRET_ARN="$(terraform output -raw postgres_connection_secret_arn)"

if [[ "$MODE" == "creds" ]]; then
  aws secretsmanager get-secret-value \
    --secret-id "$CONN_SECRET_ARN" \
    --query SecretString \
    --output text | python3 -m json.tool
  exit 0
fi

echo "RDS host: $RDS_HOST"
echo "Local port: $LOCAL_PORT"
echo "Credentials: bash infra/aws/db-tunnel.sh --show-creds"
echo ""
echo "DBeaver: host localhost, port $LOCAL_PORT, SSH tab OFF"
echo "         SSL require (or disable if DBeaver says server does not support SSL)"
echo ""
echo "Starting SSM tunnel (Ctrl+C to stop)…"
exec aws ssm start-session \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"${RDS_HOST}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"${LOCAL_PORT}\"]}"

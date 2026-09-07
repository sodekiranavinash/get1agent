#!/usr/bin/env bash
# Open a local tunnel to dev RDS via the app EC2.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
LOCAL_PORT="${LOCAL_PORT:-5432}"
MODE="ssm"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ssh) MODE="ssh"; shift ;;
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
  echo "Data plane not found. Run the Infra GitHub Action with DATA_PLANE_SSH_CIDR set." >&2
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

if [[ "$MODE" == "ssh" ]]; then
  APP_IP="$(terraform output -raw app_public_ip)"
  KEY_PATH="${HOME}/.ssh/get1agent-dev-app.pem"

  if [[ ! -f "$KEY_PATH" ]]; then
    bash "$ROOT/infra/aws/fetch-app-ssh-key.sh" "$KEY_PATH"
  fi

  echo "Starting SSH tunnel (Ctrl+C to stop)…"
  exec ssh -i "$KEY_PATH" \
    -o StrictHostKeyChecking=accept-new \
    -L "${LOCAL_PORT}:${RDS_HOST}:5432" \
    "ec2-user@${APP_IP}" \
    -N
fi

echo "Starting SSM tunnel (Ctrl+C to stop)…"
exec aws ssm start-session \
  --target "$INSTANCE_ID" \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters "{\"host\":[\"${RDS_HOST}\"],\"portNumber\":[\"5432\"],\"localPortNumber\":[\"${LOCAL_PORT}\"]}"

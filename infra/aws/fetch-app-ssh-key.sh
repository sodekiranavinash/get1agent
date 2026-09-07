#!/usr/bin/env bash
# Save the app EC2 SSH private key locally for DBeaver / SSH.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"
KEY_PATH="${1:-${HOME}/.ssh/get1agent-dev-app.pem}"

cd "$ENV_DIR"
SECRET_ARN="$(terraform output -raw app_ssh_key_secret_arn)"

mkdir -p "$(dirname "$KEY_PATH")"
aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ARN" \
  --query SecretString \
  --output text >"$KEY_PATH"
chmod 600 "$KEY_PATH"

echo "Saved SSH key to $KEY_PATH"
echo "Use this path in DBeaver → SSH → Private key"

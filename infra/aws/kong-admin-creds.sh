#!/usr/bin/env bash
# Print Kong Manager UI admin credentials from Secrets Manager.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT/infra/terraform/envs/dev"

cd "$ENV_DIR"
terraform init -input=false >/dev/null

SECRET_ARN="$(terraform output -raw kong_admin_credentials_secret_arn)"

aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ARN" \
  --query SecretString \
  --output text | python3 -m json.tool

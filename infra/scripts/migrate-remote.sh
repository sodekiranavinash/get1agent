#!/usr/bin/env bash
# Runs on the production jumpbox via SSM (invoked by .github/workflows/migrate.yml).
#
# Expects the migration bundle already extracted into the current directory
# (containing backend/migrations, backend/services/shared, infra/scripts/). Builds DATABASE_URL
# from the RDS connection parameter in SSM and runs Alembic.
#
# Args: <name-prefix> <upgrade|downgrade> <revision>
set -euo pipefail

NAME_PREFIX="${1:?name prefix, e.g. get1agent-prod}"
ACTION="${2:?upgrade or downgrade}"
REVISION="${3:?revision, e.g. head or -1}"

# AWS CLI is preinstalled on AL2023; install it if this is a bare image.
if ! command -v aws >/dev/null 2>&1; then
  curl -sSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
  python3 -c 'import zipfile; zipfile.ZipFile("/tmp/awscliv2.zip").extractall("/tmp/awscli")'
  /tmp/awscli/aws/install --update
fi

CREDS="$(aws ssm get-parameter \
  --name "/${NAME_PREFIX}/postgres/connection" \
  --with-decryption --query Parameter.Value --output text)"

read -r HOST PORT DB USER PASS < <(python3 -c '
import json, sys
d = json.load(sys.stdin)
print(d["host"], d["port"], d["dbname"], d["username"], d["password"])
' <<<"$CREDS")

export DATABASE_URL="postgresql+asyncpg://${USER}:${PASS}@${HOST}:${PORT}/${DB}?ssl=require"

export PATH="$HOME/.local/bin:$PATH"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

cd backend/migrations
echo "[migrate] $ACTION $REVISION against ${HOST}:${PORT}/${DB}"
uv run alembic "$ACTION" "$REVISION"

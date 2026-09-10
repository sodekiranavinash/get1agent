#!/usr/bin/env bash
# Run a Lambda handler locally over HTTP (no AWS, no Docker, no layers).
# Each Lambda gets its own uv-managed environment with just its dependencies.
#
# Usage: bash local/run.sh <account-settings|health-check>
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAMBDA="${1:-}"

case "$LAMBDA" in
  account-settings) PKGS=("sqlalchemy[asyncio]" asyncpg boto3) ;;
  health-check) PKGS=("sqlalchemy[asyncio]" asyncpg boto3) ;;
  *)
    echo "usage: bash local/run.sh <account-settings|health-check>" >&2
    exit 2
    ;;
esac

# Local overrides (DATABASE_URL, PORT, ...). Never committed.
# Prefer `.env.local`; fall back to `.env` for anyone who copied the template
# there instead of to `.env.local`.
ENV_FILE="$ROOT/.env.local"
[[ -f "$ENV_FILE" ]] || ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

export PYTHONPATH="$ROOT/backend${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONUNBUFFERED=1

ARGS=()
for pkg in "${PKGS[@]}"; do
  ARGS+=(--with "$pkg")
done

exec uv run "${ARGS[@]}" python "$ROOT/local/run_lambda.py" "$LAMBDA"

#!/usr/bin/env bash
# Run Alembic migrations against the Floci Postgres.
#
#   bash infra/local/floci/migrate.sh upgrade [revision]    # default revision: head
#   bash infra/local/floci/migrate.sh downgrade [revision]  # default revision: -1
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
ACTION="${1:-upgrade}"
REVISION="${2:-}"

case "$ACTION" in
  up | upgrade)
    ACTION="upgrade"
    REVISION="${REVISION:-head}"
    ;;
  down | downgrade)
    ACTION="downgrade"
    REVISION="${REVISION:--1}"
    ;;
  *)
    echo "usage: $0 upgrade|downgrade [revision]" >&2
    exit 2
    ;;
esac

# Read DATABASE_URL from the root .env unless it is already set.
if [[ -z "${DATABASE_URL:-}" && -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ROOT/.env"
  set +a
fi
DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://get1agent:get1agent@localhost:5433/get1agent}"

cd "$ROOT/backend/migrations"
echo "[floci-migrate] $ACTION $REVISION"
DATABASE_URL="$DATABASE_URL" uv run alembic "$ACTION" "$REVISION"

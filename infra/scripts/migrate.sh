#!/usr/bin/env bash
# Local Alembic migration helper (uses DATABASE_URL from .env.local or .env).
#
#   bash infra/scripts/migrate.sh up [revision]        # upgrade (default: head)
#   bash infra/scripts/migrate.sh down [revision]      # downgrade (default: -1)
#   bash infra/scripts/migrate.sh current|history
#   bash infra/scripts/migrate.sh revision "message"
#
# Floci stack:    make floci-migrate / make floci-migrate-down
# Production:     the "Migrate" GitHub Actions workflow (runs on the jumpbox)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"

usage() {
  cat >&2 <<'EOF'
usage:
  bash infra/scripts/migrate.sh up [revision]        # local DB (default: head)
  bash infra/scripts/migrate.sh down [revision]      # local DB (default: -1)
  bash infra/scripts/migrate.sh current|history
  bash infra/scripts/migrate.sh revision "message"
EOF
  exit 2
}

CMD="${1:-up}"

ENV_FILE="$ROOT/.env.local"
[[ -f "$ENV_FILE" ]] || ENV_FILE="$ROOT/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi
if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required. Set it in .env.local (or .env)." >&2
  exit 1
fi

cd "$ROOT/backend/migrations"
case "$CMD" in
  up | upgrade) uv run alembic upgrade "${2:-head}" ;;
  down | downgrade) uv run alembic downgrade "${2:--1}" ;;
  current) uv run alembic current ;;
  history) uv run alembic history --verbose ;;
  revision)
    [[ -n "${2:-}" ]] || usage
    uv run alembic revision --autogenerate -m "$2"
    ;;
  *) usage ;;
esac

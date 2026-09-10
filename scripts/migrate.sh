#!/usr/bin/env bash
# Local Alembic runner (no deploy, no Lambda). Targets your local database
# via DATABASE_URL from the environment or .env.local.
#
# Usage:
#   bash scripts/migrate.sh up                 # alembic upgrade head
#   bash scripts/migrate.sh up <revision>      # alembic upgrade <revision>
#   bash scripts/migrate.sh down               # alembic downgrade -1
#   bash scripts/migrate.sh down <revision>    # alembic downgrade <revision>
#   bash scripts/migrate.sh current
#   bash scripts/migrate.sh history
#   bash scripts/migrate.sh revision "message"
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$ROOT/.env.local" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env.local"
  set +a
fi

if [[ -z "${DATABASE_URL:-}" ]]; then
  echo "DATABASE_URL is required. Set it in .env.local (see .env.example)." >&2
  exit 1
fi

cd "$ROOT/backend/migrations"
CMD="${1:-up}"

case "$CMD" in
  up | upgrade) uv run alembic upgrade "${2:-head}" ;;
  down | downgrade) uv run alembic downgrade "${2:--1}" ;;
  current) uv run alembic current ;;
  history) uv run alembic history --verbose ;;
  revision)
    if [[ -z "${2:-}" ]]; then
      echo "usage: bash scripts/migrate.sh revision \"message\"" >&2
      exit 2
    fi
    uv run alembic revision --autogenerate -m "$2"
    ;;
  *)
    echo "usage: $0 <up|down|current|history|revision> [revision|message]" >&2
    exit 2
    ;;
esac

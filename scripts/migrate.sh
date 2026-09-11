#!/usr/bin/env bash
# Migration helper (standalone — intentionally NOT a make target).
#
# Local database (Alembic directly, uses DATABASE_URL from env, .env.local or .env):
#   bash scripts/migrate.sh up [revision]        # upgrade head
#   bash scripts/migrate.sh down [revision]      # downgrade -1
#   bash scripts/migrate.sh current
#   bash scripts/migrate.sh history
#   bash scripts/migrate.sh revision "message"
#
# Cloud (invoke the deployed migration-runner Lambda over AWS CLI):
#   bash scripts/migrate.sh lambda up [revision]
#   bash scripts/migrate.sh lambda down [revision]
#   bash scripts/migrate.sh lambda stamp [revision]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  cat >&2 <<'EOF'
usage:
  bash scripts/migrate.sh up [revision]        # local DB (default: head)
  bash scripts/migrate.sh down [revision]      # local DB (default: -1)
  bash scripts/migrate.sh current|history
  bash scripts/migrate.sh revision "message"
  bash scripts/migrate.sh lambda up [revision]    # invoke cloud migration-runner
  bash scripts/migrate.sh lambda down [revision]
  bash scripts/migrate.sh lambda stamp [revision]
EOF
  exit 2
}

MODE="local"
if [[ "${1:-}" == "lambda" ]]; then
  MODE="lambda"
  shift
fi
CMD="${1:-up}"

if [[ "$MODE" == "local" ]]; then
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
  exit 0
fi

# --- Cloud: invoke the migration-runner Lambda ---
FUNCTION="${MIGRATION_FUNCTION:-get1agent-prod-migration-runner}"
REGION="${AWS_REGION:-ap-south-1}"
OUT="/tmp/get1agent-migrate-out.json"

case "$CMD" in
  up | upgrade)
    ACTION="upgrade"
    REV="${2:-head}"
    ;;
  down | downgrade)
    ACTION="downgrade"
    REV="${2:--1}"
    ;;
  stamp)
    ACTION="stamp"
    REV="${2:-head}"
    ;;
  *) usage ;;
esac

PAYLOAD="{\"action\":\"$ACTION\",\"revision\":\"$REV\"}"
aws lambda invoke \
  --region "$REGION" \
  --function-name "$FUNCTION" \
  --cli-binary-format raw-in-base64-out \
  --payload "$PAYLOAD" \
  "$OUT" >/dev/null
cat "$OUT"
echo

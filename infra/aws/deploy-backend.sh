#!/usr/bin/env bash
# Package and optionally deploy backend/* Lambdas (TypeScript + esbuild).
#
# Usage:
#   bash infra/aws/deploy-backend.sh health-check          # package only
#   bash infra/aws/deploy-backend.sh health-check deploy   # package + upload
#   bash infra/aws/deploy-backend.sh all deploy
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
QUERY="${1:-health-check}"
MODE="${2:-package}"
AWS_REGION="${AWS_REGION:-ap-south-1}"

if [[ "$MODE" != "package" && "$MODE" != "deploy" ]]; then
  echo "usage: $0 <lambda-name|function-name|all> [package|deploy]" >&2
  exit 2
fi

ENTRIES=()
while IFS= read -r line; do
  [[ -n "$line" ]] && ENTRIES+=("$line")
done < <(python3 - "$ROOT/backend/registry.json" "$QUERY" <<'PY'
import json
import sys

path, query = sys.argv[1], sys.argv[2].strip()
with open(path, encoding="utf-8") as f:
    lambdas = json.load(f)["lambdas"]

if query.lower() == "all":
    selected = lambdas
else:
    selected = [
        item for item in lambdas
        if item["name"] == query or item["function_name"] == query
    ]

if not selected:
    sys.exit(1)

for item in selected:
    print(f"{item['dir']}|{item['function_name']}")
PY
)

if [[ "${#ENTRIES[@]}" -eq 0 ]]; then
  echo "Unknown lambda: $QUERY" >&2
  bash "$ROOT/infra/aws/select-backend.sh" >&2 || true
  exit 1
fi

for entry in "${ENTRIES[@]}"; do
  lambda_dir="${entry%%|*}"
  function_name="${entry##*|}"
  dir="$ROOT/$lambda_dir"

  echo "=== Packaging $lambda_dir ==="
  make -C "$dir" package

  zip="$dir/dist/function.zip"
  if [[ ! -s "$zip" ]]; then
    echo "Missing zip: $zip" >&2
    exit 1
  fi

  if [[ "$MODE" != "deploy" ]]; then
    echo "Built $zip ($(wc -c <"$zip") bytes)"
    continue
  fi

  if ! aws lambda get-function --region "$AWS_REGION" --function-name "$function_name" >/dev/null 2>&1; then
    echo "Function $function_name does not exist. Run infra apply first." >&2
    exit 1
  fi

  local_sha="$(python3 -c "import base64,hashlib,pathlib,sys; p=pathlib.Path(sys.argv[1]); print(base64.b64encode(hashlib.sha256(p.read_bytes()).digest()).decode())" "$zip")"
  remote_sha="$(aws lambda get-function-configuration --region "$AWS_REGION" --function-name "$function_name" --query CodeSha256 --output text)"
  echo "local  CodeSha256=$local_sha"
  echo "remote CodeSha256=$remote_sha"

  if [[ "$local_sha" == "$remote_sha" ]]; then
    echo "Zip matches live function; skipping upload."
    continue
  fi

  aws lambda update-function-code \
    --region "$AWS_REGION" \
    --function-name "$function_name" \
    --zip-file "fileb://$zip"
  aws lambda wait function-updated --region "$AWS_REGION" --function-name "$function_name"
  echo "Deployed $function_name"
done

#!/usr/bin/env bash
# Print a GitHub Actions matrix include JSON for one backend lambda, function name, or "all".
set -euo pipefail

QUERY="${1:-}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REGISTRY="$ROOT/backend/services/registry.json"

if [[ -z "$QUERY" ]]; then
  echo "usage: $0 <lambda-name|function-name|all>" >&2
  exit 2
fi

python3 - "$REGISTRY" "$QUERY" <<'PY'
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
        if item["name"] == query
        or item["function_name"] == query
        or item.get("group") == query
    ]

if not selected:
    names = ", ".join(item["name"] for item in lambdas)
    groups = ", ".join(sorted({item["group"] for item in lambdas if item.get("group")}))
    print(
        f"Unknown target {query!r}. Use a lambda name ({names}), a group ({groups}), "
        "a function name, or all.",
        file=sys.stderr,
    )
    sys.exit(1)

print(json.dumps([
    {
        "name": item["name"],
        "lambda_dir": item["dir"],
        "function_name": item["function_name"],
    }
    for item in selected
]))
PY

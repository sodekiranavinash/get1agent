#!/usr/bin/env bash
# Build a GitHub Actions matrix JSON from backend registry checkboxes.
# Set SELECT_<name-with-underscores>=true for each lambda (e.g. SELECT_HEALTH_CHECK=true).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REGISTRY="$ROOT/backend/registry.json"

python3 - "$REGISTRY" <<'PY'
import json
import os
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    lambdas = json.load(f)["lambdas"]

selected = []
for item in lambdas:
    key = "SELECT_" + re.sub(r"[^A-Za-z0-9]+", "_", item["name"]).upper()
    if os.environ.get(key, "").lower() == "true":
        selected.append(
            {
                "name": item["name"],
                "lambda_dir": item["dir"],
                "function_name": item["function_name"],
            }
        )

if not selected:
    print("Select at least one backend lambda.", file=sys.stderr)
    sys.exit(1)

print(json.dumps(selected))
PY

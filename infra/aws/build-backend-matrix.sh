#!/usr/bin/env bash
# Build a GitHub Actions matrix JSON from grouped backend checkboxes.
#
# Selection is by *group* (registry `group` field): set SELECT_<GROUP>=true,
# e.g. SELECT_USER_APIS=true, SELECT_MCP_TOOLS=true. Lambdas without a group
# fall back to per-name selection (SELECT_<LAMBDA_NAME>).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REGISTRY="$ROOT/backend/services/registry.json"

python3 - "$REGISTRY" <<'PY'
import json
import os
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    lambdas = json.load(f)["lambdas"]


def key_for(value: str) -> str:
    return "SELECT_" + re.sub(r"[^A-Za-z0-9]+", "_", value).upper()


selected = []
for item in lambdas:
    group = item.get("group")
    if group:
        wanted = os.environ.get(key_for(group), "").lower() == "true"
    else:
        wanted = os.environ.get(key_for(item["name"]), "").lower() == "true"
    if wanted:
        selected.append(
            {
                "name": item["name"],
                "group": group,
                "lambda_dir": item["dir"],
                "function_name": item["function_name"],
            }
        )

if not selected:
    print("Select at least one group (or lambda).", file=sys.stderr)
    sys.exit(1)

print(json.dumps(selected))
PY

#!/usr/bin/env bash
# Build a GitHub Actions matrix JSON from tools registry checkboxes.
# Set SELECT_<name-with-underscores>=true for each tool (e.g. SELECT_CHALLAN_EXTRACTOR=true).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REGISTRY="$ROOT/tools/registry.json"

python3 - "$REGISTRY" <<'PY'
import json
import os
import re
import sys

path = sys.argv[1]
with open(path, encoding="utf-8") as f:
    tools = json.load(f)["tools"]

selected = []
for item in tools:
    key = "SELECT_" + re.sub(r"[^A-Za-z0-9]+", "_", item["name"]).upper()
    if os.environ.get(key, "").lower() == "true":
        selected.append(
            {
                "name": item["name"],
                "tool_dir": item["dir"],
                "function_name": item["function_name"],
            }
        )

if not selected:
    print("Select at least one tool.", file=sys.stderr)
    sys.exit(1)

print(json.dumps(selected))
PY

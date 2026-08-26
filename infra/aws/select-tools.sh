#!/usr/bin/env bash
# Print a GitHub Actions matrix include JSON for one tool, a function name, or "all".
set -euo pipefail

QUERY="${1:-}"
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REGISTRY="$ROOT/tools/registry.json"

if [[ -z "$QUERY" ]]; then
  echo "usage: $0 <tool-name|function-name|all>" >&2
  exit 2
fi

python3 - "$REGISTRY" "$QUERY" <<'PY'
import json
import sys

path, query = sys.argv[1], sys.argv[2].strip()
with open(path, encoding="utf-8") as f:
    tools = json.load(f)["tools"]

if query.lower() == "all":
    selected = tools
else:
    selected = [t for t in tools if t["name"] == query or t["function_name"] == query]

if not selected:
    names = ", ".join(t["name"] for t in tools)
    print(f"Unknown tool {query!r}. Use a name ({names}), a function name, or all.", file=sys.stderr)
    sys.exit(1)

print(json.dumps([
    {"name": t["name"], "tool_dir": t["dir"], "function_name": t["function_name"]}
    for t in selected
]))
PY

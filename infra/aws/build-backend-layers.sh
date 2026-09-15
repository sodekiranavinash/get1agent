#!/usr/bin/env bash
# Build Lambda layers listed in backend/registry.json.
# Optional first arg: comma-separated layer names (default: all).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REGISTRY="$ROOT/backend/registry.json"
FILTER="${1:-}"

python3 - "$REGISTRY" "$ROOT" "$FILTER" <<'PY'
import json
import subprocess
import sys

path, root, filter_raw = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, encoding="utf-8") as f:
    layers = json.load(f).get("layers", [])

wanted = {name.strip() for name in filter_raw.split(",") if name.strip()}
if wanted:
    layers = [layer for layer in layers if layer["name"] in wanted]
    missing = wanted - {layer["name"] for layer in layers}
    if missing:
        raise SystemExit(f"Unknown layer(s): {', '.join(sorted(missing))}")

if not layers:
    print("No backend layers to build.")
    raise SystemExit(0)

for layer in layers:
    layer_dir = f"{root}/{layer['dir']}"
    print(f"=== Building layer {layer['name']} ({layer_dir}) ===")
    subprocess.run(["make", "-C", layer_dir, "build"], check=True)
    zip_path = f"{layer_dir}/dist/layer.zip"
    with open(zip_path, "rb") as fh:
        size = len(fh.read())
    print(f"Built {zip_path} ({size} bytes)")
PY

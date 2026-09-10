#!/usr/bin/env bash
# Start every local Lambda from local/routes.json plus the gateway, with one
# command. Ctrl+C stops everything. No AWS, no Docker.
#
# Usage: bash local/dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG_DIR="${TMPDIR:-/tmp}"
PIDS=()

cleanup() {
  echo
  echo "stopping local services..."
  for pid in "${PIDS[@]:-}"; do
    kill "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

while IFS=: read -r name port; do
  [[ -z "$name" ]] && continue
  echo "starting ${name} on :${port}"
  PORT="$port" bash "$ROOT/local/run.sh" "$name" > "${LOG_DIR}/get1agent-${name}.log" 2>&1 &
  PIDS+=($!)
done < <(python3 -c "import json; [print(f\"{s['name']}:{s['port']}\") for s in json.load(open('$ROOT/local/routes.json'))['services']]")

echo
echo "logs:    ${LOG_DIR}/get1agent-*.log"
echo "follow:  tail -f ${LOG_DIR}/get1agent-*.log"
echo "gateway: http://localhost:9000  (UI base URL)"
echo "press Ctrl+C to stop"
echo
python3 -u "$ROOT/local/gateway.py"

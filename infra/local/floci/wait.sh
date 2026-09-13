#!/usr/bin/env bash
# Wait until the Floci stack is ready AND the init hook finished provisioning.
# Fails fast (non-zero) if the provisioning script errored, so `make floci`
# never starts the API against a half-built stack.
set -euo pipefail

ENDPOINT="${FLOCI_ENDPOINT:-http://localhost:4566}"
TIMEOUT="${FLOCI_WAIT_TIMEOUT:-180}"

deadline=$((SECONDS + TIMEOUT))
while (( SECONDS < deadline )); do
  body="$(curl -fsS "$ENDPOINT/_floci/init" 2>/dev/null || true)"
  if [[ -n "$body" ]]; then
    state="$(python3 - "$body" <<'PY'
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    print("waiting")
    raise SystemExit
if not data.get("completed", {}).get("ready"):
    print("waiting")
    raise SystemExit
scripts = data.get("scripts", {}).get("ready", [])
bad = [s for s in scripts if s.get("state") not in (None, "successful")]
print("failed" if bad else "ready")
PY
)"
    case "$state" in
      ready)
        echo "[floci-wait] ready (provisioning succeeded)"
        exit 0
        ;;
      failed)
        echo "[floci-wait] init hook provisioning failed:" >&2
        python3 - "$body" >&2 <<'PY'
import json, sys
data = json.loads(sys.argv[1])
for script in data.get("scripts", {}).get("ready", []):
    print(f"  {script.get('script')}: state={script.get('state')} rc={script.get('return_code')}")
PY
        exit 1
        ;;
    esac
  fi
  sleep 2
done

echo "[floci-wait] timed out after ${TIMEOUT}s waiting for $ENDPOINT/_floci/init" >&2
exit 1

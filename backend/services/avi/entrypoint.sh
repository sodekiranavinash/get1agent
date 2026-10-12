#!/usr/bin/env bash
# Avi container entrypoint: the agent service plus the MicroVM streaming proxy.
#
# Two processes, one container:
#   * the agent (FastAPI, LangChain Deep Agents) on the loopback port
#   * the proxy (Node) on the MicroVM ingress port, which is the only thing
#     exposed — it forwards every request to the agent and streams SSE back
#
# The proxy waits for the agent to answer /ping, so the first request a browser
# makes does not race a cold Python import. If either process dies the container
# exits, so a crash surfaces as a failed run rather than a half-working service.
set -euo pipefail

AGENT_PORT="${AVI_PORT:-8000}"
PROXY_PORT="${PORT:-8080}"
AGENT_URL="http://127.0.0.1:${AGENT_PORT}"
export AVI_AGENT_URL="$AGENT_URL"

log() { printf '{"level":"info","message":"%s"}\n' "$1"; }

log "starting avi agent on :${AGENT_PORT}"
python /app/main.py &
AGENT_PID=$!

# If the agent exits, take the container down with it.
trap 'kill "$AGENT_PID" 2>/dev/null || true' TERM INT

log "waiting for the agent to become ready"
for _ in $(seq 1 60); do
  if ! kill -0 "$AGENT_PID" 2>/dev/null; then
    log "agent exited during startup"
    exit 1
  fi
  if python - "$AGENT_URL" <<'PY' 2>/dev/null
import sys, urllib.request
url = sys.argv[1] + "/ping"
try:
    with urllib.request.urlopen(url, timeout=2) as response:
        sys.exit(0 if response.status == 200 else 1)
except Exception:
    sys.exit(1)
PY
  then
    log "agent is ready"
    break
  fi
  sleep 1
done

log "starting avi microvm proxy on :${PROXY_PORT}"
node /app/microvm/app.mjs &
PROXY_PID=$!

# Whichever exits first ends the container.
wait -n "$AGENT_PID" "$PROXY_PID"
EXIT_CODE=$?
log "a process exited (code ${EXIT_CODE}); shutting down"
kill "$AGENT_PID" "$PROXY_PID" 2>/dev/null || true
exit "$EXIT_CODE"

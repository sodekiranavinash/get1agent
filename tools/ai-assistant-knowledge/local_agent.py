"""Run AI Assistant's Lambda handler locally, on the **local** Floci stack.

This is the local stand-in for API Gateway. In production the browser POSTs to two
API Gateway routes, the authorizer validates the Auth0 JWT (on `/ask` only) and the
Lambda reads the verified claims; locally there is no gateway, so
`backend/ai-assistant/main.py` translates HTTP into the same payload-format-2.0
event, verifies the token itself (`src/local_auth.py`) and calls the **same**
`handler.lambda_handler`. Nothing about the turn is reimplemented locally.

**Guests work with no setup at all** — the widget serves the landing page through
the `/guest` route, which has no authorizer in either environment. The signed-in
path needs a real Auth0 token, which the SPA already sends.

    python3 tools/ai-assistant-knowledge/local_agent.py

Then, in `frontend/.env.local`:

    VITE_AI_ASSISTANT_URL=http://localhost:8091

and `make ui`. Open `/` (signed out) to exercise the guest path.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_env  # noqa: E402  (same directory)

local_env.apply()
# Local development is the *only* place the service is reached without API Gateway,
# so the Auth0 JWT authorizer that normally protects `/ask` is absent and
# `main.py` verifies the token instead. That is fine for loopback and unacceptable
# anywhere else, so bind to loopback and say so loudly.
os.environ.setdefault("AI_ASSISTANT_HOST", "127.0.0.1")

for extra in (REPO_ROOT / "backend" / "packages", REPO_ROOT / "backend" / "ai-assistant"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))


def _raise_local_limits() -> None:
    """Give local development a much bigger guest budget.

    The shipped guest cap is 6 per hour per IP — right for an unauthenticated
    public surface, and useless for testing, because a developer would hit it
    within a few questions and reasonably conclude AI Assistant was broken. The limit stays
    a real limit (set ``AI_ASSISTANT_LOCAL_RAISE_LIMITS=false`` to exercise the shipped
    numbers), and this only ever runs when the agent is started by this script.
    """
    if (os.environ.get("AI_ASSISTANT_LOCAL_RAISE_LIMITS") or "true").lower() in ("0", "false", "no"):
        return
    try:
        from data.repositories import ai_assistant_settings  # noqa: PLC0415

        ai_assistant_settings.update_settings(
            {"guestPerHour": 200, "guestPerDay": 1000, "userPerHour": 500, "userPerDay": 5000},
            updated_by="local-dev",
        )
        print("  limits     : raised for local dev (guest 200/hour; set AI_ASSISTANT_LOCAL_RAISE_LIMITS=false to keep the shipped caps)")
    except Exception as exc:  # noqa: BLE001 - never block the dev server on this
        print(f"  limits     : could not raise (continuing with defaults): {exc}", file=sys.stderr)


def main() -> int:
    import uvicorn  # noqa: PLC0415

    # Imported here so `--help`-style failures and a missing dev dependency surface
    # as a clear message rather than at module scope.
    from main import app  # noqa: PLC0415

    host = os.environ["AI_ASSISTANT_HOST"]
    port = int(os.environ.get("AI_ASSISTANT_PORT") or "8091")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "Refusing to bind the local AI Assistant service to a non-loopback address: it "
            "stands in for API Gateway, and `main.py` — not a managed authorizer — is what "
            "verifies the JWT here.",
            file=sys.stderr,
        )
        return 2

    _raise_local_limits()
    print(f"AI Assistant (local) on http://{host}:{port}")
    print("  routes     : POST /v1/ai-assistant/ask (JWT verified here) · /v1/ai-assistant/guest (none)")
    print("  health     : GET  /health")
    print("  scope      :", os.environ.get("AI_ASSISTANT_SCOPE"), "/", os.environ.get("AI_ASSISTANT_KB_ID"))
    print("  embeddings :", os.environ.get("EMBED_MODE"), "via", os.environ.get("LOCAL_EMBED_URL"))
    print("  models     : Bedrock (real AWS); guests served here, per-IP limited")
    print()
    print("  frontend/.env.local:")
    print(f"    VITE_AI_ASSISTANT_URL=http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

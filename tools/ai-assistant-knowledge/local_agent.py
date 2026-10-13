"""Run AI Assistant's agent service against the **local** Floci stack.

This is the local stand-in for the deployed ingress. In production the browser
streams from a MicroVM whose session token the control-plane Lambda signed after
API Gateway verified the Auth0 JWT; locally there is no gateway and no MicroVM, so
the widget talks to this process directly (``VITE_AI_ASSISTANT_URL`` +
``VITE_AI_ASSISTANT_MICROVM=false``) and **guests** are served here too — which is what
makes the landing page work.

    python3 tools/ai-assistant-knowledge/local_agent.py

Then, in `frontend/.env.local`:

    VITE_AI_ASSISTANT_URL=http://localhost:8091
    VITE_AI_ASSISTANT_MICROVM=false

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
# Local development is the *only* place the service is reached without a gateway,
# so the Auth0 JWT authorizer that normally protects it is absent. That is fine for
# loopback and unacceptable anywhere else, so bind to loopback and say so loudly.
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

    from main import app  # noqa: PLC0415

    host = os.environ["AI_ASSISTANT_HOST"]
    port = int(os.environ.get("AI_ASSISTANT_PORT") or "8091")
    if host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "Refusing to bind the local AI Assistant service to a non-loopback address: it "
            "has no JWT authorizer in front of it.",
            file=sys.stderr,
        )
        return 2

    _raise_local_limits()
    print(f"AI Assistant (local) on http://{host}:{port}")
    print("  scope      :", os.environ.get("AI_ASSISTANT_SCOPE"), "/", os.environ.get("AI_ASSISTANT_KB_ID"))
    print("  embeddings :", os.environ.get("EMBED_MODE"), "via", os.environ.get("LOCAL_EMBED_URL"))
    print("  models     : Bedrock (real AWS); guests served here, per-IP limited")
    print()
    print("  frontend/.env.local:")
    print(f"    VITE_AI_ASSISTANT_URL=http://{host}:{port}")
    print("    VITE_AI_ASSISTANT_MICROVM=false")
    uvicorn.run(app, host=host, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

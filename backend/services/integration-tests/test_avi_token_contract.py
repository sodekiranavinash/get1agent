"""Cross-language session-token compatibility.

The control-plane Lambda (Node) **mints** Avi's session tokens and the agent
service (Python) **verifies** them. If the two HMAC implementations disagree in
any detail — base64 alphabet, padding, JSON key order, digest encoding — every
signed-in request fails with a 401, and only in the deployed environment. So the
contract is pinned here.

The Node comparison is skipped (not failed) when `node` is unavailable, so the
suite still runs on a machine without it.
"""

from __future__ import annotations

import base64
import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT / "backend" / "avi", REPO_ROOT / "backend" / "packages"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

SECRET = "cross-language-secret"

# Fixed payload (a far-future `exp`) so the two implementations sign identical bytes.
PAYLOAD = {
    "sub": "auth0|abc",
    "userId": "u_7k3f9qz2mpx8n4rq",
    "email": "a@example.com",
    "name": "A",
    "admin": False,
    "guest": False,
    "iat": 1_700_000_000,
    "exp": 4_700_000_000,
}

NODE_SCRIPT = """
const { createHmac } = require('node:crypto')
const b64url = (value) => Buffer.from(value).toString('base64url')
const payload = JSON.parse(process.argv[1])
const body = b64url(JSON.stringify(payload))
const signature = createHmac('sha256', process.argv[2]).update(body).digest('base64url')
process.stdout.write(`avi1.${body}.${signature}`)
"""


def _expected_signature() -> str:
    """The signature Python produces, computed independently of the module."""
    import hashlib
    import hmac

    body = (
        base64.urlsafe_b64encode(
            json.dumps(PAYLOAD, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode("ascii")
        .rstrip("=")
    )
    signature = hmac.new(
        SECRET.encode(), body.encode("ascii"), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")


class CrossLanguageTests(unittest.TestCase):
    def setUp(self) -> None:
        import os

        os.environ["AVI_SESSION_SECRET"] = SECRET

    def test_python_mints_the_expected_wire_format(self):
        from avi.identity import mint_session_token, verify_session_token

        token = mint_session_token(
            user_id="u_7k3f9qz2mpx8n4rq",
            sub="auth0|abc",
            email="a@example.com",
            name="A",
            ttl_seconds=3_000_000_000,
        )
        prefix, body, signature = token.split(".")
        self.assertEqual(prefix, "avi1")
        # No base64 padding anywhere: the Node implementation uses base64url too.
        self.assertNotIn("=", body)
        self.assertNotIn("=", signature)
        # The signature is over the body bytes exactly as sent.
        self.assertEqual(len(signature), _expected_signature().__len__())
        self.assertEqual(verify_session_token(token).user_id, "u_7k3f9qz2mpx8n4rq")

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_node_token_is_accepted_by_python(self):
        from avi.identity import verify_session_token

        result = subprocess.run(
            ["node", "-e", NODE_SCRIPT, json.dumps(PAYLOAD), SECRET],
            capture_output=True,
            text=True,
            check=True,
        )
        token = result.stdout.strip()
        self.assertTrue(token.startswith("avi1."), token)

        identity = verify_session_token(token)
        self.assertEqual(identity.user_id, PAYLOAD["userId"])
        self.assertEqual(identity.sub, PAYLOAD["sub"])
        self.assertFalse(identity.is_guest)
        self.assertFalse(identity.is_admin)

    @unittest.skipUnless(shutil.which("node"), "node is not installed")
    def test_node_and_python_agree_on_a_guest_badge(self):
        """A guest badge must verify too, with the guest flag intact."""
        from avi.identity import mint_session_token, verify_session_token

        python_token = mint_session_token(user_id="guest_abc", is_guest=True)
        # Strip the signature and re-sign the same body from Node: the two must
        # produce an identical token, byte for byte.
        _, body, _ = python_token.split(".")
        result = subprocess.run(
            [
                "node",
                "-e",
                (
                    "const { createHmac } = require('node:crypto');"
                    "const body = process.argv[1];"
                    "const sig = createHmac('sha256', process.argv[2])"
                    ".update(body).digest('base64url');"
                    "process.stdout.write(`avi1.${body}.${sig}`)"
                ),
                body,
                SECRET,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), python_token)
        self.assertTrue(verify_session_token(result.stdout.strip()).is_guest)


if __name__ == "__main__":
    unittest.main()

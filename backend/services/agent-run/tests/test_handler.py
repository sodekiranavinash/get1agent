"""Unit tests for the agent-run proxy: token verification + session binding."""

from __future__ import annotations

import json
import sys
import time
import types
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))
sys.path.insert(0, str(APP_ROOT.parents[1] / "packages"))

# ``handler`` imports the Lambda-only ``awslambda`` module; stub it so the
# module can be imported and its pure helpers tested.
_stub = types.ModuleType("awslambda")
_stub.streamifyResponse = lambda fn: fn  # type: ignore[attr-defined]
sys.modules.setdefault("awslambda", _stub)

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: E402

from core.jwt import TokenError, verify_token  # noqa: E402
from handler import _session_id  # noqa: E402

ISSUER = "https://get1agent.us.auth0.com/"
AUDIENCE = "https://api.get1agent.com"
KID = "test-key"


def _keypair() -> tuple[object, object]:
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def _jwks(public_key: object, kid: str = KID) -> dict:
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(public_key))
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    return {"keys": [jwk]}


def _token(private: object, kid: str = KID, **overrides: object) -> str:
    now = int(time.time())
    claims: dict[str, object] = {
        "sub": "auth0|abc",
        "iss": ISSUER,
        "aud": AUDIENCE,
        "iat": now,
        "exp": now + 300,
    }
    claims.update(overrides)
    return jwt.encode(claims, private, algorithm="RS256", headers={"kid": kid})


class VerifyTokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.private, cls.public = _keypair()
        cls.jwks = _jwks(cls.public)

    def verify(self, token: str, jwks: dict | None = None) -> dict:
        return verify_token(
            token, jwks=jwks or self.jwks, audience=[AUDIENCE], issuer=ISSUER
        )

    def test_valid_token_returns_claims(self) -> None:
        claims = self.verify(_token(self.private))
        self.assertEqual(claims["sub"], "auth0|abc")

    def test_wrong_audience_rejected(self) -> None:
        with self.assertRaises(TokenError):
            self.verify(_token(self.private, aud="https://other.example"))

    def test_expired_token_rejected(self) -> None:
        with self.assertRaises(TokenError):
            self.verify(_token(self.private, exp=int(time.time()) - 10))

    def test_wrong_issuer_rejected(self) -> None:
        with self.assertRaises(TokenError):
            self.verify(_token(self.private, iss="https://evil.example/"))

    def test_signature_from_another_key_rejected(self) -> None:
        other_private, _ = _keypair()
        with self.assertRaises(TokenError):
            self.verify(_token(other_private))

    def test_unknown_kid_rejected(self) -> None:
        with self.assertRaises(TokenError):
            self.verify(_token(self.private, kid="missing"))

    def test_alg_none_rejected(self) -> None:
        token = jwt.encode({"sub": "x"}, "", algorithm="none", headers={"kid": KID})
        with self.assertRaises(TokenError):
            self.verify(token)

    def test_malformed_token_rejected(self) -> None:
        for bad in ("", "not-a-token", "a.b.c"):
            with self.assertRaises(TokenError):
                self.verify(bad)


class SessionIdTests(unittest.TestCase):
    def test_deterministic_per_user_and_conversation(self) -> None:
        first = _session_id("auth0|abc", "42")
        self.assertEqual(first, _session_id("auth0|abc", "42"))
        self.assertEqual(len(first), 64)

    def test_different_users_do_not_collide(self) -> None:
        self.assertNotEqual(_session_id("auth0|abc", "42"), _session_id("auth0|xyz", "42"))

    def test_different_conversations_do_not_collide(self) -> None:
        self.assertNotEqual(_session_id("auth0|abc", "42"), _session_id("auth0|abc", "43"))

    def test_missing_conversation_still_scoped_to_user(self) -> None:
        self.assertEqual(len(_session_id("auth0|abc", "")), 64)
        self.assertNotEqual(_session_id("auth0|abc", ""), _session_id("auth0|xyz", ""))


if __name__ == "__main__":
    unittest.main()

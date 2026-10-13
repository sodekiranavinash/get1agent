"""The local development path must not be a weaker version of production.

Two things are being pinned here, and both matter because local dev is where a
security regression is easiest to introduce and hardest to notice:

* **`src/local_auth.py`** is the *only* JWT verification in AI Assistant — in
  production the gateway does it, so this module exists purely for local dev. If it
  accepted an unsigned or wrongly-signed token, a developer's machine would happily
  serve one account's data to another, and nobody would find out.
* **`main.py`** stands in for API Gateway, which means it owns the per-route
  `authorization_type`. A JWT-protected route that quietly falls back to the guest
  path would hide the difference between the two audiences.

The local server is exercised with the turn engine stubbed, so these tests need no
AWS, no Bedrock and no network — they test the translation and the auth decision.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parent / "packages"
for extra in (str(SERVICE_ROOT), str(PACKAGES)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402

from src import local_auth  # noqa: E402

ISSUER = "https://example-tenant.us.auth0.com"
AUDIENCE = "https://api.example.com"
KID = "test-key-1"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class _Tenant:
    """A throwaway RSA keypair that stands in for the Auth0 tenant."""

    def __init__(self, kid: str = KID) -> None:
        self.kid = kid
        self.private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        numbers = self.private.public_key().public_numbers()
        self.jwk = {
            "kty": "RSA",
            "kid": kid,
            "use": "sig",
            "alg": "RS256",
            "n": _b64url(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
            "e": _b64url(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
        }

    def sign(self, claims: dict, *, headers: dict | None = None, key=None) -> str:
        header = {"alg": "RS256", "kid": self.kid, "typ": "JWT"}
        header.update(headers or {})
        body = f"{_b64url(json.dumps(header).encode())}.{_b64url(json.dumps(claims).encode())}"
        signature = (key or self.private).sign(
            body.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()
        )
        return f"{body}.{_b64url(signature)}"

    def claims(self, **overrides) -> dict:
        now = int(time.time())
        claims = {
            "sub": "auth0|tester",
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now - 10,
            "exp": now + 600,
        }
        claims.update(overrides)
        return claims


class LocalAuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenant = _Tenant()
        self._env = {
            "AI_ASSISTANT_AUTH_ISSUER": ISSUER,
            "AI_ASSISTANT_AUTH_AUDIENCE": AUDIENCE,
            # Skip discovery: point straight at a JWKS URL and stub the fetch.
            "AI_ASSISTANT_AUTH_JWKS_URL": "https://example.test/jwks.json",
        }
        self._saved = {key: os.environ.get(key) for key in self._env}
        os.environ.update(self._env)
        local_auth._jwks_cache.clear()
        self._real_fetch = local_auth._fetch_json
        local_auth._fetch_json = lambda url, timeout=10: {"keys": [self.tenant.jwk]}

    def tearDown(self) -> None:
        local_auth._fetch_json = self._real_fetch
        local_auth._jwks_cache.clear()
        for key, value in self._saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_a_properly_signed_token_verifies(self) -> None:
        claims = local_auth.verify(self.tenant.sign(self.tenant.claims()))
        self.assertEqual(claims["sub"], "auth0|tester")

    def test_a_token_signed_by_another_key_is_rejected(self) -> None:
        """The whole point: a valid-looking token from the wrong key must fail."""
        other = _Tenant()
        token = self.tenant.sign(self.tenant.claims(), key=other.private)
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth.verify(token)

    def test_a_tampered_payload_is_rejected(self) -> None:
        token = self.tenant.sign(self.tenant.claims())
        header, _, signature = token.split(".")
        forged = _b64url(json.dumps(self.tenant.claims(sub="auth0|victim")).encode())
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth.verify(f"{header}.{forged}.{signature}")

    def test_the_alg_none_downgrade_is_rejected(self) -> None:
        """The classic JWT confusion attack: `alg: none` must never be honoured."""
        header = _b64url(json.dumps({"alg": "none", "kid": KID}).encode())
        payload = _b64url(json.dumps(self.tenant.claims()).encode())
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth.verify(f"{header}.{payload}.")

    def test_an_expired_token_is_rejected(self) -> None:
        token = self.tenant.sign(self.tenant.claims(exp=int(time.time()) - 600))
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth.verify(token)

    def test_a_wrong_audience_is_rejected(self) -> None:
        token = self.tenant.sign(self.tenant.claims(aud="https://api.somewhere-else.com"))
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth.verify(token)

    def test_a_wrong_issuer_is_rejected(self) -> None:
        token = self.tenant.sign(self.tenant.claims(iss="https://evil.example.com"))
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth.verify(token)

    def test_an_audience_list_containing_ours_verifies(self) -> None:
        token = self.tenant.sign(
            self.tenant.claims(aud=[AUDIENCE, "https://api.other.example.com"])
        )
        self.assertTrue(local_auth.verify(token))

    def test_a_malformed_token_is_rejected(self) -> None:
        for candidate in ("", "not-a-jwt", "a.b", "a.b.c.d"):
            with self.subTest(token=candidate):
                with self.assertRaises(local_auth.LocalAuthError):
                    local_auth.verify(candidate)

    def test_a_rotated_key_is_refetched(self) -> None:
        """An unknown kid must trigger one refetch, not a permanent failure.

        This is real rotation: the second key has a **different kid**, so the first
        lookup misses (rather than finding a same-kid key that fails the signature,
        which would be a different and worse situation).
        """
        rotated = _Tenant(kid="test-key-2")
        responses = [{"keys": [self.tenant.jwk]}, {"keys": [rotated.jwk]}]
        calls = {"count": 0}

        def fetch(url, timeout=10):
            response = responses[min(calls["count"], len(responses) - 1)]
            calls["count"] += 1
            return response

        local_auth._fetch_json = fetch
        token = rotated.sign(rotated.claims())
        self.assertTrue(local_auth.verify(token))
        self.assertGreaterEqual(calls["count"], 2)

    def test_a_missing_issuer_configuration_fails_closed(self) -> None:
        os.environ.pop("AI_ASSISTANT_AUTH_ISSUER", None)
        os.environ.pop("VITE_AUTH_DOMAIN", None)
        os.environ.pop("AUTH_DOMAIN", None)
        with self.assertRaises(local_auth.LocalAuthError):
            local_auth._issuer()


class LocalServerTests(unittest.TestCase):
    """`main.py` as the local stand-in for API Gateway's routing and authorizer."""

    @classmethod
    def setUpClass(cls) -> None:
        import main  # noqa: PLC0415

        cls.main = main
        cls.handler = main.lambda_handler

    def setUp(self) -> None:
        from fastapi.testclient import TestClient  # noqa: PLC0415

        import handler  # noqa: PLC0415
        import src.conversations as conversations  # noqa: PLC0415
        import src.traces as traces  # noqa: PLC0415

        self.handler = handler
        self.turn: list[dict] = []
        self._patched: list[tuple[object, str, object]] = []
        self._patch(handler, "check_and_count", lambda caller: (True, 0))
        self._patch(handler, "_run_frames", self._fake_frames)
        self._patch(handler.settings, "enabled", lambda: True)
        self._patch(handler.settings, "guest_enabled", lambda: True)
        self._patch(handler.settings, "max_input_chars", lambda: 4000)
        self._patch(handler.settings, "max_history_turns", lambda: 12)
        self._patch(handler.settings, "model", lambda: "test-model")
        self._patch(handler, "get_or_create_user", lambda claims: {"userId": "u_local"})
        self._patch(conversations, "ensure_conversation", lambda *a, **k: "conv_local")
        self._patch(conversations, "record_turn", lambda *a, **k: None)
        self._patch(traces, "record_trace", lambda *a, **k: None)
        self.client = TestClient(self.main.app)

    def tearDown(self) -> None:
        for target, name, original in reversed(self._patched):
            setattr(target, name, original)

    def _patch(self, target: object, name: str, value: object) -> None:
        self._patched.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def _fake_frames(self, **kwargs) -> list[dict]:
        self.turn.append(kwargs)
        return [
            {"type": "run.started", "runId": "r", "agentId": "ai-assistant", "sessionId": "r"},
            {"type": "text", "data": "hello"},
            {"type": "run.completed", "text": "hello", "stopReason": "end_turn"},
        ]

    @staticmethod
    def _frames(response) -> list[dict]:
        return [
            json.loads(part[len("data: ") :].strip())
            for part in response.text.split("\n\n")
            if part.startswith("data: ")
        ]

    def test_health_reports_ok(self) -> None:
        self.assertEqual(self.client.get("/health").status_code, 200)

    def test_the_guest_route_serves_a_guest_turn(self) -> None:
        response = self.client.post("/v1/ai-assistant/guest", json={"question": "hi"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response.headers["content-type"])
        self.assertEqual(
            [frame["type"] for frame in self._frames(response)],
            ["run.started", "text", "run.completed"],
        )
        self.assertTrue(self.turn[-1]["identity"].is_guest)

    def test_the_ask_route_without_a_token_is_401(self) -> None:
        """A JWT route must not silently downgrade to the guest path."""
        response = self.client.post("/v1/ai-assistant/ask", json={"question": "hi"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.turn, [])

    def test_the_ask_route_with_a_bad_token_is_401(self) -> None:
        response = self.client.post(
            "/v1/ai-assistant/ask",
            json={"question": "hi"},
            headers={"authorization": "Bearer not.a.jwt"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.turn, [])

    def test_an_unknown_route_is_404(self) -> None:
        self.assertEqual(self.client.post("/v1/ai-assistant/nope", json={}).status_code, 404)

    def test_a_verified_token_reaches_the_signed_in_path(self) -> None:
        """With `verify` stubbed to succeed, `/ask` must run the signed-in turn."""
        original = self.main._claims_for
        self.main._claims_for = lambda token: {"sub": "auth0|local"}
        try:
            response = self.client.post(
                "/v1/ai-assistant/ask",
                json={"question": "hi"},
                headers={"authorization": "Bearer stubbed.token.value"},
            )
        finally:
            self.main._claims_for = original
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self.turn[-1]["identity"].is_guest)


if __name__ == "__main__":
    unittest.main()

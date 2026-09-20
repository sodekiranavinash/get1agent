"""Unit tests for the OAuth discovery/registration/PKCE helpers.

Run with: ``make -C backend/services/mcp-connections test``
"""

from __future__ import annotations

import base64
import hashlib
import sys
import unittest
import urllib.parse
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
BACKEND = APP.parents[1]
sys.path.insert(0, str(BACKEND / "packages"))

from core import oauth  # noqa: E402


class PkceTests(unittest.TestCase):
    def test_challenge_is_s256_of_verifier(self) -> None:
        verifier, challenge = oauth.pkce_pair()
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        self.assertEqual(challenge, expected)

    def test_pairs_are_unique(self) -> None:
        self.assertNotEqual(oauth.pkce_pair()[0], oauth.pkce_pair()[0])


class AuthorizationUrlTests(unittest.TestCase):
    def test_includes_pkce_state_and_resource(self) -> None:
        url = oauth.build_authorization_url(
            "https://auth.example.com/authorize",
            client_id="cid",
            redirect_uri="https://api.example.com/v1/mcp/oauth/callback",
            scopes=["read", "write"],
            state="st",
            code_challenge="chal",
            resource="https://mcp.example.com/mcp",
        )
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["scope"], ["read write"])
        self.assertEqual(query["resource"], ["https://mcp.example.com/mcp"])


class TokenResponseTests(unittest.TestCase):
    def test_json_response(self) -> None:
        parsed = oauth._parse_token_response(
            b'{"access_token":"a","refresh_token":"r","token_type":"bearer","expires_in":"3600"}'
        )
        self.assertEqual(parsed["access_token"], "a")
        self.assertEqual(parsed["expires_in"], 3600)

    def test_form_encoded_response(self) -> None:
        parsed = oauth._parse_token_response(b"access_token=a&refresh_token=r&scope=x+y")
        self.assertEqual(parsed["access_token"], "a")
        self.assertEqual(parsed["scope"], ["x", "y"])

    def test_missing_token_raises(self) -> None:
        with self.assertRaises(oauth.OAuthError):
            oauth._parse_token_response(b'{"error":"invalid_grant"}')


class DiscoveryTests(unittest.TestCase):
    def _fake_get_json(self, url: str, timeout: int):
        if "oauth-protected-resource" in url:
            return 200, {
                "resource": "https://mcp.example.com/mcp",
                "authorization_servers": ["https://auth.example.com"],
                "scopes_supported": ["read"],
            }
        if "oauth-authorization-server" in url:
            return 200, {
                "issuer": "https://auth.example.com",
                "authorization_endpoint": "https://auth.example.com/authorize",
                "token_endpoint": "https://auth.example.com/token",
            }
        return 404, None

    def test_full_discovery(self) -> None:
        original = oauth._get_json
        oauth._get_json = self._fake_get_json  # type: ignore[assignment]
        try:
            metadata = oauth.discover("https://mcp.example.com/mcp")
        finally:
            oauth._get_json = original  # type: ignore[assignment]
        self.assertEqual(metadata["token_endpoint"], "https://auth.example.com/token")
        self.assertEqual(metadata["resource"], "https://mcp.example.com/mcp")
        self.assertEqual(metadata["scopes_supported"], ["read"])

    def test_override_short_circuits_discovery(self) -> None:
        metadata = oauth.discover(
            "https://api.githubcopilot.com/mcp/",
            override={
                "authorization_endpoint": "https://github.com/login/oauth/authorize",
                "token_endpoint": "https://github.com/login/oauth/access_token",
                "resource": "https://api.githubcopilot.com/mcp",
                "scopes": ["repo"],
            },
        )
        self.assertEqual(metadata["authorization_endpoint"], "https://github.com/login/oauth/authorize")
        self.assertEqual(metadata["scopes_supported"], ["repo"])

    def test_missing_endpoints_raise(self) -> None:
        original = oauth._get_json
        oauth._get_json = lambda url, timeout: (404, None)  # type: ignore[assignment]
        try:
            with self.assertRaises(oauth.OAuthError):
                oauth.discover("https://mcp.example.com/mcp")
        finally:
            oauth._get_json = original  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()

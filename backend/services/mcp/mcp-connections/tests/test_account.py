"""Unit tests for connected-account identity (best-effort).

The provider's identity endpoint is declared on the catalog entry; a failure to
read it must never break a successful connection.

Run with: ``make -C backend/services/mcp/mcp-connections test``
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from src import catalog, service  # noqa: E402


class _FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *_exc) -> bool:
        return False


class AccountTests(unittest.TestCase):
    def test_account_field_reads_dotted_paths(self) -> None:
        self.assertEqual(
            service._account_field({"user": {"login": "x"}}, "user.login"), "x"
        )
        self.assertIsNone(service._account_field({"user": {}}, "user.login"))
        self.assertIsNone(service._account_field({"login": ""}, "login"))
        self.assertIsNone(service._account_field({"login": "x"}, None))

    def test_fetch_account_extracts_fields(self) -> None:
        payload = json.dumps(
            {"login": "octocat", "name": "The Octocat", "avatar_url": "https://a/x.png"}
        ).encode()
        with mock.patch.object(
            service.urllib.request, "urlopen", return_value=_FakeResponse(payload)
        ) as urlopen:
            account = service._fetch_account(catalog.get_entry("github"), "tok")
        self.assertEqual(account["accountLogin"], "octocat")
        self.assertEqual(account["accountName"], "The Octocat")
        self.assertEqual(account["accountAvatarUrl"], "https://a/x.png")
        # The access token is sent as a bearer header to the declared endpoint.
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "https://api.github.com/user")
        self.assertEqual(request.get_header("Authorization"), "Bearer tok")

    def test_fetch_account_swallows_errors(self) -> None:
        with mock.patch.object(
            service.urllib.request, "urlopen", side_effect=OSError("boom")
        ):
            self.assertEqual(
                service._fetch_account(catalog.get_entry("github"), "tok"), {}
            )

    def test_fetch_account_without_endpoint_or_token(self) -> None:
        self.assertEqual(service._fetch_account(None, "tok"), {})
        self.assertEqual(service._fetch_account({"id": "svc"}, "tok"), {})
        self.assertEqual(service._fetch_account(catalog.get_entry("github"), None), {})


if __name__ == "__main__":
    unittest.main()

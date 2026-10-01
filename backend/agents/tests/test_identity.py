"""Unit tests for identity resolution, incl. the platform service caller."""

from __future__ import annotations

import base64
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "packages"))

from agentflow import identity  # noqa: E402


def _token(sub: str) -> str:
    payload = (
        base64.urlsafe_b64encode(json.dumps({"sub": sub}).encode()).decode().rstrip("=")
    )
    return f"header.{payload}.signature"


def _context(token: str) -> mock.Mock:
    return mock.Mock(request_headers={"authorization": f"Bearer {token}"})


class ServiceCallerTests(unittest.TestCase):
    def test_service_sub_uses_payload_user_id(self) -> None:
        with mock.patch.dict(os.environ, {"SERVICE_AUTH_CLIENT_ID": "svc123"}):
            with mock.patch("data.repositories.users.get_user_by_sub") as lookup:
                user_id = identity.resolve_user_id(
                    {"userId": "u_abc"}, _context(_token("svc123@clients"))
                )
        self.assertEqual(user_id, "u_abc")
        lookup.assert_not_called()

    def test_service_without_user_id_raises(self) -> None:
        with mock.patch.dict(os.environ, {"SERVICE_AUTH_CLIENT_ID": "svc123"}):
            with self.assertRaises(ValueError):
                identity.resolve_user_id({}, _context(_token("svc123@clients")))

    def test_unconfigured_service_is_not_trusted(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SERVICE_AUTH_CLIENT_ID", None)
            with mock.patch(
                "data.repositories.users.get_user_by_sub", return_value=None
            ):
                with self.assertRaises(ValueError):
                    identity.resolve_user_id(
                        {"userId": "u_abc"}, _context(_token("svc123@clients"))
                    )

    def test_regular_user_resolves_via_sub(self) -> None:
        with mock.patch.dict(os.environ, {"SERVICE_AUTH_CLIENT_ID": "svc123"}):
            with mock.patch(
                "data.repositories.users.get_user_by_sub",
                return_value={"userId": "u_1"},
            ) as lookup:
                user_id = identity.resolve_user_id({}, _context(_token("auth0|user")))
        self.assertEqual(user_id, "u_1")
        lookup.assert_called_once()

    def test_local_fallback_uses_payload(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SERVICE_AUTH_CLIENT_ID", None)
            self.assertEqual(
                identity.resolve_user_id({"userId": "u_local"}, mock.Mock(request_headers={})),
                "u_local",
            )

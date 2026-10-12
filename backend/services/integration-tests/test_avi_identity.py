"""Avi identity and rate limiting.

No model calls: these are the two guards that sit in front of every turn, so they
are tested directly and hard. The properties that matter are the *negative* ones —
a forged token must not be accepted, an expired one must not be, and one caller
must not be able to consume another's budget.
"""

from __future__ import annotations

import os
import sys
import time
import unittest
from pathlib import Path

import pytest
from moto import mock_aws

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT / "backend" / "avi", REPO_ROOT / "backend" / "packages"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

# The service signs its session tokens; a missing secret must fail closed, so the
# tests that need a working token set one explicitly.
os.environ.setdefault("AVI_SESSION_SECRET", "test-session-secret")

from conftest import _create_table  # noqa: E402
from avi import identity, limits  # noqa: E402
from avi.limits import Caller, SURFACE_EVAL, SURFACE_GUEST, SURFACE_USER  # noqa: E402


class SessionTokenTests(unittest.TestCase):
    """The session token is how the agent service learns who is asking."""

    def test_round_trip_carries_the_identity(self):
        token = identity.mint_session_token(
            user_id="u_7k3f9qz2mpx8n4rq",
            sub="auth0|abc",
            email="a@example.com",
            name="A",
            is_admin=True,
        )
        resolved = identity.verify_session_token(token)
        self.assertEqual(resolved.user_id, "u_7k3f9qz2mpx8n4rq")
        self.assertEqual(resolved.sub, "auth0|abc")
        self.assertTrue(resolved.is_admin)
        self.assertFalse(resolved.is_guest)

    def test_tampered_payload_is_rejected(self):
        """Editing the payload must not survive the signature check."""
        token = identity.mint_session_token(user_id="u_aaaa")
        _, body, signature = token.split(".")
        forged_body = identity._b64(b'{"userId":"u_evil","exp":9999999999}')
        with pytest.raises(identity.IdentityError):
            identity.verify_session_token(f"avi1.{forged_body}.{signature}")

    def test_tampered_signature_is_rejected(self):
        token = identity.mint_session_token(user_id="u_aaaa")
        head, body, _ = token.split(".")
        with pytest.raises(identity.IdentityError):
            identity.verify_session_token(f"{head}.{body}.AAAA")

    def test_expired_token_is_rejected(self):
        token = identity.mint_session_token(user_id="u_aaaa", ttl_seconds=0)
        # ttl is floored at 60s, so build an already-expired payload directly.
        import json as _json

        payload = {"userId": "u_aaaa", "exp": int(time.time()) - 10}
        body = identity._b64(_json.dumps(payload).encode())
        signature = identity._b64(
            identity.hmac.new(identity._secret(), body.encode(), identity.hashlib.sha256).digest()
        )
        with pytest.raises(identity.IdentityError):
            identity.verify_session_token(f"avi1.{body}.{signature}")
        # And the real (still-valid) token is accepted.
        self.assertEqual(identity.verify_session_token(token).user_id, "u_aaaa")

    def test_missing_secret_is_an_error_not_a_default(self):
        """A missing signing secret must fail closed, never fall back."""
        token = identity.mint_session_token(user_id="u_aaaa")
        original = identity.os.environ.pop("AVI_SESSION_SECRET", None)
        agent_secret = identity.os.environ.pop("AGENT_SERVICE_CLIENT_SECRET", None)
        try:
            with pytest.raises(identity.IdentityError):
                identity.verify_session_token(token)
        finally:
            if original is not None:
                identity.os.environ["AVI_SESSION_SECRET"] = original
            if agent_secret is not None:
                identity.os.environ["AGENT_SERVICE_CLIENT_SECRET"] = agent_secret

    def test_garbage_is_rejected(self):
        for bad in ("", "nope", "avi1.only-two", "avi2.a.b", "avi1.!!!.!!!"):
            with pytest.raises(identity.IdentityError):
                identity.verify_session_token(bad)


class ResolveIdentityTests(unittest.TestCase):
    def test_guest_requires_the_guest_flag(self):
        with pytest.raises(identity.IdentityError):
            identity.resolve_identity(None, allow_guest=False)
        guest = identity.resolve_identity(None, allow_guest=True, client_ip="1.2.3.4")
        self.assertTrue(guest.is_guest)

    def test_guest_key_is_stable_and_not_the_raw_ip(self):
        first = identity.guest_identity("1.2.3.4")
        second = identity.guest_identity("1.2.3.4")
        other = identity.guest_identity("5.6.7.8")
        self.assertEqual(first.user_id, second.user_id)
        self.assertNotEqual(first.user_id, other.user_id)
        self.assertNotIn("1.2.3.4", first.user_id)
        self.assertTrue(first.user_id.startswith("guest_"))

    def test_bearer_prefix_is_optional(self):
        token = identity.mint_session_token(user_id="u_aaaa")
        self.assertEqual(identity.resolve_identity(token).user_id, "u_aaaa")
        self.assertEqual(identity.resolve_identity(f"Bearer {token}").user_id, "u_aaaa")

    def test_a_raw_jwt_is_not_accepted_as_a_session_token(self):
        """The service must not silently trust an unverified JWT."""
        with pytest.raises(identity.IdentityError):
            identity.resolve_identity("Bearer eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJ4In0.sig")


@pytest.fixture(autouse=True)
def _aws():
    """A fresh moto DynamoDB table + S3 bucket per test (no AWS, no network)."""
    with mock_aws():
        from data import client as dynamo_client
        from data.repositories import avi_settings

        dynamo_client._table = None
        _create_table()
        avi_settings.invalidate_cache()
        yield
        dynamo_client._table = None
        avi_settings.invalidate_cache()


def _caller(surface: str = SURFACE_USER, key: str = "u_test") -> Caller:
    return Caller(key=key, surface=surface, user_id=key)


class RateLimitTests(unittest.TestCase):
    def test_under_the_limit_is_allowed(self):
        allowed, retry = limits.check_and_count(_caller())
        self.assertTrue(allowed)
        self.assertEqual(retry, 0)

    def test_the_hour_cap_stops_a_burst(self):
        from data.repositories import avi_settings

        avi_settings.invalidate_cache()
        avi_settings.update_settings({"userPerHour": 2, "userPerDay": 100})
        caller = _caller(key="u_burst")
        self.assertTrue(limits.check_and_count(caller)[0])
        self.assertTrue(limits.check_and_count(caller)[0])
        allowed, retry = limits.check_and_count(caller)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)
        self.assertLessEqual(retry, 3601)

    def test_the_day_cap_stops_a_patient_script(self):
        from data.repositories import avi_settings

        avi_settings.invalidate_cache()
        avi_settings.update_settings({"userPerHour": 0, "userPerDay": 2})
        caller = _caller(key="u_day")
        self.assertTrue(limits.check_and_count(caller)[0])
        self.assertTrue(limits.check_and_count(caller)[0])
        allowed, retry = limits.check_and_count(caller)
        self.assertFalse(allowed)
        self.assertGreater(retry, 0)
        self.assertLessEqual(retry, 86_401)

    def test_guests_and_users_have_separate_budgets(self):
        from data.repositories import avi_settings

        avi_settings.invalidate_cache()
        avi_settings.update_settings(
            {"guestPerHour": 1, "guestPerDay": 10, "userPerHour": 5, "userPerDay": 10}
        )
        guest = _caller(surface=SURFACE_GUEST, key="guest_abc")
        self.assertTrue(limits.check_and_count(guest)[0])
        self.assertFalse(limits.check_and_count(guest)[0])
        # The signed-in budget is untouched by the guest's consumption.
        self.assertTrue(limits.check_and_count(_caller(surface=SURFACE_USER, key="u_ok"))[0])

    def test_two_callers_do_not_share_a_budget(self):
        from data.repositories import avi_settings

        avi_settings.invalidate_cache()
        avi_settings.update_settings({"userPerHour": 1, "userPerDay": 10})
        self.assertTrue(limits.check_and_count(_caller(key="u_one"))[0])
        self.assertTrue(limits.check_and_count(_caller(key="u_two"))[0])
        self.assertFalse(limits.check_and_count(_caller(key="u_one"))[0])

    def test_a_zero_limit_means_no_cap(self):
        from data.repositories import avi_settings

        avi_settings.invalidate_cache()
        avi_settings.update_settings({"userPerHour": 0, "userPerDay": 0})
        caller = _caller(key="u_nolimit")
        for _ in range(5):
            self.assertTrue(limits.check_and_count(caller)[0])

    def test_evaluation_runs_are_exempt(self):
        from data.repositories import avi_settings

        avi_settings.invalidate_cache()
        avi_settings.update_settings({"userPerHour": 1, "userPerDay": 1})
        caller = _caller(surface=SURFACE_EVAL, key="u_eval")
        for _ in range(4):
            self.assertTrue(limits.check_and_count(caller)[0])

    def test_usage_reports_the_budget(self):
        from data.repositories import avi_settings

        avi_settings.invalidate_cache()
        avi_settings.update_settings({"userPerHour": 7, "userPerDay": 70})
        caller = _caller(key="u_usage")
        limits.check_and_count(caller)
        report = limits.usage(caller)
        self.assertEqual(report["hourLimit"], 7)
        self.assertEqual(report["hourUsed"], 1)
        self.assertEqual(report["scope"], SURFACE_USER)

    def test_limiter_fails_open_when_storage_is_unavailable(self):
        """A rate limiter outage must not take Avi down with it."""
        from data.repositories import avi_settings

        avi_settings.invalidate_cache()
        avi_settings.update_settings({"userPerHour": 1, "userPerDay": 1})
        caller = _caller(key="u_failopen")
        self.assertTrue(limits.check_and_count(caller)[0])
        # Break the table handle: core.ratelimit swallows the error and allows.
        from data import client as dynamo_client

        dynamo_client._table = None
        original = dynamo_client.table

        def boom():
            raise RuntimeError("dynamodb down")

        dynamo_client.table = boom  # type: ignore[assignment]
        try:
            self.assertTrue(limits.check_and_count(caller)[0])
        finally:
            dynamo_client.table = original  # type: ignore[assignment]


if __name__ == "__main__":
    unittest.main()

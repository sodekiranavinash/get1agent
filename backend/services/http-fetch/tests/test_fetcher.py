"""Unit tests for the SSRF guard (no network, no AWS).

Run with: ``make -C backend/services/http-fetch test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from src import fetcher  # noqa: E402


class BlockedAddressTests(unittest.TestCase):
    def test_blocks_private_and_internal_ranges(self) -> None:
        for ip in (
            "127.0.0.1",
            "10.0.0.5",
            "172.16.3.4",
            "192.168.1.10",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "::1",
            "fe80::1",
            "fc00::1",
            "::ffff:127.0.0.1",
        ):
            self.assertTrue(fetcher._blocked(ip), ip)

    def test_allows_public_addresses(self) -> None:
        for ip in ("8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"):
            self.assertFalse(fetcher._blocked(ip), ip)

    def test_blocks_garbage(self) -> None:
        self.assertTrue(fetcher._blocked("not-an-ip"))


class DomainAllowlistTests(unittest.TestCase):
    def test_empty_allowlist_permits_all(self) -> None:
        self.assertTrue(fetcher._domain_allowed("example.com", ()))

    def test_suffix_match(self) -> None:
        allowed = ("example.com", "api.test.io")
        self.assertTrue(fetcher._domain_allowed("example.com", allowed))
        self.assertTrue(fetcher._domain_allowed("a.b.example.com", allowed))
        self.assertFalse(fetcher._domain_allowed("notexample.com", allowed))
        self.assertFalse(fetcher._domain_allowed("evil.com", allowed))


class ValidateTests(unittest.TestCase):
    def test_rejects_non_http_scheme(self) -> None:
        with self.assertRaises(fetcher.FetchError) as ctx:
            fetcher._validate("ftp://example.com/file", ())
        self.assertEqual(ctx.exception.code, "invalid_url")

    def test_rejects_embedded_credentials(self) -> None:
        with self.assertRaises(fetcher.FetchError) as ctx:
            fetcher._validate("https://user:pass@example.com", ())
        self.assertEqual(ctx.exception.code, "invalid_url")

    def test_rejects_missing_host(self) -> None:
        with self.assertRaises(fetcher.FetchError) as ctx:
            fetcher._validate("https:///nohost", ())
        self.assertEqual(ctx.exception.code, "invalid_url")

    def test_rejects_disallowed_host_before_dns(self) -> None:
        with self.assertRaises(fetcher.FetchError) as ctx:
            fetcher._validate("https://evil.com", ("example.com",))
        self.assertEqual(ctx.exception.code, "blocked_target")


class FetchMethodTests(unittest.TestCase):
    def test_unsupported_method_rejected(self) -> None:
        with self.assertRaises(fetcher.FetchError) as ctx:
            fetcher.fetch("https://example.com", method="TRACE")
        self.assertEqual(ctx.exception.code, "invalid_request")


class HeaderTests(unittest.TestCase):
    def test_drops_hop_by_hop_headers_and_sets_user_agent(self) -> None:
        captured: dict[str, str] = {}

        def fake_open(target, method, headers, body, timeout, max_bytes):
            captured.update(headers)
            return 200, {"content-type": "text/plain"}, b"ok"

        with patch.object(fetcher, "_open_once", fake_open):
            fetcher.fetch(
                "https://8.8.8.8/",
                headers={
                    "Host": "evil.example",
                    "Content-Length": "9",
                    "Connection": "close",
                    "Authorization": "Bearer token",
                },
            )
        self.assertNotIn("Host", captured)
        self.assertNotIn("Content-Length", captured)
        self.assertNotIn("Connection", captured)
        self.assertEqual(captured.get("Authorization"), "Bearer token")
        self.assertEqual(captured.get("user-agent"), fetcher.DEFAULT_USER_AGENT)


if __name__ == "__main__":
    unittest.main()

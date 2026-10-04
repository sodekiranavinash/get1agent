"""Browser tool: domain allowlist is enforced (fails closed)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parents[1] / "packages"))

from core import browser  # noqa: E402
from src import service  # noqa: E402


class AllowlistTests(unittest.TestCase):
    def test_empty_allowlist_denies(self) -> None:
        with mock.patch.dict(os.environ, {"BROWSER_ALLOWED_DOMAINS": ""}, clear=False):
            allowed, _ = browser.allowed("https://example.com")
        self.assertFalse(allowed)

    def test_suffix_match(self) -> None:
        env = {"BROWSER_ALLOWED_DOMAINS": "example.com, docs.aws.amazon.com"}
        with mock.patch.dict(os.environ, env, clear=False):
            self.assertTrue(browser.allowed("https://example.com/x")[0])
            self.assertTrue(browser.allowed("https://sub.example.com")[0])
            self.assertTrue(browser.allowed("https://docs.aws.amazon.com/x")[0])
            self.assertFalse(browser.allowed("https://evil.com")[0])
            self.assertFalse(browser.allowed("https://example.com.evil.com")[0])

    def test_invalid_url_denied(self) -> None:
        with mock.patch.dict(os.environ, {"BROWSER_ALLOWED_DOMAINS": "example.com"}, clear=False):
            self.assertFalse(browser.allowed("not-a-url")[0])


class ToolTests(unittest.TestCase):
    def test_open_requires_config(self) -> None:
        with mock.patch.dict(os.environ, {"BROWSER_ID": ""}, clear=False):
            result = service.open_browser_session({"url": "https://example.com"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "not_configured")

    def test_open_blocks_unlisted_domain(self) -> None:
        env = {"BROWSER_ID": "b-1", "BROWSER_ALLOWED_DOMAINS": "example.com"}
        with mock.patch.dict(os.environ, env, clear=False):
            result = service.open_browser_session({"url": "https://evil.com"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "domain_not_allowed")

    def test_open_returns_session(self) -> None:
        env = {"BROWSER_ID": "b-1", "BROWSER_ALLOWED_DOMAINS": "example.com"}
        session = {"sessionId": "s-1", "browserId": "b-1", "liveViewUrl": "u", "wsHeaders": {}}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(
            browser, "start_session", lambda: session
        ):
            result = service.open_browser_session({"url": "https://example.com/a"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["sessionId"], "s-1")


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the public MCP catalog.

Run with: ``make -C backend/services/mcp/mcp-connections test``
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from src import catalog  # noqa: E402


class CatalogTests(unittest.TestCase):
    def test_github_entry_present(self) -> None:
        entry = catalog.get_entry("github")
        self.assertIsNotNone(entry)
        self.assertEqual(entry["serverUrl"], "https://api.githubcopilot.com/mcp/")

    def test_public_entries_hide_env_names(self) -> None:
        for entry in catalog.public_entries():
            self.assertNotIn("clientIdEnv", entry)
            self.assertNotIn("clientSecretEnv", entry)
            self.assertIn("serverUrl", entry)
            self.assertEqual(entry["source"], "public")

    def test_oauth_override_maps_endpoints(self) -> None:
        override = catalog.oauth_override(catalog.get_entry("github"))
        self.assertEqual(
            override["authorization_endpoint"], "https://github.com/login/oauth/authorize"
        )
        self.assertEqual(override["token_endpoint"], "https://github.com/login/oauth/access_token")
        self.assertIn("repo", override["scopes"])

    def test_client_credentials_from_env(self) -> None:
        os.environ["MCP_GITHUB_CLIENT_ID"] = "abc"
        os.environ["MCP_GITHUB_CLIENT_SECRET"] = "shh"
        try:
            client_id, client_secret = catalog.client_credentials(catalog.get_entry("github"))
        finally:
            os.environ.pop("MCP_GITHUB_CLIENT_ID", None)
            os.environ.pop("MCP_GITHUB_CLIENT_SECRET", None)
        self.assertEqual((client_id, client_secret), ("abc", "shh"))

    def test_client_credentials_absent(self) -> None:
        os.environ.pop("MCP_GITHUB_CLIENT_ID", None)
        os.environ.pop("MCP_GITHUB_CLIENT_SECRET", None)
        self.assertEqual(catalog.client_credentials(catalog.get_entry("github")), (None, None))

    def test_identity_config_declared(self) -> None:
        config = catalog.identity_config(catalog.get_entry("github"))
        self.assertEqual(config["endpoint"], "https://api.github.com/user")
        self.assertEqual(config["login"], "login")
        self.assertEqual(config["avatar"], "avatar_url")

    def test_identity_config_absent(self) -> None:
        self.assertEqual(catalog.identity_config(None), {})
        self.assertEqual(catalog.identity_config({"id": "svc"}), {})


if __name__ == "__main__":
    unittest.main()

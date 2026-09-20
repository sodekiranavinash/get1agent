"""Unit tests for the official MCP registry proxy.

Run with: ``make -C backend/services/mcp-connections test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from src import registry  # noqa: E402


class RegistryMapTests(unittest.TestCase):
    def test_maps_streamable_http_remote(self) -> None:
        mapped = registry._map_server(
            {
                "name": "ac.foo/bar",
                "title": "Foo",
                "description": "Does foo.",
                "remotes": [{"type": "streamable-http", "url": "https://x.dev/mcp"}],
            }
        )
        self.assertIsNotNone(mapped)
        self.assertEqual(mapped["serverUrl"], "https://x.dev/mcp")
        self.assertEqual(mapped["name"], "Foo")
        self.assertEqual(mapped["source"], "public")

    def test_skips_stdio_only(self) -> None:
        self.assertIsNone(
            registry._map_server(
                {"name": "x", "packages": [{"transport": {"type": "stdio"}}]}
            )
        )

    def test_skips_required_header(self) -> None:
        self.assertIsNone(
            registry._map_server(
                {
                    "name": "x",
                    "remotes": [
                        {
                            "type": "streamable-http",
                            "url": "https://x.dev/mcp",
                            "headers": [
                                {"name": "Authorization", "isRequired": True, "isSecret": True}
                            ],
                        }
                    ],
                }
            )
        )

    def test_prefers_headerless_remote(self) -> None:
        mapped = registry._map_server(
            {
                "name": "x",
                "remotes": [
                    {
                        "type": "streamable-http",
                        "url": "https://a.dev/mcp",
                        "headers": [{"name": "Authorization", "isRequired": True}],
                    },
                    {"type": "streamable-http", "url": "https://b.dev/mcp"},
                ],
            }
        )
        self.assertIsNotNone(mapped)
        self.assertEqual(mapped["serverUrl"], "https://b.dev/mcp")

    def test_category_from_publisher(self) -> None:
        mapped = registry._map_server(
            {
                "name": "x",
                "remotes": [{"type": "streamable-http", "url": "https://x.dev/mcp"}],
                "_meta": {
                    "io.modelcontextprotocol.registry/publisher-provided": {
                        "categories": ["devtools"]
                    }
                },
            }
        )
        self.assertIsNotNone(mapped)
        self.assertEqual(mapped["category"], "devtools")

    def test_filter_by_auth_keeps_matches(self) -> None:
        servers = [
            {"serverUrl": "https://a.dev/mcp"},
            {"serverUrl": "https://b.dev/mcp"},
            {"serverUrl": "https://c.dev/mcp"},
        ]
        probe = {
            "https://a.dev/mcp": "oauth",
            "https://b.dev/mcp": "none",
            "https://c.dev/mcp": "oauth",
        }
        original = registry._probe_auth
        registry._probe_auth = lambda url: probe[url]
        try:
            kept = registry._filter_by_auth(servers, "oauth")
        finally:
            registry._probe_auth = original
        self.assertEqual(
            [server["serverUrl"] for server in kept],
            ["https://a.dev/mcp", "https://c.dev/mcp"],
        )
        self.assertTrue(all(server["auth"] == "oauth" for server in kept))


if __name__ == "__main__":
    unittest.main()

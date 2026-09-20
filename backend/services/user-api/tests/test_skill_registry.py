"""Unit tests for the skills registry / importer helpers.

Run with: ``make -C backend/services/user-api test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from src.skills import classify  # noqa: E402
from src.skills import fetch  # noqa: E402
from src.skills import registry  # noqa: E402
from src.skills import repo_resolver  # noqa: E402


class ClassifyTests(unittest.TestCase):
    def test_prompt_only(self) -> None:
        result = classify.classify_skill("# Style guide\n\nWrite clearly and concisely.")
        self.assertEqual(result["kind"], "prompt")
        self.assertEqual(result["suggestedServers"], [])

    def test_code_is_tool_based(self) -> None:
        result = classify.classify_skill("```python\nprint('hi')\n```")
        self.assertEqual(result["kind"], "tool")
        self.assertIn("code-interpreter", result["suggestedServers"])

    def test_web_is_tool_based(self) -> None:
        result = classify.classify_skill("Use web search to find the latest news.")
        self.assertEqual(result["kind"], "tool")
        self.assertIn("web-search", result["suggestedServers"])

    def test_referenced_files(self) -> None:
        refs = classify.referenced_files(
            "See [details](references/details.md) and [site](https://example.com)."
        )
        self.assertEqual(refs, ["references/details.md"])


class FetchGuardTests(unittest.TestCase):
    def test_rejects_non_https(self) -> None:
        with self.assertRaises(fetch.FetchError):
            fetch.fetch_text("http://raw.githubusercontent.com/x/y")

    def test_rejects_unlisted_host(self) -> None:
        with self.assertRaises(fetch.FetchError):
            fetch.fetch_text("https://evil.example.com/SKILL.md")


class RegistryMapTests(unittest.TestCase):
    def test_maps_item(self) -> None:
        mapped = registry._map(
            {
                "id": "1",
                "name": "pdf",
                "namespace": "@anthropics/skills/pdf",
                "description": "PDF toolkit",
                "author": "anthropics",
                "stars": 10,
                "installs": 2,
                "sourceUrl": "https://github.com/anthropics/skills",
                "metadata": {"rawFileUrl": "https://raw.githubusercontent.com/x/SKILL.md"},
            }
        )
        self.assertIsNotNone(mapped)
        self.assertEqual(mapped["name"], "pdf")
        self.assertEqual(mapped["rawUrl"], "https://raw.githubusercontent.com/x/SKILL.md")

    def test_skips_without_raw_url(self) -> None:
        self.assertIsNone(registry._map({"name": "x", "metadata": {}}))


class RepoParseTests(unittest.TestCase):
    def test_shorthand(self) -> None:
        self.assertEqual(
            repo_resolver.parse_repo("anthropics/skills"),
            ("anthropics", "skills", None, None),
        )

    def test_url_with_tree(self) -> None:
        self.assertEqual(
            repo_resolver.parse_repo(
                "https://github.com/anthropics/skills/tree/main/skills/pdf"
            ),
            ("anthropics", "skills", "main", "skills/pdf"),
        )

    def test_invalid(self) -> None:
        with self.assertRaises(repo_resolver.RepoError):
            repo_resolver.parse_repo("not a repo")


if __name__ == "__main__":
    unittest.main()

"""Every citation AI Assistant offers must be a link that lands somewhere.

Two failures shipped from the same root: the deep-link check stripped the
`#fragment` before validating, so `/docs#anything` passed. That let AI Assistant cite
per-question anchors the Documentation page never renders
(`/docs#troubleshooting-a-custom-tool-times-out-or-errors-check--4`) — a link that
did nothing when clicked — and it meant a *stale* index could keep producing dead
links after the corpus had been fixed.

The anchors the page renders are published in the generated `features.json`, so
the check is exact and a bad route is refused (the caller then falls back to
`/docs`, which works). This is the test for that guard, and for the rule that a
live app page and a documentation section can never be confused.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
for extra in (REPO_ROOT / "backend" / "ai-assistant", REPO_ROOT / "backend" / "packages"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from src import deep_links  # noqa: E402

FEATURES = REPO_ROOT / "backend" / "ai-assistant" / "src" / "features.json"


class CatalogueContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalogue = json.loads(FEATURES.read_text(encoding="utf-8"))
        deep_links.refresh()

    def test_the_catalogue_publishes_the_docs_anchors(self) -> None:
        """Without this list the check cannot be exact."""
        anchors = self.catalogue.get("docAnchors")
        self.assertIsInstance(anchors, list)
        self.assertIn("faq", anchors)
        self.assertIn("troubleshooting", anchors)

    def test_a_real_page_is_valid(self) -> None:
        for path in ("/agent-builder", "/knowledge-bases", "/tools", "/docs"):
            self.assertTrue(deep_links.is_valid(path), path)

    def test_a_real_docs_anchor_is_valid(self) -> None:
        for path in ("/docs#faq", "/docs#troubleshooting", "/docs#concepts"):
            self.assertTrue(deep_links.is_valid(path), path)

    def test_a_per_question_anchor_is_refused(self) -> None:
        """The exact shape that shipped broken: a FAQ/troubleshooting spin-off id."""
        dead = "/docs#troubleshooting-a-custom-tool-times-out-or-errors-check--4"
        self.assertFalse(deep_links.is_valid(dead))

    def test_an_unknown_anchor_is_refused(self) -> None:
        self.assertFalse(deep_links.is_valid("/docs#not-a-section"))

    def test_an_unknown_page_is_refused(self) -> None:
        self.assertFalse(deep_links.is_valid("/not-a-page"))

    def test_admin_routes_stay_refused_for_a_non_admin(self) -> None:
        self.assertFalse(deep_links.is_valid("/admin/users", allow_admin=False))

    def test_normalize_blanks_a_dead_link(self) -> None:
        """What the agent does with a refused route: fall back, never emit it."""
        self.assertEqual(deep_links.normalize("/docs#nope"), "")
        self.assertEqual(deep_links.normalize("/agent-builder"), "/agent-builder")


class CorpusLinkTest(unittest.TestCase):
    """The committed corpus, checked through the same gate the runtime uses."""

    def test_every_document_route_is_openable(self) -> None:
        documents = sorted((REPO_ROOT / "backend" / "ai-assistant" / "knowledge").glob("*.md"))
        self.assertTrue(documents, "the committed corpus is missing")
        for path in documents:
            match = re.search(r'^route: "([^"]+)"', path.read_text(encoding="utf-8"), re.M)
            self.assertIsNotNone(match, f"{path.name} has no route")
            route = match.group(1)
            self.assertTrue(
                deep_links.is_valid(route),
                f"{path.name} links to {route}, which is not openable",
            )


if __name__ == "__main__":
    unittest.main()

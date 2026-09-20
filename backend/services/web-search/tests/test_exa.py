"""Unit tests for the Exa request builder and response shaper.

Run with: ``make -C backend/services/web-search test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from src import exa  # noqa: E402


class BuildBodyTests(unittest.TestCase):
    def test_requires_query(self) -> None:
        with self.assertRaises(exa.ExaError):
            exa.build_body({})

    def test_defaults_highlights_only_and_five_results(self) -> None:
        body, warnings = exa.build_body({"query": "latest in llms"})
        self.assertEqual(body["type"], "auto")
        self.assertEqual(body["numResults"], 5)
        self.assertEqual(
            body["contents"],
            {
                "highlights": {"maxCharacters": 400},
                "maxAgeHours": 24,
            },
        )
        self.assertEqual(warnings, [])

    def test_max_age_hours_can_be_overridden(self) -> None:
        body, _ = exa.build_body({"query": "x", "maxAgeHours": 0})
        self.assertEqual(body["contents"]["maxAgeHours"], 0)

    def test_unknown_type_falls_back_to_auto(self) -> None:
        body, _ = exa.build_body({"query": "x", "type": "bogus"})
        self.assertEqual(body["type"], "auto")

    def test_supported_types_are_preserved(self) -> None:
        for search_type in ("instant", "fast", "auto", "deep-lite", "deep"):
            body, _ = exa.build_body({"query": "x", "type": search_type})
            self.assertEqual(body["type"], search_type)

    def test_num_results_can_be_raised_up_to_the_cap(self) -> None:
        body, _ = exa.build_body({"query": "x", "numResults": 25}, max_results=25)
        self.assertEqual(body["numResults"], 25)

    def test_num_results_is_clamped_to_the_cap(self) -> None:
        body, _ = exa.build_body({"query": "x", "numResults": 500}, max_results=25)
        self.assertEqual(body["numResults"], 25)
        body, _ = exa.build_body({"query": "x", "numResults": 0}, max_results=25)
        self.assertEqual(body["numResults"], 1)

    def test_text_and_summary_are_opt_in(self) -> None:
        body, _ = exa.build_body(
            {"query": "x", "text": True, "textMaxCharacters": 2000, "summary": True}
        )
        self.assertEqual(body["contents"]["text"], {"maxCharacters": 2000})
        self.assertEqual(body["contents"]["summary"], True)
        self.assertNotIn("highlights", body["contents"])

    def test_highlights_can_be_disabled(self) -> None:
        body, _ = exa.build_body({"query": "x", "highlights": False, "text": True})
        self.assertNotIn("highlights", body["contents"])
        self.assertEqual(body["contents"]["text"], True)

    def test_filters_and_dates(self) -> None:
        body, warnings = exa.build_body(
            {
                "query": "x",
                "category": "publication",
                "includeDomains": ["arxiv.org"],
                "excludeDomains": ["example.com"],
                "startPublishedDate": "2026-01-01",
                "endPublishedDate": "2026-06-01",
                "includeText": ["transformer"],
                "userLocation": "US",
                "moderation": True,
                "additionalQueries": ["a", "b"],
                "systemPrompt": "prefer official sources",
                "subpages": 3,
                "subpageTarget": ["sources"],
                "maxAgeHours": 24,
            }
        )
        self.assertEqual(body["category"], "publication")
        self.assertEqual(body["includeDomains"], ["arxiv.org"])
        self.assertEqual(body["excludeDomains"], ["example.com"])
        self.assertEqual(body["startPublishedDate"], "2026-01-01")
        self.assertEqual(body["includeText"], ["transformer"])
        self.assertEqual(body["userLocation"], "US")
        self.assertIs(body["moderation"], True)
        self.assertEqual(body["additionalQueries"], ["a", "b"])
        self.assertEqual(body["systemPrompt"], "prefer official sources")
        self.assertEqual(body["contents"]["subpages"], 3)
        self.assertEqual(body["contents"]["subpageTarget"], ["sources"])
        self.assertEqual(body["contents"]["maxAgeHours"], 24)
        self.assertEqual(warnings, [])

    def test_restricted_filters_dropped_for_company(self) -> None:
        body, warnings = exa.build_body(
            {
                "query": "x",
                "category": "company",
                "excludeDomains": ["example.com"],
                "startPublishedDate": "2026-01-01",
            }
        )
        self.assertNotIn("excludeDomains", body)
        self.assertNotIn("startPublishedDate", body)
        self.assertEqual(len(warnings), 2)


class ShapeResultsTests(unittest.TestCase):
    def test_projects_only_known_fields(self) -> None:
        shaped = exa.shape_results(
            {
                "results": [
                    {
                        "title": "T",
                        "url": "https://example.com",
                        "highlights": ["h"],
                        "score": 0.9,
                    }
                ]
            }
        )
        self.assertEqual(shaped[0]["title"], "T")
        self.assertEqual(shaped[0]["highlights"], ["h"])
        self.assertNotIn("score", shaped[0])


if __name__ == "__main__":
    unittest.main()

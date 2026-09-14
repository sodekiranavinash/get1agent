"""Unit tests for the web-search service (Exa call is mocked).

Run with: ``make -C backend/tools/web-search test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import exa  # noqa: E402
import service  # noqa: E402

_ENV = {"EXA_API_KEY": "test-key", "WEB_SEARCH_MAX_RESULTS": "25"}

_RESPONSE = {
    "requestId": "req-1",
    "results": [
        {
            "title": "Result",
            "url": "https://example.com",
            "publishedDate": "2026-01-01T00:00:00Z",
            "highlights": ["relevant excerpt"],
        }
    ],
    "costDollars": {"total": 0.007},
    "searchTime": 120.5,
}


class ServiceTests(unittest.TestCase):
    def test_missing_api_key_is_not_configured(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            result = service.search({"auth0Sub": "u", "query": "x"})
        self.assertEqual(result["error"]["code"], "not_configured")

    def test_missing_query_is_invalid_request(self) -> None:
        with mock.patch.dict("os.environ", _ENV, clear=True):
            result = service.search({"auth0Sub": "u"})
        self.assertEqual(result["error"]["code"], "invalid_request")

    def test_shapes_successful_search(self) -> None:
        with mock.patch.dict("os.environ", _ENV, clear=True), mock.patch.object(
            service.exa, "search", return_value=_RESPONSE
        ) as search:
            result = service.search({"auth0Sub": "u", "query": "latest in llms", "numResults": 25})

        body = search.call_args.args[0]
        self.assertEqual(body["numResults"], 25)
        self.assertEqual(result["error"], None)
        self.assertEqual(result["meta"]["requestId"], "req-1")
        self.assertEqual(result["meta"]["resultCount"], 1)
        self.assertEqual(result["results"][0]["highlights"], ["relevant excerpt"])

    def test_exa_error_is_surfaced(self) -> None:
        error = exa.ExaError("Invalid API key", status=401, tag="INVALID_API_KEY")
        with mock.patch.dict("os.environ", _ENV, clear=True), mock.patch.object(
            service.exa, "search", side_effect=error
        ):
            result = service.search({"auth0Sub": "u", "query": "x"})

        self.assertEqual(result["error"]["code"], "search_failed")
        self.assertEqual(result["error"]["status"], 401)
        self.assertEqual(result["error"]["tag"], "INVALID_API_KEY")


if __name__ == "__main__":
    unittest.main()

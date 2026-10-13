"""The Bedrock Rerank request must match the API, and a mismatch is invisible.

This is the regression test for a bug that silently disabled reranking everywhere:
the reranker sent ``type: "INLINE_DOCUMENT"`` — the obvious-looking name — while the
API's enum is ``"INLINE"``. Every call failed validation, and because the reranker
is required to degrade rather than fail, the only symptom was that results came back
in RRF order forever. `applied=False` on every search, no error surfaced, and a
plausible-looking ranking that was simply not reranked.

So the request shape is asserted literally, and the fallback is asserted separately:
one test proves we send what AWS accepts, the other proves a rejection stays
invisible to the caller (which is what made this hard to notice).
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parent / "packages"
for extra in (str(SERVICE_ROOT), str(PACKAGES)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from retrieval import rerank  # noqa: E402


class _FakeBedrock:
    """Records the rerank call and returns a chosen order."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls: list[dict] = []
        self._error = error

    def rerank(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        count = len(kwargs["sources"])
        return {
            "results": [
                {"index": index, "relevanceScore": 1.0 - 0.1 * index}
                for index in range(count)
            ]
        }


class _FakeBoto3:
    def __init__(self, client) -> None:
        self._client = client
        self.service = ""

    def client(self, service, **kwargs):
        self.service = service
        return self._client


class BedrockRequestShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.get("RERANK_MODE")
        os.environ["RERANK_MODE"] = "bedrock"
        self.client = _FakeBedrock()
        self._real_import = rerank._rerank_bedrock.__globals__.get("boto3")
        # `_rerank_bedrock` imports boto3 inside the function, so patch the module
        # the import resolves to.
        import boto3  # noqa: PLC0415

        self._real_client = boto3.client
        boto3.client = lambda service, **kwargs: self.client  # type: ignore[assignment]

    def tearDown(self) -> None:
        import boto3  # noqa: PLC0415

        boto3.client = self._real_client  # type: ignore[assignment]
        if self._env is None:
            os.environ.pop("RERANK_MODE", None)
        else:
            os.environ["RERANK_MODE"] = self._env

    def test_the_source_type_is_the_enum_the_api_accepts(self) -> None:
        """`INLINE`, not `INLINE_DOCUMENT` — the whole bug in one assertion."""
        rerank.rerank_candidates(
            "q", [{"content": "a"}, {"content": "b"}], 2, region="us-west-2"
        )
        sources = self.client.calls[0]["sources"]
        self.assertEqual([source["type"] for source in sources], ["INLINE", "INLINE"])

    def test_each_source_carries_an_inline_text_document(self) -> None:
        rerank.rerank_candidates("q", [{"content": "hello"}], 1, region="us-west-2")
        source = self.client.calls[0]["sources"][0]
        self.assertEqual(source["inlineDocumentSource"]["type"], "TEXT")
        self.assertEqual(
            source["inlineDocumentSource"]["textDocument"]["text"], "hello"
        )

    def test_the_configuration_names_the_reranking_model(self) -> None:
        rerank.rerank_candidates("q", [{"content": "a"}], 1, region="us-west-2")
        config = self.client.calls[0]["rerankingConfiguration"]
        self.assertEqual(config["type"], "BEDROCK_RERANKING_MODEL")
        self.assertIn("modelArn", config["bedrockRerankingConfiguration"]["modelConfiguration"])

    def test_number_of_results_never_exceeds_the_sources(self) -> None:
        """Asking for more results than documents is a validation error."""
        rerank.rerank_candidates("q", [{"content": "a"}], 5, region="us-west-2")
        asked = self.client.calls[0]["rerankingConfiguration"]["bedrockRerankingConfiguration"]["numberOfResults"]
        self.assertEqual(asked, 1)

    def test_the_score_is_read_back_onto_the_candidate(self) -> None:
        ranked, applied = rerank.rerank_candidates(
            "q", [{"content": "a"}, {"content": "b"}], 2, region="us-west-2"
        )
        self.assertTrue(applied)
        self.assertIsNotNone(ranked[0]["rerankScore"])

    def test_a_rejected_request_degrades_to_the_input_order(self) -> None:
        """The property that hid the bug: a failure must look like 'not applied'."""
        self.client = _FakeBedrock(error=RuntimeError("validation failed"))
        import boto3  # noqa: PLC0415

        boto3.client = lambda service, **kwargs: self.client  # type: ignore[assignment]
        candidates = [{"content": "a"}, {"content": "b"}]
        ranked, applied = rerank.rerank_candidates("q", candidates, 2, region="us-west-2")
        self.assertFalse(applied)
        self.assertEqual([c["content"] for c in ranked], ["a", "b"])


class RerankModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.get("RERANK_MODE")

    def tearDown(self) -> None:
        if self._env is None:
            os.environ.pop("RERANK_MODE", None)
        else:
            os.environ["RERANK_MODE"] = self._env

    def test_bedrock_is_the_default(self) -> None:
        os.environ.pop("RERANK_MODE", None)
        self.assertEqual(rerank.rerank_mode(), "bedrock")

    def test_none_skips_reranking(self) -> None:
        os.environ["RERANK_MODE"] = "none"
        candidates = [{"content": "a"}]
        ranked, applied = rerank.rerank_candidates("q", candidates, 1)
        self.assertFalse(applied)
        self.assertEqual(ranked, candidates)

    def test_no_candidates_is_not_an_error(self) -> None:
        ranked, applied = rerank.rerank_candidates("q", [], 3)
        self.assertEqual(ranked, [])
        self.assertFalse(applied)


if __name__ == "__main__":
    unittest.main()

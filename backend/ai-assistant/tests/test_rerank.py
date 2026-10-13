"""Reranking must reorder a search and never break one.

RRF fuses two ranked lists by *agreement*, so its top entry is frequently not the
passage that answers the question — which is why the reranker exists. But it is also
a cross-region network call to a model that can be throttled or down, on the critical
path of every answer. So two properties are pinned here:

* when the reranker works, its ordering is what the answer is built from;
* when it does not, the search returns the RRF order and still returns *something*.
  A reranker outage must degrade ranking, never availability.

Plus the plumbing that is easy to get subtly wrong: `rerankScore` recorded on the
passage, indices renumbered after reordering (the citation `[n]` badges depend on
them), and the cache key separating a reranked search from an unreranked one.

No AWS, no network: `retrieval.rerank_candidates` is replaced with a recorder.
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

from src import retrieval  # noqa: E402


def _passage(title: str, content: str = "", score: float = 0.1) -> retrieval.Passage:
    return retrieval.Passage(
        index=0,
        title=title,
        route=f"/docs#{title.lower()}",
        content=content or f"body of {title}",
        matched=content or f"body of {title}",
        snippet=content or f"body of {title}",
        score=score,
    )


class RerankPassagesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.get("AI_ASSISTANT_RERANK")
        os.environ.pop("AI_ASSISTANT_RERANK", None)
        self.calls: list[dict] = []
        self._real = retrieval.rerank_candidates

    def tearDown(self) -> None:
        retrieval.rerank_candidates = self._real
        if self._env is None:
            os.environ.pop("AI_ASSISTANT_RERANK", None)
        else:
            os.environ["AI_ASSISTANT_RERANK"] = self._env

    def _stub(self, ranked_titles: list[str] | None, applied: bool = True) -> None:
        """Replace the reranker with one that returns a chosen order."""

        def fake(query, candidates, top_k, **kwargs):
            self.calls.append({"query": query, "candidates": candidates, "top_k": top_k})
            if not applied:
                return candidates[:top_k], False
            chosen = []
            for title in ranked_titles or []:
                for candidate in candidates:
                    if candidate["passage"].title == title:
                        candidate = dict(candidate)
                        candidate["rerankScore"] = 1.0 - 0.1 * len(chosen)
                        chosen.append(candidate)
                        break
            return chosen[:top_k], True

        retrieval.rerank_candidates = fake

    def test_the_reranker_order_is_what_is_returned(self) -> None:
        self._stub(["third", "first", "second"])
        passages, applied = retrieval.rerank_passages(
            "q", [_passage("first"), _passage("second"), _passage("third")], 3
        )
        self.assertTrue(applied)
        self.assertEqual([p.title for p in passages], ["third", "first", "second"])

    def test_indices_are_renumbered_after_reordering(self) -> None:
        """The `[n]` citation badges are keyed off `index`, so it must track order."""
        self._stub(["c", "a", "b"])
        passages, _ = retrieval.rerank_passages(
            "q", [_passage("a"), _passage("b"), _passage("c")], 3
        )
        self.assertEqual([p.index for p in passages], [1, 2, 3])
        self.assertEqual([p.title for p in passages], ["c", "a", "b"])

    def test_the_rerank_score_is_recorded(self) -> None:
        self._stub(["b", "a"])
        passages, _ = retrieval.rerank_passages("q", [_passage("a"), _passage("b")], 2)
        self.assertIsNotNone(passages[0].rerank_score)
        self.assertGreater(passages[0].rerank_score, passages[1].rerank_score)
        self.assertIn("rerankScore", passages[0].to_dict())

    def test_top_k_truncates_after_reordering(self) -> None:
        self._stub(["c", "b", "a"])
        passages, _ = retrieval.rerank_passages(
            "q", [_passage("a"), _passage("b"), _passage("c")], 2
        )
        self.assertEqual([p.title for p in passages], ["c", "b"])

    def test_an_unavailable_reranker_preserves_the_rrf_order(self) -> None:
        """The critical property: an outage degrades ranking, not availability."""
        original = [_passage("a"), _passage("b"), _passage("c")]
        self._stub(None, applied=False)
        passages, applied = retrieval.rerank_passages("q", list(original), 3)
        self.assertFalse(applied)
        self.assertEqual([p.title for p in passages], ["a", "b", "c"])
        self.assertTrue(all(p.rerank_score is None for p in passages))

    def test_a_successful_but_empty_rerank_falls_back(self) -> None:
        """`applied=True` with nothing usable must not return an empty answer."""
        self._stub([])
        passages, applied = retrieval.rerank_passages(
            "q", [_passage("a"), _passage("b")], 2
        )
        self.assertFalse(applied)
        self.assertEqual([p.title for p in passages], ["a", "b"])

    def test_no_passages_never_calls_the_reranker(self) -> None:
        self._stub(["a"])
        passages, applied = retrieval.rerank_passages("q", [], 3)
        self.assertEqual(passages, [])
        self.assertFalse(applied)
        self.assertEqual(self.calls, [])

    def test_the_switch_disables_reranking_entirely(self) -> None:
        os.environ["AI_ASSISTANT_RERANK"] = "0"
        self._stub(["c", "b", "a"])
        self.assertFalse(retrieval.rerank_enabled())
        passages, applied = retrieval.rerank_passages(
            "q", [_passage("a"), _passage("b"), _passage("c")], 3
        )
        self.assertFalse(applied)
        self.assertEqual([p.title for p in passages], ["a", "b", "c"])
        self.assertEqual(self.calls, [], "a disabled reranker must not be called")

    def test_the_reranker_sees_the_parent_content(self) -> None:
        """It scores `(query, passage.content)`, not the child snippet."""
        self._stub(["a"])
        retrieval.rerank_passages("my question", [_passage("a", content="full page")], 1)
        candidate = self.calls[0]["candidates"][0]
        self.assertEqual(candidate["content"], "full page")
        self.assertEqual(self.calls[0]["query"], "my question")


class RerankSwitchTests(unittest.TestCase):
    def setUp(self) -> None:
        self._env = os.environ.get("AI_ASSISTANT_RERANK")

    def tearDown(self) -> None:
        if self._env is None:
            os.environ.pop("AI_ASSISTANT_RERANK", None)
        else:
            os.environ["AI_ASSISTANT_RERANK"] = self._env

    def test_reranking_is_on_by_default(self) -> None:
        os.environ.pop("AI_ASSISTANT_RERANK", None)
        self.assertTrue(retrieval.rerank_enabled())

    def test_common_off_spellings_all_disable_it(self) -> None:
        for value in ("0", "false", "FALSE", "no", "off", " off "):
            with self.subTest(value=value):
                os.environ["AI_ASSISTANT_RERANK"] = value
                self.assertFalse(retrieval.rerank_enabled())

    def test_other_values_leave_it_on(self) -> None:
        for value in ("1", "true", "yes", "on", ""):
            with self.subTest(value=value):
                os.environ["AI_ASSISTANT_RERANK"] = value
                self.assertTrue(retrieval.rerank_enabled())


class CacheKeyTests(unittest.TestCase):
    """Reranked and unreranked orderings must never be served from each other's cache."""

    def test_the_rerank_flag_is_part_of_the_key(self) -> None:
        self.assertNotEqual(
            retrieval._cache_key("q", 6, "user", rerank=True),
            retrieval._cache_key("q", 6, "user", rerank=False),
        )

    def test_the_audience_is_still_part_of_the_key(self) -> None:
        self.assertNotEqual(
            retrieval._cache_key("q", 6, "user"), retrieval._cache_key("q", 6, "admin")
        )

    def test_the_same_inputs_produce_the_same_key(self) -> None:
        self.assertEqual(
            retrieval._cache_key("q", 6, "user", rerank=True),
            retrieval._cache_key("q", 6, "user", rerank=True),
        )


if __name__ == "__main__":
    unittest.main()


class SearchPipelineTests(unittest.TestCase):
    """`search()` end to end: two legs → RRF → rerank → passages.

    This is the wiring test. `rerank_passages` is unit-tested above, but the bug
    that matters is the one where it is never *called*, or called on the wrong list
    (e.g. before hydration, when the passages have no `content` to score). So the
    legs, the vector store, the embedder and the parent reads are all stubbed and
    the ordering that comes out of `search` is asserted directly.

    No AWS, no S3, no network.
    """

    def setUp(self) -> None:
        os.environ.pop("AI_ASSISTANT_RERANK", None)
        self._patched: list[tuple[object, str, object]] = []

        # Three candidates, inserted so that RRF order and rerank order differ.
        self.rrf_order = ["alpha", "beta", "gamma"]
        self.rerank_order = ["gamma", "alpha", "beta"]

        self._patch(retrieval.cache, "get", lambda key: None)
        self._patch(retrieval.cache, "set", lambda *a, **k: None)
        self._patch(retrieval, "embed_texts", lambda texts, config: [[0.1, 0.2, 0.3]])
        self._patch(retrieval, "load_config", lambda: None)
        self._patch(retrieval, "vector_store", lambda storage: _FakeStore(self.rrf_order))
        self._patch(retrieval, "_lexical_leg", lambda *a, **k: [])
        self._patch(retrieval, "_load_parent", self._fake_parent)
        self._patch(retrieval, "Storage", lambda: object())
        # The reranker itself is stubbed: this class is about the *wiring*, and a real
        # Bedrock call here would make the resulting order depend on a model's
        # judgement (and on the network). `test_rerank_bedrock.py` covers the real
        # request contract.
        self._patch(retrieval, "rerank_candidates", self._fake_rerank)

    def _fake_rerank(self, query, candidates, top_k, **kwargs):
        """Return the candidates in a deliberately different order from the input."""
        chosen = []
        for position, title in enumerate(self.rerank_order):
            matched = next(
                (c for c in candidates if c["passage"].title == title), None
            )
            if matched is None:
                continue
            item = dict(matched)
            item["rerankScore"] = 1.0 - 0.1 * position
            chosen.append(item)
        return chosen[:top_k], True

    def tearDown(self) -> None:
        for target, name, original in reversed(self._patched):
            setattr(target, name, original)

    def _patch(self, target: object, name: str, value: object) -> None:
        self._patched.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    @staticmethod
    def _fake_parent(storage, scope, parent_id: str) -> dict:
        return {
            "content": f"body of {parent_id}",
            "route": f"/docs#{parent_id}",
            "title": parent_id,
            "children": [{"chunkId": f"{parent_id}#0", "text": f"body of {parent_id}"}],
        }

    def test_search_returns_the_reranked_order(self) -> None:
        """The answer is built from this order, and the citations are numbered by it."""
        passages, diagnostic = retrieval.search("q", top_k=3, use_cache=False)
        self.assertEqual([p.title for p in passages], self.rerank_order)
        self.assertTrue(diagnostic["rerank"]["requested"])
        self.assertTrue(diagnostic["rerank"]["applied"])
        self.assertEqual([p.index for p in passages], [1, 2, 3])

    def test_the_diagnostic_records_how_much_recall_reached_the_reranker(self) -> None:
        _, diagnostic = retrieval.search("q", top_k=3, use_cache=False)
        self.assertGreaterEqual(diagnostic["hydrated"], 3)

    def test_the_rerank_score_lands_on_the_passage(self) -> None:
        passages, _ = retrieval.search("q", top_k=3, use_cache=False)
        self.assertTrue(all(p.rerank_score is not None for p in passages))

    def test_turning_reranking_off_yields_the_rrf_order(self) -> None:
        os.environ["AI_ASSISTANT_RERANK"] = "0"
        passages, diagnostic = retrieval.search("q", top_k=3, use_cache=False)
        self.assertEqual([p.title for p in passages], self.rrf_order)
        self.assertFalse(diagnostic["rerank"]["requested"])
        self.assertFalse(diagnostic["rerank"]["applied"])

    def test_a_failing_reranker_still_returns_passages(self) -> None:
        """The availability property, at the level that actually matters."""
        self._patch(
            retrieval,
            "rerank_candidates",
            lambda query, candidates, top_k, **k: (candidates[:top_k], False),
        )
        passages, diagnostic = retrieval.search("q", top_k=3, use_cache=False)
        self.assertEqual([p.title for p in passages], self.rrf_order)
        self.assertFalse(diagnostic["rerank"]["applied"])

    def test_top_k_is_respected_after_reranking(self) -> None:
        passages, _ = retrieval.search("q", top_k=2, use_cache=False)
        self.assertEqual(len(passages), 2)
        self.assertEqual([p.title for p in passages], self.rerank_order[:2])


class _FakeStore:
    """A vector store whose single hit per parent sets the RRF order."""

    def __init__(self, order: list[str]) -> None:
        self._order = order

    def query(self, scope, vector, top_k, flt):
        matches = []
        for rank, name in enumerate(self._order, start=1):
            match = type("M", (), {})()
            match.key = f"{name}#0"
            match.score = 1.0 - 0.1 * rank
            match.metadata = {"parentId": name}
            matches.append(match)
        return matches

"""The semantic cache must shorten a search, never change its contract.

A cached answer is only safe if it was produced for the same *question shape*
and the same visibility scope. So these tests pin three things:

* a near-duplicate hit returns the cached passages and never runs the vector,
  BM25, hydration or rerank work;
* a miss stores the payload under a signature that includes the audience, the
  admin flag, ``top_k`` and the rerank setting;
* a broken or malformed cache degrades to a normal search.

No Redis, no AWS, no S3: ``core.semantic_cache`` is replaced with a recorder and
every retrieval dependency is stubbed.
"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from typing import Any

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parent / "packages"
for extra in (str(SERVICE_ROOT), str(PACKAGES)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from core import semantic_cache  # noqa: E402
from src import retrieval  # noqa: E402


def _cached(title: str) -> dict[str, Any]:
    return {
        "index": 1,
        "title": title,
        "route": f"/docs#{title}",
        "content": f"body of {title}",
        "matchedContent": f"body of {title}",
        "snippet": f"body of {title}",
        "score": 0.5,
    }


class _Store:
    """A vector store that records how often the semantic leg ran."""

    def __init__(self) -> None:
        self.queries = 0

    def query(self, scope, vector, top_k, flt):
        self.queries += 1
        match = type("M", (), {})()
        match.key = "alpha#0"
        match.score = 0.9
        match.metadata = {"parentId": "alpha"}
        return [match]


class SemanticCacheWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self._patched: list[tuple[object, str, object]] = []
        self._rerank_env = os.environ.get("AI_ASSISTANT_RERANK")
        # Reranking is off so the pipeline's ordering is deterministic; the
        # rerank flag is still asserted to be part of the cache signature.
        os.environ["AI_ASSISTANT_RERANK"] = "0"

        self.semantic_hit: tuple[list[dict[str, Any]], dict[str, Any]] | None = None
        self.lookups: list[dict[str, Any]] = []
        self.stores: list[dict[str, Any]] = []
        self.store = _Store()

        self._patch(retrieval.cache, "get", lambda key: None)
        self._patch(retrieval.cache, "set", lambda *a, **k: None)
        self._patch(retrieval, "embed_texts", lambda texts, config: [[0.1, 0.2, 0.3]])
        self._patch(retrieval, "load_config", lambda: None)
        self._patch(retrieval, "Storage", lambda: object())
        self._patch(retrieval, "vector_store", lambda storage: self.store)
        self._patch(retrieval, "_lexical_leg", lambda *a, **k: [])
        self._patch(retrieval, "_load_parent", self._fake_parent)
        self._patch(semantic_cache, "lookup_match", self._lookup)
        self._patch(semantic_cache, "store", self._store)

    def tearDown(self) -> None:
        for target, name, original in reversed(self._patched):
            setattr(target, name, original)
        if self._rerank_env is None:
            os.environ.pop("AI_ASSISTANT_RERANK", None)
        else:
            os.environ["AI_ASSISTANT_RERANK"] = self._rerank_env

    def _patch(self, target: object, name: str, value: object) -> None:
        self._patched.append((target, name, getattr(target, name)))
        setattr(target, name, value)

    def _lookup(self, **kwargs):
        self.lookups.append(kwargs)
        return self.semantic_hit

    def _store(self, **kwargs):
        self.stores.append(kwargs)

    @staticmethod
    def _fake_parent(storage, scope, parent_id: str) -> dict:
        return {
            "content": f"body of {parent_id}",
            "route": f"/docs#{parent_id}",
            "title": parent_id,
            "children": [{"chunkId": f"{parent_id}#0", "text": f"body of {parent_id}"}],
        }

    def test_a_near_duplicate_skips_every_retrieval_leg(self) -> None:
        self.semantic_hit = (
            [_cached("cached")],
            {"backend": "redis", "kind": "semantic", "similarity": 0.98},
        )

        passages, diagnostic = retrieval.search("how do i create an agent", top_k=3)

        self.assertEqual([passage.title for passage in passages], ["cached"])
        self.assertEqual(diagnostic["stage"], "semantic-cache-hit")
        self.assertEqual(diagnostic["cache"]["backend"], "redis")
        self.assertEqual(diagnostic["returned"], 1)
        # The expensive work must not run on a hit.
        self.assertEqual(self.store.queries, 0)
        self.assertEqual(self.stores, [])
        self.assertEqual(self.lookups[0]["user_id"], "platform")
        self.assertEqual(
            self.lookups[0]["require"],
            {
                "audience": "user",
                "allowAdmin": False,
                "topK": 3,
                "rerank": False,
            },
        )

    def test_a_hit_keeps_the_rerank_score(self) -> None:
        cached = _cached("cached")
        cached["rerankScore"] = 0.87
        self.semantic_hit = ([cached], {"backend": "redis", "kind": "semantic"})

        passages, _ = retrieval.search("q", top_k=1)

        self.assertAlmostEqual(passages[0].rerank_score, 0.87)

    def test_a_miss_runs_the_search_and_stores_the_payload(self) -> None:
        passages, diagnostic = retrieval.search("q", top_k=3)

        self.assertEqual([passage.title for passage in passages], ["alpha"])
        self.assertEqual(diagnostic["stage"], "ok")
        self.assertEqual(self.store.queries, 1)
        self.assertEqual(len(self.stores), 1)
        stored = self.stores[0]
        self.assertEqual(stored["user_id"], "platform")
        self.assertEqual(stored["value"][0]["title"], "alpha")
        self.assertTrue(stored["vector_id"])
        self.assertEqual(
            stored["require"],
            {
                "audience": "user",
                "allowAdmin": False,
                "topK": 3,
                "rerank": False,
            },
        )

    def test_a_malformed_entry_is_a_miss(self) -> None:
        self.semantic_hit = (["not-a-passage"], {"backend": "redis"})

        passages, diagnostic = retrieval.search("q", top_k=3)

        self.assertEqual(diagnostic["stage"], "ok")
        self.assertEqual([passage.title for passage in passages], ["alpha"])
        self.assertEqual(self.store.queries, 1)

    def test_a_broken_cache_never_breaks_the_search(self) -> None:
        def explode(**kwargs):
            raise RuntimeError("redis is down")

        self._patch(semantic_cache, "lookup_match", explode)
        self._patch(semantic_cache, "store", explode)

        passages, diagnostic = retrieval.search("q", top_k=3)

        self.assertEqual(diagnostic["stage"], "ok")
        self.assertEqual([passage.title for passage in passages], ["alpha"])

    def test_use_cache_false_bypasses_the_semantic_cache(self) -> None:
        retrieval.search("q", top_k=3, use_cache=False)

        self.assertEqual(self.lookups, [])
        self.assertEqual(self.stores, [])

    def test_admin_and_user_never_share_an_entry(self) -> None:
        retrieval.search("q", top_k=3, audience="user", allow_admin=False)
        retrieval.search("q", top_k=3, audience="admin", allow_admin=True)

        self.assertNotEqual(
            self.lookups[0]["require"], self.lookups[1]["require"]
        )
        self.assertNotEqual(
            self.stores[0]["vector_id"], self.stores[1]["vector_id"]
        )


class SemanticSignatureTests(unittest.TestCase):
    def test_the_admin_flag_is_part_of_the_exact_key(self) -> None:
        self.assertNotEqual(
            retrieval._cache_key("q", 6, "user", allow_admin=False),
            retrieval._cache_key("q", 6, "user", allow_admin=True),
        )

    def test_every_input_that_changes_the_result_changes_the_signature(self) -> None:
        base = retrieval._semantic_require("user", 6, True)
        self.assertNotEqual(base, retrieval._semantic_require("admin", 6, True))
        self.assertNotEqual(base, retrieval._semantic_require("user", 3, True))
        self.assertNotEqual(base, retrieval._semantic_require("user", 6, False))
        self.assertNotEqual(
            base, retrieval._semantic_require("user", 6, True, allow_admin=True)
        )

    def test_the_vector_id_is_deterministic(self) -> None:
        first = retrieval._semantic_vector_id("How do I build an agent?", 6, "user", True)
        second = retrieval._semantic_vector_id(
            "  how do i build an agent?", 6, "user", True
        )
        self.assertEqual(first, second)
        self.assertNotEqual(
            first,
            retrieval._semantic_vector_id("how do i build an agent?", 6, "admin", True),
        )


if __name__ == "__main__":
    unittest.main()

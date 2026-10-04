"""Unit tests for the cache module and the embedding cache wiring."""

from __future__ import annotations

import json
import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP.parents[1] / "packages"))

from core import cache  # noqa: E402
from core import semantic_cache  # noqa: E402
from core import singleflight  # noqa: E402
from retrieval.embedding import embeddings  # noqa: E402


class CacheConfigTests(unittest.TestCase):
    def test_key_is_deterministic_and_part_sensitive(self) -> None:
        self.assertEqual(cache.cache_key("emb", "m", "t"), cache.cache_key("emb", "m", "t"))
        self.assertNotEqual(cache.cache_key("emb", "m", "t"), cache.cache_key("emb", "m", "u"))

    def test_enabled_defaults_to_dynamodb(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CACHE_BACKEND", None)
            self.assertTrue(cache.enabled())
        with mock.patch.dict(os.environ, {"CACHE_BACKEND": "dynamodb"}):
            self.assertTrue(cache.enabled())

    def test_backend_none_disables(self) -> None:
        with mock.patch.dict(os.environ, {"CACHE_BACKEND": "none"}):
            self.assertFalse(cache.enabled())

    def test_ttl_from_env_and_default(self) -> None:
        with mock.patch.dict(os.environ, {"CACHE_SEARCH_TTL_SECONDS": "120"}):
            self.assertEqual(cache.ttl("search", 300), 120)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CACHE_SEARCH_TTL_SECONDS", None)
            self.assertEqual(cache.ttl("search", 300), 300)


class EmbeddingCacheTests(unittest.TestCase):
    def _config(self) -> SimpleNamespace:
        return SimpleNamespace(
            embed_mode="bedrock",
            text_embed_model="amazon.titan-embed-text-v2:0",
            image_embed_model="amazon.titan-embed-image-v1",
            embedding_dim=3,
            embed_images=False,
            bedrock_region="us-east-1",
            local_embed_url="",
            local_embed_model="",
        )

    def test_reuses_cached_vectors(self) -> None:
        store: dict = {}
        calls = {"n": 0}

        def fake_embed(texts, config):
            calls["n"] += 1
            return [[1.0, 2.0, 3.0] for _ in texts]

        def fake_key(*parts):
            return "k:" + "|".join(str(part) for part in parts)

        with mock.patch.object(embeddings, "_embed_uncached", fake_embed), mock.patch.object(
            cache, "enabled", lambda: True
        ), mock.patch.object(cache, "cache_key", fake_key), mock.patch.object(
            cache, "get_many", lambda keys: [store.get(key) for key in keys]
        ), mock.patch.object(
            cache, "set_many", lambda pairs, ttl: store.update(dict(pairs))
        ), mock.patch.object(
            cache, "ttl", lambda kind, default: default
        ):
            first = embeddings.embed_texts(["a", "b"], self._config())
            second = embeddings.embed_texts(["a", "b"], self._config())
            third = embeddings.embed_texts(["a", "c"], self._config())

        self.assertEqual(first, second)
        # Only the one miss for "c" triggered a new embedding call in the 3rd run.
        self.assertEqual(calls["n"], 2)
        self.assertEqual(len(third), 2)
        self.assertEqual(third[1], [1.0, 2.0, 3.0])


class SemanticCacheTests(unittest.TestCase):
    ENV = {
        "SEMANTIC_CACHE_ENABLED": "true",
        "SEMANTIC_CACHE_THRESHOLD": "0.9",
        "SEMANTIC_CACHE_TTL_SECONDS": "600",
    }

    class _Match:
        def __init__(self, key, score, metadata):
            self.key = key
            self.score = score
            self.metadata = metadata

    class _FakeStore:
        def __init__(self, matches):
            self.matches = matches
            self.upserts = []
            self.filters = None

        def query(self, sub, vector, top_k, filters=None):
            self.filters = filters
            return self.matches

        def upsert(self, sub, records):
            self.upserts.append((sub, records))

    class _FakeCache:
        def __init__(self, on=True):
            self.items = {}
            self.on = on

        def enabled(self):
            return self.on

        def cache_key(self, kind, *parts):
            return kind + ":" + "|".join(str(part) for part in parts)

        def get(self, key):
            return self.items.get(key)

        def set(self, key, value, _ttl):
            self.items[key] = value

    def test_lookup_returns_hit_above_threshold(self) -> None:
        now = int(time.time())
        store = self._FakeStore(
            [self._Match("a", 0.97, {"expiresAt": now + 60, "kind": "semcache", "kb": "kb1"})]
        )
        fake_cache = self._FakeCache()
        fake_cache.items["semcache:u_1|a"] = {"chunks": [1]}

        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
            semantic_cache, "vector_store", lambda: store
        ), mock.patch.object(semantic_cache, "_cache", lambda: fake_cache):
            self.assertTrue(semantic_cache.enabled())
            result = semantic_cache.lookup(
                user_id="u_1", vector=[0.1, 0.2], require={"kb": "kb1"}
            )

        self.assertEqual(result, {"chunks": [1]})
        self.assertEqual(store.filters, {"kind": "semcache", "kb": "kb1"})

    def test_lookup_misses_on_low_score_or_expiry(self) -> None:
        now = int(time.time())
        scenarios = [
            [self._Match("a", 0.5, {"expiresAt": now + 60, "kind": "semcache"})],
            [self._Match("a", 0.99, {"expiresAt": now - 1, "kind": "semcache"})],
            [self._Match("a", 0.99, {"expiresAt": now + 60, "kind": "semcache"})],  # no payload
        ]
        for matches in scenarios:
            store = self._FakeStore(matches)
            fake_cache = self._FakeCache()
            with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
                semantic_cache, "vector_store", lambda: store
            ), mock.patch.object(semantic_cache, "_cache", lambda: fake_cache):
                self.assertIsNone(
                    semantic_cache.lookup(user_id="u_1", vector=[0.1], require={"kb": "kb1"})
                )

    def test_store_upserts_vector_and_payload(self) -> None:
        store = self._FakeStore([])
        fake_cache = self._FakeCache()
        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
            semantic_cache, "vector_store", lambda: store
        ), mock.patch.object(semantic_cache, "_cache", lambda: fake_cache):
            semantic_cache.store(
                user_id="u_1",
                vector=[0.1, 0.2],
                value={"a": 1},
                vector_id="abc",
                require={"kb": "kb1"},
            )

        self.assertEqual(len(store.upserts), 1)
        sub, records = store.upserts[0]
        self.assertEqual(sub, "u_1")
        record = records[0]
        self.assertEqual(record.key, "abc")
        self.assertEqual(record.filterable["kb"], "kb1")
        self.assertEqual(record.filterable["kind"], "semcache")
        self.assertIn("expiresAt", record.filterable)
        self.assertEqual(fake_cache.items["semcache:u_1|abc"], {"a": 1})

    def test_disabled_when_cache_backend_off(self) -> None:
        fake_cache = self._FakeCache(on=False)
        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
            semantic_cache, "_cache", lambda: fake_cache
        ):
            self.assertFalse(semantic_cache.enabled())
            self.assertIsNone(semantic_cache.lookup(user_id="u", vector=[0.1]))


class SingleFlightTests(unittest.TestCase):
    ENV = {
        "CACHE_BACKEND": "dynamodb",
        "SINGLE_FLIGHT_ENABLED": "true",
    }

    def test_acquire_delegates_to_cache_lock(self) -> None:
        with mock.patch.dict(os.environ, self.ENV):
            with mock.patch.object(cache, "set_nx", lambda key, ttl: True):
                self.assertTrue(singleflight.acquire("k", 10))
            with mock.patch.object(cache, "set_nx", lambda key, ttl: False):
                self.assertFalse(singleflight.acquire("k", 10))

    def test_single_flight_waits_for_cached_result(self) -> None:
        compute_calls = {"n": 0}

        def compute():
            compute_calls["n"] += 1
            return {"source": "computed"}

        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
            singleflight, "enabled", lambda: True
        ), mock.patch.object(
            singleflight, "acquire", lambda key, ttl: False
        ), mock.patch.object(
            cache, "get", lambda key: {"source": "cached"}
        ):
            result = singleflight.single_flight(
                lock_key="l", result_key="r", ttl_seconds=10, wait=1.0, compute=compute
            )
        self.assertEqual(result, {"source": "cached"})
        self.assertEqual(compute_calls["n"], 0)

    def test_single_flight_computes_when_lock_acquired(self) -> None:
        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
            singleflight, "enabled", lambda: True
        ), mock.patch.object(
            singleflight, "acquire", lambda key, ttl: True
        ), mock.patch.object(
            singleflight, "release", lambda key: None
        ):
            result = singleflight.single_flight(
                lock_key="l",
                result_key="r",
                ttl_seconds=10,
                wait=1.0,
                compute=lambda: {"source": "computed"},
            )
        self.assertEqual(result, {"source": "computed"})


if __name__ == "__main__":
    unittest.main()

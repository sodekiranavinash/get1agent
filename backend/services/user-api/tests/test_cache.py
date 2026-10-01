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

    def test_enabled_requires_credentials(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("UPSTASH_REDIS_REST_URL", None)
            os.environ.pop("UPSTASH_REDIS_REST_TOKEN", None)
            os.environ["CACHE_BACKEND"] = "redis"
            self.assertFalse(cache.enabled())
        with mock.patch.dict(
            os.environ,
            {
                "CACHE_BACKEND": "redis",
                "UPSTASH_REDIS_REST_URL": "https://x.upstash.io",
                "UPSTASH_REDIS_REST_TOKEN": "tok",
            },
        ):
            self.assertTrue(cache.enabled())

    def test_backend_none_disables(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "CACHE_BACKEND": "none",
                "UPSTASH_REDIS_REST_URL": "https://x.upstash.io",
                "UPSTASH_REDIS_REST_TOKEN": "tok",
            },
        ):
            self.assertFalse(cache.enabled())

    def test_ttl_from_env_and_default(self) -> None:
        with mock.patch.dict(os.environ, {"CACHE_SEARCH_TTL_SECONDS": "120"}):
            self.assertEqual(cache.ttl("search", 300), 120)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CACHE_SEARCH_TTL_SECONDS", None)
            self.assertEqual(cache.ttl("search", 300), 300)


class CacheCommandTests(unittest.TestCase):
    def test_get_and_set_round_trip(self) -> None:
        store: dict[str, str] = {}
        calls: list = []

        def fake_post(path, payload):
            calls.append((path, payload))
            if path == "/pipeline":
                results = []
                for command in payload:
                    if command[0] == "GET":
                        results.append({"result": store.get(command[1])})
                    else:
                        store[command[1]] = command[2]
                        results.append({"result": "OK"})
                return results
            if payload[0] == "GET":
                return {"result": store.get(payload[1])}
            store[payload[1]] = payload[2]
            return {"result": "OK"}

        env = {
            "CACHE_BACKEND": "redis",
            "UPSTASH_REDIS_REST_URL": "https://x.upstash.io",
            "UPSTASH_REDIS_REST_TOKEN": "tok",
        }
        with mock.patch.dict(os.environ, env), mock.patch.object(cache, "_post", fake_post):
            cache.set("k", {"a": 1}, 60)
            self.assertEqual(cache.get("k"), {"a": 1})
            self.assertIsNone(cache.get("missing"))
            cache.set_many([("k2", [1, 2, 3])], 60)
            self.assertEqual(cache.get_many(["k", "k2"]), [{"a": 1}, [1, 2, 3]])
            self.assertEqual(cache.get_many([]), [])

        # SET carries the TTL.
        set_call = [c for c in calls if c[0] == "" and c[1][0] == "SET"][0]
        self.assertEqual(set_call[1][-2:], ["EX", 60])
        # get_many uses the pipeline endpoint.
        self.assertTrue(any(c[0] == "/pipeline" for c in calls))


class EmbeddingCacheTests(unittest.TestCase):
    def _config(self) -> SimpleNamespace:
        return SimpleNamespace(
            embed_mode="voyage",
            text_embed_model="voyage-4-large",
            embedding_dim=3,
            bedrock_region="us-east-1",
            local_embed_url="",
            local_embed_model="",
        )

    def test_reuses_cached_vectors(self) -> None:
        store: dict = {}
        calls = {"n": 0}

        def fake_embed(texts, config, input_type):
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
        "UPSTASH_VECTOR_REST_URL": "https://v.upstash.io",
        "UPSTASH_VECTOR_REST_TOKEN": "tok",
        "SEMANTIC_CACHE_THRESHOLD": "0.9",
        "SEMANTIC_CACHE_TTL_SECONDS": "600",
    }

    def _fake(self, hits):
        calls: list = []

        def fake_request(path, payload):
            calls.append((path, payload))
            if path.startswith("/query/"):
                return {"result": hits}
            return {"result": "Success"}

        return calls, fake_request

    def test_lookup_returns_hit_above_threshold(self) -> None:
        hits = [
            {
                "id": "a",
                "score": 0.97,
                "metadata": {"expiresAt": int(time.time()) + 60, "kb": "kb1"},
                "data": '{"chunks": [1]}',
            }
        ]
        calls, fake = self._fake(hits)
        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
            semantic_cache, "_request", fake
        ):
            self.assertTrue(semantic_cache.enabled())
            result = semantic_cache.lookup(
                user_id="u_1", vector=[0.1, 0.2], require={"kb": "kb1"}
            )
        self.assertEqual(result, {"chunks": [1]})
        self.assertTrue(calls[0][0].startswith("/query/"))

    def test_lookup_misses(self) -> None:
        now = int(time.time())
        scenarios = [
            [{"score": 0.5, "metadata": {"expiresAt": now + 60, "kb": "kb1"}, "data": "{}"}],
            [{"score": 0.99, "metadata": {"expiresAt": now - 1, "kb": "kb1"}, "data": "{}"}],
            [{"score": 0.99, "metadata": {"expiresAt": now + 60, "kb": "other"}, "data": "{}"}],
        ]
        for hits in scenarios:
            _, fake = self._fake(hits)
            with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
                semantic_cache, "_request", fake
            ):
                self.assertIsNone(
                    semantic_cache.lookup(
                        user_id="u_1", vector=[0.1], require={"kb": "kb1"}
                    )
                )

    def test_store_is_namespaced_with_ttl_metadata(self) -> None:
        calls, fake = self._fake([])
        with mock.patch.dict(os.environ, self.ENV), mock.patch.object(
            semantic_cache, "_request", fake
        ):
            semantic_cache.store(
                user_id="u_1",
                vector=[0.1, 0.2],
                value={"a": 1},
                vector_id="abc",
                require={"kb": "kb1"},
            )
        path, payload = calls[0]
        self.assertTrue(path.startswith("/upsert/"))
        self.assertIn("u_1", path)
        self.assertEqual(payload["id"], "abc")
        self.assertEqual(payload["metadata"]["kb"], "kb1")
        self.assertIn("expiresAt", payload["metadata"])
        self.assertEqual(json.loads(payload["data"]), {"a": 1})

    def test_disabled_without_credentials(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("UPSTASH_VECTOR_REST_URL", None)
            os.environ.pop("UPSTASH_VECTOR_REST_TOKEN", None)
            self.assertFalse(semantic_cache.enabled())
            self.assertIsNone(semantic_cache.lookup(user_id="u", vector=[0.1]))


class SingleFlightTests(unittest.TestCase):
    ENV = {
        "CACHE_BACKEND": "redis",
        "UPSTASH_REDIS_REST_URL": "https://x.upstash.io",
        "UPSTASH_REDIS_REST_TOKEN": "tok",
        "SINGLE_FLIGHT_ENABLED": "true",
    }

    def test_acquire_true_only_on_ok(self) -> None:
        def fake_ok(*args):
            return "OK"

        def fake_held(*args):
            return None

        with mock.patch.dict(os.environ, self.ENV):
            with mock.patch.object(cache, "_command", fake_ok):
                self.assertTrue(singleflight.acquire("k", 10))
            with mock.patch.object(cache, "_command", fake_held):
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

"""Semantic cache on Redis (RediSearch vector index).

``fakeredis`` has no RediSearch, so ``FakeSearchRedis`` implements just the
``FT.CREATE``/``FT.SEARCH`` surface our module uses (a real brute-force cosine
index) on top of the in-memory server. That pins the command construction, the
``WITHATTRIBS``-free reply parsing, the distance -> similarity conversion, the
requirement (kbTag) isolation and the threshold — the parts that would silently
degrade a hit into a miss.

The real Redis Stack commands were verified against the container; these run
everywhere (no Docker).
"""

from __future__ import annotations

import math
import re
import struct

import fakeredis
import pytest
from redis.exceptions import ResponseError

from core import cache, redis_client
from core import semantic_cache, semantic_cache_redis

FAKE_URL = "redis://fake.invalid:6379/0"
USER = "u_7k3f9qz2mpx8n4rq"


def _cosine_distance(left: list[float], right: list[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 1.0
    return 1.0 - dot / (left_norm * right_norm)


class FakeSearchRedis(fakeredis.FakeRedis):
    """A ``FakeRedis`` with the two RediSearch commands our cache issues."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("decode_responses", True)
        super().__init__(*args, **kwargs)
        self.indexes: dict[str, dict[str, object]] = {}
        self.docs: dict[str, dict[str, object]] = {}
        self.creates = 0

    def execute_command(self, *args, **kwargs):
        name = str(args[0]).upper()
        if name == "FT.CREATE":
            return self._ft_create(args)
        if name == "FT.SEARCH":
            return self._ft_search(args)
        if name == "COMMAND":  # the support probe
            return [["FT.SEARCH", -1, ["readonly"], 0, 0, 0]]
        return super().execute_command(*args, **kwargs)

    def hset(self, key, *args, **kwargs):
        mapping = kwargs.get("mapping")
        result = super().hset(key, *args, **kwargs)
        if mapping:
            self.docs[key] = dict(mapping)
        return result

    def _ft_create(self, args):
        index = args[1]
        prefix = args[args.index("PREFIX") + 2]
        dim = int(args[args.index("DIM") + 1])
        if index in self.indexes:
            raise ResponseError("Index already exists")
        self.creates += 1
        self.indexes[index] = {"prefix": prefix, "dim": dim}
        return "OK"

    def _ft_search(self, args):
        spec = self.indexes.get(args[1])
        if spec is None:
            raise ResponseError(f"No such index {args[1]}")
        query = args[2]
        dim = int(spec["dim"])  # type: ignore[arg-type]
        prefix = str(spec["prefix"])
        blob = args[args.index("blob") + 1]
        query_vector = list(struct.unpack(f"<{dim}f", blob))
        tag = str(re.search(r"@kbTag:\{([^}]*)\}", query).group(1))
        knn = int(re.search(r"KNN (\d+)", query).group(1))

        scored: list[tuple[str, float]] = []
        for key, doc in self.docs.items():
            if not key.startswith(prefix) or str(doc.get("kbTag")) != tag:
                continue
            raw = doc["vec"]
            vector = list(struct.unpack(f"<{len(raw) // 4}f", raw))  # type: ignore[arg-type]
            scored.append((key, _cosine_distance(query_vector, vector)))
        scored.sort(key=lambda item: item[1])

        out: list[object] = [len(scored)]
        for key, distance in scored[:knn]:
            out += [key, ["score", repr(distance)]]
        return out


@pytest.fixture
def redis_sem(monkeypatch: pytest.MonkeyPatch):
    fake = FakeSearchRedis(server=fakeredis.FakeServer())
    monkeypatch.setenv("REDIS_URL", FAKE_URL)
    monkeypatch.setenv("CACHE_BACKEND", "auto")
    monkeypatch.setenv("SEMANTIC_CACHE_BACKEND", "auto")
    monkeypatch.setenv("SEMANTIC_CACHE_ENABLED", "true")
    redis_client.reset()
    semantic_cache_redis.reset()
    with monkeypatch.context() as patch:
        patch.setattr(redis_client, "_CLIENT", fake)
        patch.setattr(redis_client, "_CLIENT_TARGET", FAKE_URL)
        yield fake
    redis_client.reset()
    semantic_cache_redis.reset()


def test_the_backend_is_redis_once_it_answers(redis_sem) -> None:
    assert semantic_cache_redis.supported() is True
    assert semantic_cache.backend() == "redis"
    assert semantic_cache.enabled() is True


def test_a_stored_query_is_returned_with_its_match_info(redis_sem) -> None:
    vector = [1.0, 0.0, 0.0]
    semantic_cache.store(
        user_id=USER,
        vector=vector,
        value={"chunks": ["a"]},
        vector_id="q1",
        require={"kb": "kb-a"},
    )

    match = semantic_cache.lookup_match(
        user_id=USER, vector=[0.99, 0.01, 0.0], require={"kb": "kb-a"}
    )

    assert match is not None
    payload, info = match
    assert payload == {"chunks": ["a"]}
    assert info["backend"] == "redis"
    assert info["kind"] == "semantic"
    assert info["similarity"] > 0.99
    assert info["vectorId"] == "q1"


def test_a_distant_query_is_a_miss(redis_sem) -> None:
    semantic_cache.store(
        user_id=USER,
        vector=[1.0, 0.0, 0.0],
        value={"chunks": ["a"]},
        vector_id="q1",
        require={"kb": "kb-a"},
    )

    # Orthogonal -> similarity 0, well under the 0.95 default.
    assert semantic_cache.lookup(user_id=USER, vector=[0.0, 1.0, 0.0]) is None


def test_the_requirement_set_isolates_entries(redis_sem) -> None:
    semantic_cache.store(
        user_id=USER,
        vector=[1.0, 0.0, 0.0],
        value={"chunks": ["a"]},
        vector_id="q1",
        require={"kb": "kb-a"},
    )

    # Same embedding, different knowledge-base set: never a hit.
    assert semantic_cache.lookup(user_id=USER, vector=[1.0, 0.0, 0.0], require={"kb": "kb-b"}) is None
    assert semantic_cache.lookup(user_id=USER, vector=[1.0, 0.0, 0.0], require={"kb": "kb-a"}) == {
        "chunks": ["a"]
    }


def test_the_index_is_created_once(redis_sem) -> None:
    for index in range(3):
        semantic_cache.store(
            user_id=USER,
            vector=[1.0, 0.0, 0.0],
            value={"n": index},
            vector_id=f"q{index}",
            require={"kb": "kb-a"},
        )
    assert redis_sem.creates == 1


def test_a_missing_index_is_a_miss_without_opening_the_breaker(redis_sem) -> None:
    assert semantic_cache_redis.nearest(
        user_id="u_never", vector=[1.0, 0.0, 0.0], kb_tag="deadbeef"
    ) is None
    assert redis_client.breaker_open() is False


def test_the_payload_lives_in_the_shared_cache(redis_sem) -> None:
    semantic_cache.store(
        user_id=USER,
        vector=[1.0, 0.0, 0.0],
        value={"chunks": ["a"]},
        vector_id="q1",
        require={"kb": "kb-a"},
    )
    key = cache.cache_key("semcache", USER, "q1")
    assert cache.get(key) == {"chunks": ["a"]}


def test_s3vectors_can_be_forced_and_none_disables(redis_sem, monkeypatch) -> None:
    monkeypatch.setenv("SEMANTIC_CACHE_BACKEND", "s3vectors")
    assert semantic_cache.backend() == "s3vectors"
    monkeypatch.setenv("SEMANTIC_CACHE_BACKEND", "none")
    assert semantic_cache.backend() == "none"
    assert semantic_cache.enabled() is False


def test_rows_parses_both_redis_py_reply_shapes() -> None:
    # Raw array reply: [total, key, [field, value, …], …]
    raw = [2, "g1a:doc:u_1:e1", ["score", "0.03"], "g1a:doc:u_1:e2", ["score", "0.11"]]
    rows = semantic_cache_redis._rows(raw, "g1a:doc:u_1:")
    assert rows == [("e1", 0.03), ("e2", 0.11)]

    # Parsed object reply (some redis-py versions).
    parsed = {
        "results": [
            {"id": "g1a:doc:u_1:e1", "extra_attributes": {"score": "0.03"}},
            {"id": "g1a:doc:u_1:e2", "extra_attributes": {"score": "0.11"}},
        ]
    }
    assert semantic_cache_redis._rows(parsed, "g1a:doc:u_1:") == [("e1", 0.03), ("e2", 0.11)]


def test_rows_parses_byte_keys_from_a_non_decoding_client() -> None:
    # redis-py 8 returns a parsed dict whose keys stay bytes when the client
    # does not decode responses — the shape a decode_responses=False client
    # yields, which would otherwise read as "no match" and silently disable the
    # semantic cache.
    parsed = {
        b"results": [
            {b"id": b"g1a:doc:u_1:e1", b"extra_attributes": {b"score": b"0.03"}},
            {b"id": b"g1a:doc:u_1:e2", b"extra_attributes": {b"score": b"0.11"}},
        ]
    }
    assert semantic_cache_redis._rows(parsed, "g1a:doc:u_1:") == [("e1", 0.03), ("e2", 0.11)]

    raw = [1, b"g1a:doc:u_1:e1", [b"score", b"0.03"]]
    assert semantic_cache_redis._rows(raw, "g1a:doc:u_1:") == [("e1", 0.03)]


def test_the_support_probe_accepts_byte_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    class ByteProbe:
        def execute_command(self, *args, **kwargs):
            return {b"FT.SEARCH": {b"flags": []}}

    monkeypatch.setattr(semantic_cache_redis, "_redis", lambda: ByteProbe())
    semantic_cache_redis.reset()
    assert semantic_cache_redis.supported() is True
    semantic_cache_redis.reset()

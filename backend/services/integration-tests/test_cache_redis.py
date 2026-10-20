"""The exact cache's Redis backend (``CACHE_BACKEND=auto``/``redis``).

The DynamoDB path is the long-standing one; these pin the new behaviour: Redis
answers while it is up, DynamoDB takes over when it is not, and a ``redis``-only
deployment degrades to a miss rather than reaching for DynamoDB.
"""

from __future__ import annotations

import fakeredis
import pytest

from core import cache, redis_client

FAKE_URL = "redis://fake.invalid:6379/0"


@pytest.fixture
def redis_env(monkeypatch: pytest.MonkeyPatch):
    """Install an in-process Redis into ``core.redis_client`` (backend ``auto``)."""
    fake = fakeredis.FakeRedis(server=fakeredis.FakeServer(), decode_responses=True)
    monkeypatch.setenv("REDIS_URL", FAKE_URL)
    monkeypatch.setenv("CACHE_BACKEND", "auto")
    redis_client.reset()
    with monkeypatch.context() as patch:
        patch.setattr(redis_client, "_CLIENT", fake)
        patch.setattr(redis_client, "_CLIENT_TARGET", FAKE_URL)
        yield fake
    redis_client.reset()


def _no_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.setenv("REDIS_URL_SSM_PARAM", "")
    redis_client.reset()


def test_round_trip_and_delete(redis_env) -> None:
    key = cache.cache_key("search", "u_1", "q")
    assert cache.get(key) is None

    cache.set(key, {"chunks": [1, 2]}, 300)
    assert cache.get(key) == {"chunks": [1, 2]}

    cache.delete(key)
    assert cache.get(key) is None


def test_batch_round_trip_uses_one_mget(redis_env) -> None:
    keys = [cache.cache_key("emb", "m", str(i)) for i in range(3)]
    cache.set_many(list(zip(keys, [[i] for i in range(3)])), 60)

    calls: list[object] = []
    original = redis_env.mget

    def counting(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)

    redis_env.mget = counting  # type: ignore[method-assign]
    assert cache.get_many(keys) == [[0], [1], [2]]
    assert len(calls) == 1
    assert cache.get_many([keys[0], cache.cache_key("emb", "m", "missing")]) == [[0], None]


def test_ttl_is_applied(redis_env) -> None:
    key = cache.cache_key("search", "u_1", "q")
    cache.set(key, {"ok": True}, 120)
    assert 0 < redis_env.ttl(key) <= 120


def test_set_nx_is_atomic(redis_env) -> None:
    key = cache.cache_key("sf", "lock")
    assert cache.set_nx(key, 20) is True
    assert cache.set_nx(key, 20) is False
    cache.delete(key)
    assert cache.set_nx(key, 20) is True


def test_auto_falls_back_to_dynamodb_when_redis_is_unavailable(monkeypatch) -> None:
    _no_redis(monkeypatch)
    key = cache.cache_key("search", "u_1", "q")

    cache.set(key, {"from": "dynamodb"}, 300)
    assert cache.get(key) == {"from": "dynamodb"}
    # And the batch path still works against the table.
    cache.set_many([(key, {"from": "dynamodb"})], 300)
    assert cache.get_many([key]) == [{"from": "dynamodb"}]

    cache.delete(key)
    assert cache.get(key) is None


def test_redis_only_degrades_to_a_miss_when_unavailable(monkeypatch) -> None:
    _no_redis(monkeypatch)
    monkeypatch.setenv("CACHE_BACKEND", "redis")
    key = cache.cache_key("search", "u_1", "q")

    assert cache.enabled() is True
    cache.set(key, {"x": 1}, 300)  # no-op, must not raise
    assert cache.get(key) is None  # never reaches DynamoDB
    assert cache.get_many([key]) == [None]
    assert cache.set_nx(key, 20) is True  # fail-open


def test_redis_is_used_while_it_answers(redis_env) -> None:
    key = cache.cache_key("search", "u_1", "q")
    cache.set(key, {"from": "redis"}, 300)
    assert cache.get(key) == {"from": "redis"}
    # Nothing was written to DynamoDB for that key.
    assert cache._ddb_get(key) is None  # noqa: SLF001 - asserting backend choice

"""Reranker: the Voyage backend (payloads, mapping, graceful fallback)."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request

from src.search import rerank


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args) -> bool:
        return False


def _candidates() -> list[dict]:
    return [{"content": "alpha"}, {"content": "beta"}]


def test_rerank_mode_defaults_to_voyage(monkeypatch) -> None:
    monkeypatch.delenv("RERANK_MODE", raising=False)

    assert rerank.rerank_mode() == "voyage"


def test_rerank_voyage_builds_request_and_maps_scores(monkeypatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    captured: dict = {}

    def fake_urlopen(request, timeout=None):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data)
        captured["auth"] = request.get_header("Authorization")
        body = {
            "data": [
                {"index": 1, "relevance_score": 0.9},
                {"index": 0, "relevance_score": 0.1},
            ]
        }
        return _FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    ranked = rerank._rerank_voyage("q", _candidates(), 2)

    assert [candidate["content"] for candidate in ranked] == ["beta", "alpha"]
    assert ranked[0]["rerankScore"] == 0.9
    assert captured["url"].endswith("/rerank")
    assert captured["auth"] == "Bearer test-key"
    assert captured["payload"]["documents"] == ["alpha", "beta"]
    assert captured["payload"]["model"] == "rerank-3"
    assert captured["payload"]["top_k"] == 2


def test_rerank_candidates_applies_voyage(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_MODE", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    def fake_urlopen(request, timeout=None):
        body = {"data": [{"index": 1, "relevance_score": 0.9}]}
        return _FakeResponse(json.dumps(body).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    ranked, applied = rerank.rerank_candidates("q", _candidates(), 1)

    assert applied is True
    assert [candidate["content"] for candidate in ranked] == ["beta"]


def test_rerank_candidates_falls_back_without_api_key(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_MODE", "voyage")
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    ranked, applied = rerank.rerank_candidates("q", _candidates(), 2)

    assert applied is False
    assert [candidate["content"] for candidate in ranked] == ["alpha", "beta"]


def test_rerank_candidates_falls_back_on_http_error(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_MODE", "voyage")
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"detail": "rate limited"}'),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    ranked, applied = rerank.rerank_candidates("q", _candidates(), 2)

    assert applied is False
    assert [candidate["content"] for candidate in ranked] == ["alpha", "beta"]


def test_rerank_candidates_none_is_a_passthrough(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_MODE", "none")

    ranked, applied = rerank.rerank_candidates("q", _candidates(), 1)

    assert applied is False
    assert ranked == [{"content": "alpha"}]

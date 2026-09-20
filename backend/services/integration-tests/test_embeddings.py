"""Embedding clients: the Voyage AI backend (payloads + error handling)."""

from __future__ import annotations

import io
import urllib.error
from dataclasses import replace

import pytest

from retrieval.embedding import embeddings
from retrieval.embedding.config import load_config


def _voyage_config(**overrides):
    base = replace(
        load_config(),
        embed_mode="voyage",
        text_embed_model="voyage-4-large",
        image_embed_model="voyage-multimodal-3.5",
        embedding_dim=4,
        voyage_api_base_url="https://api.voyageai.com/v1",
    )
    return replace(base, **overrides)


def _vectors(count: int) -> dict:
    return {
        "data": [
            {"index": index, "embedding": [float(index), 0.0, 0.0, 1.0]}
            for index in range(count)
        ]
    }


def test_load_config_resolves_voyage_models(monkeypatch) -> None:
    monkeypatch.setenv("EMBED_MODE", "voyage")
    monkeypatch.setenv("VOYAGE_TEXT_MODEL", "voyage-4-large")
    monkeypatch.setenv("VOYAGE_MULTIMODAL_MODEL", "voyage-multimodal-3.5")

    config = load_config()

    assert config.embed_mode == "voyage"
    assert config.text_embed_model == "voyage-4-large"
    assert config.image_embed_model == "voyage-multimodal-3.5"


def test_embed_texts_builds_voyage_request(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_post(path, payload, config):
        calls.append((path, payload))
        return _vectors(len(payload["input"]))

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(embeddings, "_voyage_post", fake_post)

    vectors = embeddings.embed_texts(["a", "b"], _voyage_config())

    assert vectors == [[0.0, 0.0, 0.0, 1.0], [1.0, 0.0, 0.0, 1.0]]
    path, payload = calls[0]
    assert path == "/embeddings"
    assert payload["model"] == "voyage-4-large"
    assert payload["input_type"] == "document"
    assert payload["output_dimension"] == 4
    assert payload["truncation"] is True


def test_embed_texts_forwards_query_input_type(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_post(path, payload, config):
        calls.append(payload)
        return _vectors(len(payload["input"]))

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(embeddings, "_voyage_post", fake_post)

    embeddings.embed_texts(["q"], _voyage_config(), input_type="query")

    assert calls[0]["input_type"] == "query"


def test_embed_texts_splits_into_batches(monkeypatch) -> None:
    calls: list[list[str]] = []

    def fake_post(path, payload, config):
        calls.append(payload["input"])
        return _vectors(len(payload["input"]))

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(embeddings, "_voyage_post", fake_post)
    monkeypatch.setattr(embeddings, "_VOYAGE_BATCH_SIZE", 2)

    vectors = embeddings.embed_texts(["a", "b", "c"], _voyage_config())

    assert len(vectors) == 3
    assert [len(batch) for batch in calls] == [2, 1]


def test_embed_images_builds_multimodal_request(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def fake_post(path, payload, config):
        calls.append((path, payload))
        return _vectors(len(payload["inputs"]))

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(embeddings, "_voyage_post", fake_post)

    png = b"\x89PNG\r\n\x1a\n" + b"data"
    vectors = embeddings.embed_images([png], _voyage_config())

    assert vectors == [[0.0, 0.0, 0.0, 1.0]]
    path, payload = calls[0]
    assert path == "/multimodalembeddings"
    assert payload["model"] == "voyage-multimodal-3.5"
    content = payload["inputs"][0]["content"][0]
    assert content["type"] == "image_base64"
    assert content["image_base64"].startswith("data:image/png;base64,")


def test_voyage_post_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    with pytest.raises(embeddings.VoyageError):
        embeddings._voyage_post("/embeddings", {}, _voyage_config())


def test_voyage_post_maps_rate_limit_to_retryable(monkeypatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    def fake_urlopen(request, timeout=None):
        raise urllib.error.HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"detail": "rate limited"}'),
        )

    monkeypatch.setattr(embeddings.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(embeddings.VoyageError) as excinfo:
        embeddings._voyage_post("/embeddings", {"input": ["x"]}, _voyage_config())

    assert excinfo.value.status == 429
    assert excinfo.value.retryable is True
    assert "rate limited" in str(excinfo.value)

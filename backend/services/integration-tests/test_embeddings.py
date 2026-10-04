"""Embedding clients: Bedrock/Titan (default) and local Ollama."""

from __future__ import annotations

import json

from retrieval.embedding import embeddings
from retrieval.embedding.config import load_config

TITAN_TEXT = "amazon.titan-embed-text-v2:0"
TITAN_IMAGE = "amazon.titan-embed-image-v1"


class _FakeBody:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode()


class _FakeBedrockClient:
    def __init__(self, dim: int = 4) -> None:
        self.dim = dim
        self.calls: list[dict] = []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        return {"body": _FakeBody({"embedding": [float(self.dim)] * self.dim})}


def _config(**overrides):
    from dataclasses import replace

    base = replace(
        load_config(),
        embed_mode="bedrock",
        text_embed_model=TITAN_TEXT,
        image_embed_model=TITAN_IMAGE,
        embedding_dim=4,
    )
    return replace(base, **overrides)


def test_load_config_defaults_to_bedrock(monkeypatch) -> None:
    monkeypatch.delenv("EMBED_MODE", raising=False)
    monkeypatch.delenv("TEXT_EMBED_MODEL", raising=False)
    monkeypatch.delenv("IMAGE_EMBED_MODEL", raising=False)

    config = load_config()

    assert config.embed_mode == "bedrock"
    assert config.text_embed_model == TITAN_TEXT
    assert config.image_embed_model == TITAN_IMAGE
    assert config.embedding_dim == 1024
    assert config.embed_images is False


def test_load_config_local_uses_ollama_model(monkeypatch) -> None:
    monkeypatch.setenv("EMBED_MODE", "local")
    monkeypatch.setenv("LOCAL_EMBED_MODEL", "mxbai-embed-large")

    config = load_config()

    assert config.embed_mode == "local"
    assert config.text_embed_model == "mxbai-embed-large"
    assert config.image_embed_model == "mxbai-embed-large"


def test_load_config_embed_images_flag(monkeypatch) -> None:
    monkeypatch.setenv("EMBED_IMAGES", "true")
    assert load_config().embed_images is True
    monkeypatch.setenv("EMBED_IMAGES", "off")
    assert load_config().embed_images is False


def test_embed_texts_invokes_titan(monkeypatch) -> None:
    client = _FakeBedrockClient(dim=4)
    monkeypatch.setattr(embeddings, "_bedrock_client", lambda region: client)
    monkeypatch.setattr(embeddings, "_throttle", lambda: None)

    vectors = embeddings.embed_texts(["a", "b"], _config())

    assert vectors == [[4.0] * 4, [4.0] * 4]
    assert len(client.calls) == 2
    call = client.calls[0]
    assert call["modelId"] == TITAN_TEXT
    body = json.loads(call["body"])
    assert body["dimensions"] == 4
    assert body["normalize"] is True
    assert body["inputText"] in ("a", "b")


def test_embed_images_is_off_by_default(monkeypatch) -> None:
    called = {"n": 0}
    monkeypatch.setattr(
        embeddings, "_bedrock_client", lambda region: called.__setitem__("n", called["n"] + 1)
    )
    png = b"\x89PNG\r\n\x1a\n" + b"data"

    vectors = embeddings.embed_images([png], _config(embed_images=False))

    assert vectors == []
    assert called["n"] == 0


def test_embed_images_bedrock_when_enabled(monkeypatch) -> None:
    client = _FakeBedrockClient(dim=4)
    monkeypatch.setattr(embeddings, "_bedrock_client", lambda region: client)
    monkeypatch.setattr(embeddings, "_throttle", lambda: None)
    png = b"\x89PNG\r\n\x1a\n" + b"data"

    vectors = embeddings.embed_images([png], _config(embed_images=True))

    assert vectors == [[4.0] * 4]
    body = json.loads(client.calls[0]["body"])
    assert body["embeddingConfig"]["outputEmbeddingLength"] == 4
    assert body["inputImage"]


def test_embed_uncached_local_uses_ollama(monkeypatch) -> None:
    monkeypatch.setenv("EMBED_MODE", "local")
    config = _config(embed_mode="local", local_embed_model="mxbai-embed-large")
    seen: dict = {}

    def fake_ollama(texts, cfg):
        seen["texts"] = texts
        return [[1.0, 2.0, 3.0, 4.0] for _ in texts]

    monkeypatch.setattr(embeddings, "_ollama_embed", fake_ollama)

    assert embeddings._embed_uncached(["x"], config) == [[1.0, 2.0, 3.0, 4.0]]
    assert seen["texts"] == ["x"]

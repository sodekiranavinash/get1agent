"""Reranker: the Bedrock backend (default), local TEI, and graceful fallback.

The implementation lives in the shared `retrieval` package because both
`knowledge-mcp` and AI Assistant rerank through it — a copy in one service would
drift from the other.
"""

from __future__ import annotations

from retrieval import rerank


def _candidates() -> list[dict]:
    return [{"content": "alpha"}, {"content": "beta"}]


class _FakeBedrockRuntime:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls: list[dict] = []

    def rerank(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "results": [
                {"index": index, "relevanceScore": score}
                for index, score in enumerate(self.scores)
            ]
        }


def test_rerank_mode_defaults_to_bedrock(monkeypatch) -> None:
    monkeypatch.delenv("RERANK_MODE", raising=False)

    assert rerank.rerank_mode() == "bedrock"


def test_rerank_bedrock_maps_scores(monkeypatch) -> None:
    fake = _FakeBedrockRuntime([0.1, 0.9])
    import boto3

    monkeypatch.setattr(boto3, "client", lambda *a, **k: fake)

    ranked = rerank._rerank_bedrock(
        "q", _candidates(), 2, "arn:aws:bedrock:us-west-2::foundation-model/amazon.rerank-v1:0", "us-west-2"
    )

    assert [candidate["content"] for candidate in ranked] == ["alpha", "beta"]
    assert ranked[0]["rerankScore"] == 0.1
    assert fake.calls[0]["rerankingConfiguration"]["bedrockRerankingConfiguration"][
        "modelConfiguration"
    ]["modelArn"].endswith("amazon.rerank-v1:0")
    # The API's enum is `INLINE`. This used to send `INLINE_DOCUMENT`, which failed
    # validation on every call — and because reranking must degrade rather than fail,
    # the only symptom was that results were never actually reranked.
    assert [source["type"] for source in fake.calls[0]["sources"]] == ["INLINE", "INLINE"]


def test_rerank_candidates_applies_bedrock(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_MODE", "bedrock")
    monkeypatch.setattr(
        rerank,
        "_rerank_bedrock",
        lambda q, c, k, arn, region: [dict(c[1], rerankScore=0.9)],
    )

    ranked, applied = rerank.rerank_candidates("q", _candidates(), 1)

    assert applied is True
    assert [candidate["content"] for candidate in ranked] == ["beta"]


def test_rerank_candidates_falls_back_on_error(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_MODE", "bedrock")

    def boom(*args, **kwargs):
        raise RuntimeError("throttled")

    monkeypatch.setattr(rerank, "_rerank_bedrock", boom)

    ranked, applied = rerank.rerank_candidates("q", _candidates(), 2)

    assert applied is False
    assert [candidate["content"] for candidate in ranked] == ["alpha", "beta"]


def test_rerank_candidates_local_uses_tei(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_MODE", "local")
    monkeypatch.setattr(
        rerank, "_rank", lambda q, c, k, url: [dict(c[1], rerankScore=0.5)]
    )

    ranked, applied = rerank.rerank_candidates("q", _candidates(), 1)

    assert applied is True
    assert [candidate["content"] for candidate in ranked] == ["beta"]


def test_rerank_candidates_none_is_a_passthrough(monkeypatch) -> None:
    monkeypatch.setenv("RERANK_MODE", "none")

    ranked, applied = rerank.rerank_candidates("q", _candidates(), 1)

    assert applied is False
    assert ranked == [{"content": "alpha"}]

"""Bedrock chat helper (Converse API): request shape + message normalization."""

from __future__ import annotations

import pytest

from core import bedrock_chat


class _FakeClient:
    def __init__(self, text: str = "hi", stop_reason: str = "end_turn") -> None:
        self.text = text
        self.stop_reason = stop_reason
        self.calls: list[dict] = []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "output": {"message": {"role": "assistant", "content": [{"text": self.text}]}},
            "stopReason": self.stop_reason,
            "usage": {"inputTokens": 3, "outputTokens": 1, "totalTokens": 4},
        }


def test_chat_result_maps_converse_response(monkeypatch) -> None:
    client = _FakeClient(text="hello", stop_reason="end_turn")
    monkeypatch.setattr(bedrock_chat, "_client", lambda: client)
    monkeypatch.setattr(bedrock_chat, "_throttle_model", lambda _m: None)

    result = bedrock_chat.chat_result("SYS", "USER", model="zai.glm-4.7-flash")

    assert result["text"] == "hello"
    assert result["stopReason"] == "end_turn"
    assert result["usage"]["inputTokens"] == 3
    call = client.calls[0]
    assert call["modelId"] == "zai.glm-4.7-flash"
    # The system prompt carries a Bedrock cache point (prompt caching).
    assert call["system"][0] == {"text": "SYS"}
    assert call["system"][-1]["cachePoint"]["type"] == "default"
    assert call["messages"] == [{"role": "user", "content": [{"text": "USER"}]}]
    assert call["inferenceConfig"]["temperature"] == 0.2


def test_chat_raises_on_empty_text(monkeypatch) -> None:
    monkeypatch.setattr(bedrock_chat, "_client", lambda: _FakeClient(text="   "))
    monkeypatch.setattr(bedrock_chat, "_throttle_model", lambda _m: None)

    with pytest.raises(bedrock_chat.BedrockChatError):
        bedrock_chat.chat("SYS", "USER")


def test_normalize_messages_merges_and_starts_with_user() -> None:
    turns = bedrock_chat._normalize_messages(
        [
            {"role": "system", "content": "ignored"},
            {"role": "assistant", "content": "a"},
            {"role": "assistant", "content": "b"},
            {"role": "user", "content": "c"},
        ]
    )
    assert turns[0]["role"] == "user"  # a user turn is synthesized
    assert turns[1] == {"role": "assistant", "content": [{"text": "a\n\nb"}]}
    assert turns[2] == {"role": "user", "content": [{"text": "c"}]}


def test_normalize_messages_requires_a_turn() -> None:
    with pytest.raises(bedrock_chat.BedrockChatError):
        bedrock_chat._normalize_messages([{"role": "system", "content": "x"}])

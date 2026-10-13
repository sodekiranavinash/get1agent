"""AI Assistant persistence: conversations, transcripts, feedback, traces, eval runs.

Runs against the moto-backed DynamoDB table and S3 bucket from ``conftest``, so
the repository is exercised with the real boto3 calls the services make (no
hand-rolled doubles). Also covers the AI Assistant settings item, whose coercion rules are
the difference between a working admin toggle and a broken widget.
"""

from __future__ import annotations

import json
from decimal import Decimal

import boto3
import pytest

from data.keys import (
    AI_ASSISTANT_CHAT_PREFIX,
    AI_ASSISTANT_EVAL_RUN_PREFIX,
    AI_ASSISTANT_FEEDBACK_PREFIX,
    AI_ASSISTANT_TRACE_PREFIX,
    ai_assistant_chat_sk,
    ai_assistant_feedback_sk,
    ai_assistant_trace_sk,
    user_pk,
)
from data.repositories import ai_assistant, ai_assistant_settings

USER = "u_7k3f9qz2mpx8n4rq"
OTHER = "u_zzzzzzzzzzzzzzzz"


@pytest.fixture(autouse=True)
def _bucket():
    """The AI Assistant transcript and trace trees need the S3 bucket to exist."""
    boto3.client("s3", region_name="us-east-1").create_bucket(
        Bucket="get1agent-test-bucket"
    )
    yield


# --- key builders -------------------------------------------------------------


def test_ai_assistant_keys_use_avi_specific_prefixes():
    """AI Assistant must never write into an agent prefix (CHAT#/TRACE#/FEEDBACK#)."""
    assert ai_assistant_chat_sk("c1") == f"{AI_ASSISTANT_CHAT_PREFIX}c1"
    assert ai_assistant_feedback_sk("r1") == f"{AI_ASSISTANT_FEEDBACK_PREFIX}r1"
    assert ai_assistant_trace_sk("t1") == f"{AI_ASSISTANT_TRACE_PREFIX}t1"
    assert ai_assistant_chat_sk("c1").startswith("AICHAT#")
    assert not ai_assistant_chat_sk("c1").startswith("CHAT#")
    assert not ai_assistant_feedback_sk("r1").startswith("FEEDBACK#")


def test_new_ids_are_unique_and_sortable():
    ids = [ai_assistant.new_conversation_id() for _ in range(20)]
    assert len(set(ids)) == 20
    assert all(value.startswith("avi_") for value in ids)
    # Fixed-width epoch prefix => lexical order is chronological order.
    assert sorted(ids) == ids or len({value.split("_")[1] for value in ids}) <= 2


def test_cursor_round_trip():
    key = {"pk": "USER#u1", "sk": "AICHAT#c1"}
    assert ai_assistant.decode_cursor(ai_assistant.encode_cursor(key)) == key
    assert ai_assistant.encode_cursor(None) is None
    assert ai_assistant.decode_cursor("not-base64!!") is None
    assert ai_assistant.decode_cursor(None) is None


# --- conversations ------------------------------------------------------------


def test_conversation_lifecycle():
    created = ai_assistant.create_conversation(
        USER, title="", entry_route="/knowledge-bases", model="m1"
    )
    conversation_id = created["conversationId"]
    assert created["entity"] == "ai-assistant-conversation"
    assert created["entryRoute"] == "/knowledge-bases"
    assert created["turnCount"] == 0

    fetched = ai_assistant.get_conversation(USER, conversation_id)
    assert fetched is not None
    assert fetched["conversationId"] == conversation_id

    # Owner-scoped: another user cannot read it.
    assert ai_assistant.get_conversation(OTHER, conversation_id) is None

    listed, _ = ai_assistant.list_conversations(USER)
    assert [item["conversationId"] for item in listed] == [conversation_id]

    ai_assistant.delete_conversation(USER, conversation_id)
    assert ai_assistant.get_conversation(USER, conversation_id) is None


def test_transcript_appends_and_updates_metadata():
    created = ai_assistant.create_conversation(USER)
    conversation_id = created["conversationId"]

    ai_assistant.append_turn(
        USER,
        conversation_id,
        {
            "runId": "avirun_1",
            "question": "How many knowledge bases can I create?",
            "answer": "Ten by default.",
            "intent": "limits_billing",
        },
    )
    ai_assistant.append_turn(
        USER,
        conversation_id,
        {"runId": "avirun_2", "question": "And files?", "answer": "Twenty-five each."},
    )

    transcript = ai_assistant.get_transcript(USER, conversation_id)
    assert [turn["runId"] for turn in transcript["turns"]] == ["avirun_1", "avirun_2"]

    # The metadata item is updated in place and the byUser sort key is refreshed.
    item = ai_assistant.get_conversation(USER, conversation_id)
    assert item["turnCount"] == 2
    assert item["messageCount"] == 4
    assert item["title"] == "How many knowledge bases can I create?"
    assert item["lastIntent"] == "limits_billing"
    assert item["gsi2sk"].startswith(AI_ASSISTANT_CHAT_PREFIX)

    # Recency ordering comes from the refreshed GSI2 sort key.
    listed, _ = ai_assistant.list_conversations(USER)
    assert [entry["conversationId"] for entry in listed] == [conversation_id]


def test_signing_in_starts_a_separate_conversation():
    """A guest thread is never stored, so a signed-in thread starts empty."""
    first = ai_assistant.create_conversation(USER)
    second = ai_assistant.create_conversation(USER)
    assert first["conversationId"] != second["conversationId"]
    assert ai_assistant.get_transcript(USER, second["conversationId"]) == {"turns": []}


# --- feedback -----------------------------------------------------------------


def _feedback(run_id: str, **overrides):
    payload = dict(
        value="down",
        comment="The link 404s",
        categories=["Inaccurate"],
        conversation_id="avi_1",
        message_id="m_1",
        question="Where do I change the model?",
        answer_preview="Open Settings.",
        sources=[{"title": "Agent builder", "route": "/agent-builder"}],
        route_clicked="/agent-builder",
        model="nvidia.nemotron-nano-3-30b",
        classifier_kind="platform",
        intent="find_feature",
        latency_ms=812,
        tokens_in=120,
        tokens_out=310,
        cost_micro_usd=420,
        trace_id="trace_1",
    )
    payload.update(overrides)
    return ai_assistant.upsert_feedback(USER, run_id, **payload)


def test_feedback_carries_the_rich_fields():
    item = _feedback("avirun_9")
    assert item["sk"] == f"{AI_ASSISTANT_FEEDBACK_PREFIX}avirun_9"
    assert item["value"] == "down"
    assert item["question"] == "Where do I change the model?"
    assert item["sources"][0]["route"] == "/agent-builder"
    assert item["classifierKind"] == "platform"
    assert item["latencyMs"] == 812
    assert item["costMicroUsd"] == 420
    # created/updated are both stamped so the admin table can sort either way.
    assert item["createdAt"] == item["updatedAt"]


def test_feedback_upsert_is_idempotent_and_filterable():
    _feedback("avirun_a", value="up")
    _feedback("avirun_b", value="down")
    _feedback("avirun_c", value="down")

    everything, _ = ai_assistant.list_feedback(USER)
    assert len(everything) == 3

    downs, _ = ai_assistant.list_feedback(USER, value="down")
    assert {item["runId"] for item in downs} == {"avirun_b", "avirun_c"}

    # Same run id updates in place rather than creating a second item.
    _feedback("avirun_a", value="down", comment="changed my mind")
    refetched = ai_assistant.get_feedback(USER, "avirun_a")
    assert refetched["value"] == "down"
    assert refetched["comment"] == "changed my mind"

    ai_assistant.delete_feedback(USER, "avirun_a")
    assert ai_assistant.get_feedback(USER, "avirun_a") is None


def test_feedback_rejects_an_unknown_rating():
    with pytest.raises(ValueError):
        ai_assistant.upsert_feedback(USER, "avirun_x", value="sideways")


# --- traces -------------------------------------------------------------------


def test_trace_writes_tree_to_s3_and_a_small_index_item():
    ai_assistant.put_trace(
        USER,
        "trace_abc",
        tree={"spans": [{"name": "classifier", "ms": 301}]},
        summary={
            "question": "How do I add an MCP server?",
            "model": "nvidia.nemotron-nano-3-30b",
            "classifierKind": "platform",
            "intent": "how_to",
            "status": "ok",
            "latencyMs": 1204,
            "ttftMs": 221,
            "tokensIn": 900,
            "tokensOut": 260,
            "costMicroUsd": 1100,
            "sourceCount": 3,
            "spanCount": 7,
            "conversationId": "avi_1",
            "runId": "avirun_1",
            "entryRoute": "/tools",
        },
    )

    item = ai_assistant.get_trace(USER, "trace_abc")
    assert item is not None
    assert item["entity"] == "ai-assistant-trace"
    assert item["traceId"] == "trace_abc"
    assert item["ttftMs"] == 221
    assert item["spanCount"] == 7
    # The index item is small; the tree is hydrated from S3 on read, and the
    # trace id is stamped onto the tree so a raw S3 object is self-describing.
    assert item["s3Key"].endswith("trace_abc.json")
    assert item["tree"] == {
        "spans": [{"name": "classifier", "ms": 301}],
        "traceId": "trace_abc",
    }

    listed, _ = ai_assistant.list_traces(USER)
    assert [entry["traceId"] for entry in listed] == ["trace_abc"]

    # Owner-scoped.
    assert ai_assistant.get_trace(OTHER, "trace_abc") is None

    ai_assistant.delete_trace(USER, "trace_abc")
    assert ai_assistant.get_trace(USER, "trace_abc") is None


def test_trace_index_item_stays_small():
    """A long answer must not be stored on the index item (only a preview)."""
    ai_assistant.put_trace(
        USER,
        "trace_long",
        tree={"spans": []},
        summary={"question": "q" * 5_000, "answerPreview": "a" * 5_000},
    )
    item = ai_assistant.get_trace(USER, "trace_long")
    assert len(item["question"]) <= 1_000


# --- evaluation runs ----------------------------------------------------------


def test_eval_runs_are_stored_and_listed_newest_first():
    # DynamoDB has no float type: the worker hands us native JSON (floats) and
    # the repository must land them as Decimal or the write fails.
    ai_assistant.put_eval_run(USER, "run_1", {"dataset": "ai-assistant-eval", "score": 0.91})
    ai_assistant.put_eval_run(USER, "run_2", {"dataset": "ai-assistant-eval", "score": 0.95})

    fetched = ai_assistant.get_eval_run(USER, "run_2")
    assert fetched["score"] == Decimal("0.95")
    assert isinstance(fetched["score"], Decimal)
    assert fetched["sk"] == f"{AI_ASSISTANT_EVAL_RUN_PREFIX}run_2"

    listed, _ = ai_assistant.list_eval_runs(USER)
    assert [item["runId"] for item in listed] == ["run_2", "run_1"]


# --- settings -----------------------------------------------------------------


def test_settings_defaults_are_model_and_limit_aware():
    settings = ai_assistant_settings.defaults()
    assert settings["enabled"] is True
    assert settings["guestEnabled"] is True
    # Defaults are the measured winners from the design doc.
    assert settings["model"] == "nvidia.nemotron-nano-3-30b"
    assert settings["classifierModel"] == "zai.glm-4.7-flash"
    assert settings["reasoningModel"] == "deepseek.v3.2"
    assert settings["judgeModel"] == "amazon.nova-2-lite-v1:0"
    assert settings["maxAgentSteps"] == 6
    assert settings["guestPerHour"] < settings["userPerHour"]


def test_settings_round_trip_and_coercion():
    ai_assistant_settings.invalidate_cache()
    assert ai_assistant_settings.is_enabled() is True

    updated = ai_assistant_settings.update_settings(
        {"model": "qwen.qwen3-next-80b-a3b", "guestPerHour": "9", "enabled": False},
        updated_by="admin@example.com",
    )
    assert updated["model"] == "qwen.qwen3-next-80b-a3b"
    assert updated["guestPerHour"] == 9
    assert updated["enabled"] is False

    ai_assistant_settings.invalidate_cache()
    assert ai_assistant_settings.is_enabled() is False
    assert ai_assistant_settings.guest_enabled() is False
    assert ai_assistant_settings.get_settings()["model"] == "qwen.qwen3-next-80b-a3b"

    snapshot = ai_assistant_settings.snapshot()
    assert snapshot["updatedBy"] == "admin@example.com"
    assert snapshot["settings"]["model"] == "qwen.qwen3-next-80b-a3b"
    # The catalogue the admin page renders is exposed alongside.
    assert any(choice["id"] == "zai.glm-4.7-flash" for choice in snapshot["modelChoices"])


def test_settings_clamp_and_reject_junk():
    ai_assistant_settings.invalidate_cache()
    ai_assistant_settings.update_settings({"maxAgentSteps": 999, "guestPerDay": -5})
    settings = ai_assistant_settings.get_settings(use_cache=False)
    assert settings["maxAgentSteps"] == 20
    assert settings["guestPerDay"] == 0

    with pytest.raises(ValueError):
        ai_assistant_settings.update_settings({"notAThing": 1})


def test_guest_toggle_requires_the_master_switch():
    ai_assistant_settings.invalidate_cache()
    ai_assistant_settings.update_settings({"enabled": False, "guestEnabled": True})
    assert ai_assistant_settings.guest_enabled() is False


def test_kill_switch_survives_a_broken_settings_read(monkeypatch):
    """A DynamoDB failure must fall back to defaults, never raise."""

    class Boom:
        def get_item(self, **_kwargs):
            raise RuntimeError("dynamodb down")

    monkeypatch.setattr(ai_assistant_settings, "table", lambda: Boom())
    ai_assistant_settings.invalidate_cache()
    assert ai_assistant_settings.get_settings(use_cache=False) == ai_assistant_settings.defaults()
    assert ai_assistant_settings.is_enabled() is True

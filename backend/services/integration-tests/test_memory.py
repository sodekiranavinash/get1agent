"""AgentCore Memory data-plane behaviour, against a stubbed client (no AWS).

The namespace semantics here are load-bearing and **silent** when wrong:
``namespace`` is an exact match and ``namespacePath`` is the subtree, while every
record lives one level below the user root. An exact match on the root therefore
returns nothing at all — the Memory page looks empty, the DPDP export omits
memory, and an account deletion leaves every long-term record behind.

Writes are pinned too: the direct record write is what makes "remember this"
recallable in the same conversation, and ``clientToken`` is the only idempotency
key (``requestIdentifier`` is not one — reusing it creates a second record).
"""

from __future__ import annotations

import pytest

from core import memory


class _StubClient:
    """Records every API call and replays canned responses."""

    def __init__(self, **responses: object) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._responses = responses

    def __getattr__(self, name: str):
        def call(**kwargs: object):
            self.calls.append((name, kwargs))
            response = self._responses.get(name, {})
            return response(kwargs) if callable(response) else response

        return call

    def kwargs_for(self, name: str) -> list[dict]:
        return [kwargs for called, kwargs in self.calls if called == name]


@pytest.fixture
def agentcore(monkeypatch: pytest.MonkeyPatch):
    """Point the module at a stub client and a configured managed memory."""

    def install(**responses: object) -> _StubClient:
        stub = _StubClient(**responses)
        monkeypatch.setattr(memory, "is_agentcore", lambda: True)
        monkeypatch.setattr(memory, "memory_id", lambda: "mem-123")
        monkeypatch.setattr(memory, "_data_client", lambda: stub)
        return stub

    return install


def _client_error(code: str, message: str, operation: str) -> Exception:
    """A botocore error shaped the way the retry/erase guards inspect it."""
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


# --- namespaces --------------------------------------------------------------


def test_record_namespace_files_by_kind() -> None:
    assert memory.record_namespace("u_1") == "/users/u_1/preferences/"
    assert memory.record_namespace("u_1", "fact") == "/users/u_1/facts/"
    # An unknown kind files as a preference rather than failing the run.
    assert memory.record_namespace("u_1", "nonsense") == "/users/u_1/preferences/"


# --- reads use the subtree ---------------------------------------------------


def test_list_uses_the_subtree_not_an_exact_match(agentcore) -> None:
    stub = agentcore(list_memory_records={"memoryRecordSummaries": []})

    memory._agentcore_list("u_1", cursor=None, limit=10, query=None)

    (kwargs,) = stub.kwargs_for("list_memory_records")
    assert kwargs["namespacePath"] == "/users/u_1/"
    assert "namespace" not in kwargs


def test_search_uses_the_subtree(agentcore) -> None:
    stub = agentcore(retrieve_memory_records={"memoryRecordSummaries": []})

    memory._agentcore_list("u_1", cursor=None, limit=5, query="favourite colour")

    (kwargs,) = stub.kwargs_for("retrieve_memory_records")
    assert kwargs["namespacePath"] == "/users/u_1/"
    assert "namespace" not in kwargs
    assert kwargs["searchCriteria"]["searchQuery"] == "favourite colour"


def test_list_shapes_records_for_the_page(agentcore) -> None:
    agentcore(
        list_memory_records={
            "memoryRecordSummaries": [
                {
                    "memoryRecordId": "mem-1",
                    "content": {"text": "The user likes red."},
                    "namespaces": ["/users/u_1/preferences/"],
                }
            ]
        }
    )

    result = memory._agentcore_list("u_1", cursor=None, limit=10, query=None)

    assert [record["text"] for record in result["records"]] == ["The user likes red."]


# --- erase covers the subtree ------------------------------------------------


def test_erase_uses_the_subtree_and_deletes_the_records_own_namespace(agentcore) -> None:
    stub = agentcore(
        list_memory_records={
            "memoryRecordSummaries": [
                {
                    "memoryRecordId": "mem-1",
                    "namespaces": ["/users/u_1/facts/"],
                }
            ]
        },
        list_sessions={"sessionSummaries": []},
    )

    erased = memory._agentcore_erase_all("u_1")

    (list_kwargs,) = stub.kwargs_for("list_memory_records")
    assert list_kwargs["namespacePath"] == "/users/u_1/"
    assert "namespace" not in list_kwargs

    (delete_kwargs,) = stub.kwargs_for("batch_delete_memory_records")
    assert delete_kwargs["records"] == [
        {"memoryRecordId": "mem-1", "namespace": "/users/u_1/facts/"}
    ]
    assert erased["records"] == 1


# --- writes ------------------------------------------------------------------


def test_save_record_writes_a_consolidated_record_directly(agentcore) -> None:
    stub = agentcore(
        batch_create_memory_records={
            "successfulRecords": [{"memoryRecordId": "mem-9", "status": "SUCCEEDED"}]
        }
    )

    saved = memory.save_record("u_1", "  The user's favourite colour is red.  ")

    (kwargs,) = stub.kwargs_for("batch_create_memory_records")
    assert kwargs["memoryId"] == "mem-123"
    (record,) = kwargs["records"]
    assert record["namespaces"] == ["/users/u_1/preferences/"]
    assert record["content"]["text"] == "The user's favourite colour is red."
    assert record["timestamp"] is not None
    # The idempotency token is also the request identifier.
    assert kwargs["clientToken"] == record["requestIdentifier"]
    assert saved == {
        "id": "mem-9",
        "namespace": "/users/u_1/preferences/",
        "text": "The user's favourite colour is red.",
        "failed": [],
    }


def test_save_record_files_a_fact_under_facts(agentcore) -> None:
    stub = agentcore(batch_create_memory_records={"successfulRecords": []})

    memory.save_record("u_1", "The user works at Acme.", kind="fact")

    (kwargs,) = stub.kwargs_for("batch_create_memory_records")
    assert kwargs["records"][0]["namespaces"] == ["/users/u_1/facts/"]


def test_save_record_is_idempotent_for_a_retry(agentcore) -> None:
    stub = agentcore(
        batch_create_memory_records={
            "successfulRecords": [{"memoryRecordId": "mem-9", "status": "SUCCEEDED"}]
        }
    )

    memory.save_record("u_1", "The user likes red.")
    memory.save_record("u_1", "The user likes red.")

    first, second = stub.kwargs_for("batch_create_memory_records")
    assert first["clientToken"] == second["clientToken"]


def test_save_record_token_distinguishes_different_text(agentcore) -> None:
    stub = agentcore(batch_create_memory_records={"successfulRecords": []})

    memory.save_record("u_1", "The user likes red.")
    memory.save_record("u_1", "The user likes blue.")

    first, second = stub.kwargs_for("batch_create_memory_records")
    assert first["clientToken"] != second["clientToken"]


def test_save_record_caps_the_text(agentcore) -> None:
    stub = agentcore(batch_create_memory_records={"successfulRecords": []})

    memory.save_record("u_1", "x" * (memory.MAX_RECORD_CHARS + 500))

    (kwargs,) = stub.kwargs_for("batch_create_memory_records")
    text = kwargs["records"][0]["content"]["text"]
    assert len(text) == memory.MAX_RECORD_CHARS


def test_save_record_names_the_failed_records(agentcore) -> None:
    agentcore(batch_create_memory_records={"failedRecords": [{"requestIdentifier": "x"}]})

    saved = memory.save_record("u_1", "The user likes red.")

    assert saved["failed"] == [{"requestIdentifier": "x"}]


def test_save_record_rejects_an_empty_body(agentcore) -> None:
    agentcore(batch_create_memory_records={"successfulRecords": []})

    with pytest.raises(ValueError):
        memory.save_record("u_1", "   ")


def test_save_record_needs_the_managed_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    # The local Dynamo backend owns its own write path.
    monkeypatch.setenv("AGENT_MEMORY_BACKEND", "dynamo")
    monkeypatch.delenv("AGENTCORE_MEMORY_ID", raising=False)

    with pytest.raises(RuntimeError):
        memory.save_record("u_1", "The user likes red.")


# --- restatements are not written twice --------------------------------------
#
# Two writes of one fact are the expected case, not a bug: the model calls
# ``add_memory`` and the store's extraction derives the same fact from the turn
# independently. ``clientToken`` only deduplicates a byte-identical replay, so a
# near duplicate has to be spotted *before* writing — otherwise every copy lands
# in the injection window and crowds out the memories that matter.


def test_save_record_leaves_an_exact_restatement_alone(agentcore) -> None:
    stub = agentcore(
        retrieve_memory_records={
            "memoryRecordSummaries": [
                {
                    "memoryRecordId": "mem-1",
                    "content": {"text": "The user's favourite colour is red."},
                }
            ]
        },
        batch_create_memory_records={"successfulRecords": [{"memoryRecordId": "mem-9"}]},
    )

    # Same sentence, different case and punctuation: still the same memory.
    saved = memory.save_record("u_1", "the user's FAVOURITE colour is red")

    assert stub.kwargs_for("batch_create_memory_records") == []
    assert saved["duplicate"] is True
    assert saved["id"] == "mem-1"
    assert saved["matched"] == "The user's favourite colour is red."
    assert saved["failed"] == []


def test_save_record_skips_a_high_scoring_match(agentcore) -> None:
    stub = agentcore(
        retrieve_memory_records={
            "memoryRecordSummaries": [
                {
                    "memoryRecordId": "mem-1",
                    "content": {"text": "The user's favourite colours are red and white."},
                    "score": 0.97,
                }
            ]
        },
        batch_create_memory_records={"successfulRecords": []},
    )

    saved = memory.save_record("u_1", "The user likes red and white best.")

    assert stub.kwargs_for("batch_create_memory_records") == []
    assert saved["duplicate"] is True


def test_save_record_writes_when_the_closest_match_is_weak(agentcore) -> None:
    stub = agentcore(
        retrieve_memory_records={
            "memoryRecordSummaries": [
                {
                    "memoryRecordId": "mem-1",
                    "content": {"text": "The user works at Acme."},
                    "score": 0.4,
                }
            ]
        },
        batch_create_memory_records={"successfulRecords": [{"memoryRecordId": "mem-9"}]},
    )

    saved = memory.save_record("u_1", "The user lives in Mumbai.")

    assert len(stub.kwargs_for("batch_create_memory_records")) == 1
    assert "duplicate" not in saved


def test_save_record_writes_when_the_lookup_fails(agentcore) -> None:
    def refuse(_kwargs: dict) -> dict:
        raise _client_error("AccessDeniedException", "not authorized", "RetrieveMemoryRecords")

    stub = agentcore(
        retrieve_memory_records=refuse,
        batch_create_memory_records={"successfulRecords": [{"memoryRecordId": "mem-9"}]},
    )

    saved = memory.save_record("u_1", "The user likes red.")

    # Losing a memory is worse than filing it twice, so the write proceeds.
    assert len(stub.kwargs_for("batch_create_memory_records")) == 1
    assert "duplicate" not in saved


def test_save_record_dedupe_can_be_turned_off(agentcore) -> None:
    stub = agentcore(
        retrieve_memory_records={
            "memoryRecordSummaries": [
                {
                    "memoryRecordId": "mem-1",
                    "content": {"text": "The user likes red."},
                    "score": 0.99,
                }
            ]
        },
        batch_create_memory_records={"successfulRecords": []},
    )

    memory.save_record("u_1", "The user likes red.", dedupe=False)

    assert stub.kwargs_for("retrieve_memory_records") == []
    assert len(stub.kwargs_for("batch_create_memory_records")) == 1


def test_normalisation_ignores_case_and_punctuation() -> None:
    assert (
        memory._normalized("The user's favourite colour is RED.")
        == "the user s favourite colour is red"
    )
    assert memory._normalized("   ") == ""


def test_find_duplicate_returns_none_without_text() -> None:
    assert memory.find_duplicate("u_1", "   ") is None


# --- replaying a write -------------------------------------------------------
#
# ``clientToken`` is the idempotency key, so the service rejects a second request
# carrying the same token with a *different* body. A legitimate retry always
# differs — the timestamp is re-read — so the refusal means "this exact memory was
# already written": a no-op, not a failure the user should hear about.


def test_save_record_treats_a_replayed_write_as_already_saved(agentcore) -> None:
    def refuse(_kwargs: dict) -> dict:
        raise _client_error(
            "ValidationException",
            "Parameter hash does not match existing request",
            "BatchCreateMemoryRecords",
        )

    agentcore(batch_create_memory_records=refuse)

    saved = memory.save_record("u_1", "  The user likes red.  ")

    assert saved == {
        "id": "",
        "namespace": "/users/u_1/preferences/",
        "text": "The user likes red.",
        "failed": [],
        "duplicate": True,
    }


def test_save_record_reraises_anything_else(agentcore) -> None:
    def refuse(_kwargs: dict) -> dict:
        raise _client_error("AccessDeniedException", "not authorized", "BatchCreateMemoryRecords")

    agentcore(batch_create_memory_records=refuse)

    with pytest.raises(Exception) as caught:
        memory.save_record("u_1", "The user likes red.")

    assert "AccessDeniedException" in str(caught.value)


def test_the_duplicate_guard_needs_both_the_code_and_the_message() -> None:
    assert memory._is_duplicate_write(
        _client_error(
            "ValidationException",
            "Parameter hash does not match existing request",
            "BatchCreateMemoryRecords",
        )
    )
    # Same code, different reason — must not be swallowed.
    assert not memory._is_duplicate_write(
        _client_error("ValidationException", "Some other failure", "BatchCreateMemoryRecords")
    )
    assert not memory._is_duplicate_write(
        _client_error(
            "AccessDeniedException", "Parameter hash does not match existing request", "X"
        )
    )


# --- erasing an actor that has no events -------------------------------------


def test_erase_tolerates_an_actor_with_no_events(agentcore) -> None:
    # A user whose memory was only ever written directly has no short-term events,
    # and ``list_sessions`` raises rather than returning an empty page. That must
    # not fail the erasure *after* the records were already deleted.
    def refuse(_kwargs: dict) -> dict:
        raise _client_error("ResourceNotFoundException", "Actor not found", "ListSessions")

    agentcore(
        list_memory_records={
            "memoryRecordSummaries": [
                {"memoryRecordId": "mem-1", "namespaces": ["/users/u_1/facts/"]}
            ]
        },
        list_sessions=refuse,
    )

    assert memory._agentcore_erase_all("u_1") == {"records": 1, "events": 0}


def test_erase_tolerates_a_vanished_session(agentcore) -> None:
    def refuse(_kwargs: dict) -> dict:
        raise _client_error("ResourceNotFoundException", "Session not found", "ListEvents")

    agentcore(
        list_memory_records={"memoryRecordSummaries": []},
        list_sessions={"sessionSummaries": [{"sessionId": "s-1"}]},
        list_events=refuse,
    )

    assert memory._agentcore_erase_all("u_1") == {"records": 0, "events": 0}


def test_erase_still_reports_real_failures(agentcore) -> None:
    def refuse(_kwargs: dict) -> dict:
        raise _client_error("AccessDeniedException", "not authorized", "ListSessions")

    agentcore(list_memory_records={"memoryRecordSummaries": []}, list_sessions=refuse)

    with pytest.raises(Exception) as caught:
        memory._agentcore_erase_all("u_1")

    assert "AccessDeniedException" in str(caught.value)

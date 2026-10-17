"""AgentCore Memory data-plane behaviour, against a stubbed client (no AWS).

The namespace semantics here are load-bearing and **silent** when wrong:
``namespace`` is an exact match and ``namespacePath`` is the subtree, while every
record lives one level below the user root. An exact match on the root therefore
returns nothing at all — the Memory page looks empty, the DPDP export omits
memory, and an account deletion leaves every long-term record behind.
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
    """A botocore error shaped the way the erase guard inspects it."""
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": message}}, operation)


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

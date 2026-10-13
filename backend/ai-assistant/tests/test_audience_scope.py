"""AI Assistant's audience boundary: admin content must never reach a normal caller.

Two independent mechanisms guard it, and both were broken:

* retrieval filters by the **document's** audience, and the audience is part of the
  search cache key — but ``run_turn``'s up-front search never passed one, so an
  admin's passage list (which legitimately includes admin docs) could be cached
  under the key a signed-in user's identical question reads;
* a citation's route is validated against the deep-link allow-list — but
  ``_sources_from_payload`` hard-coded ``allow_admin=True``, so any tool payload
  carrying an admin path would have been linked to a normal user.

No AWS calls: the search is replaced with a recorder and the agent build fails
harmlessly (the harness is not installed for these tests).
"""

from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parent / "packages"
for entry in (str(SERVICE_ROOT), str(PACKAGES)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from src import agent, retrieval  # noqa: E402
from src.frames import FrameWriter  # noqa: E402


class _PlatformVerdict:
    """A platform question, so the turn reaches retrieval instead of a greeting."""

    kind = "platform"
    intent = "overview"
    confidence = 1.0
    stage = "test"
    examples: tuple[str, ...] = ()
    is_platform = True
    is_smalltalk = False

    def to_frame(self) -> dict:
        return {
            "type": "ai-assistant.intent",
            "kind": self.kind,
            "intent": self.intent,
            "confidence": self.confidence,
            "stage": self.stage,
            "examples": [],
        }


class _SearchRecorder:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, query: str, **kwargs):
        self.calls.append({"query": query, **kwargs})
        return [], {"stage": "test", "count": 0}


def _pull(request: agent.TurnRequest, frames: int = 6) -> list[dict]:
    """Drive a turn far enough for retrieval to run, then close it.

    The agent harness is deliberately absent in this environment, so the turn ends
    in a ``run.error`` frame once retrieval has happened — which is all this test
    needs.
    """

    async def drive() -> list[dict]:
        out: list[dict] = []
        agen = agent.run_turn(request, verdict=_PlatformVerdict())
        try:
            async for frame in agen:
                out.append(frame)
                if len(out) >= frames:
                    break
        finally:
            await agen.aclose()
        return out

    return asyncio.run(drive())


class UpfrontRetrievalAudienceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.recorder = _SearchRecorder()
        self._original = retrieval.search
        retrieval.search = self.recorder  # type: ignore[assignment]

    def tearDown(self) -> None:
        retrieval.search = self._original  # type: ignore[assignment]

    def test_a_normal_turn_scopes_the_search_to_the_user_audience(self) -> None:
        _pull(agent.TurnRequest(question="what can I do here?", run_id="r1"))
        self.assertEqual(len(self.recorder.calls), 1)
        call = self.recorder.calls[0]
        self.assertEqual(call["audience"], "user")
        self.assertFalse(call["allow_admin"])

    def test_an_admin_turn_scopes_the_search_to_the_admin_audience(self) -> None:
        _pull(
            agent.TurnRequest(
                question="how do I manage users?", run_id="r2", allow_admin=True
            )
        )
        self.assertEqual(len(self.recorder.calls), 1)
        call = self.recorder.calls[0]
        # The audience must differ, because it is what separates the cache keys.
        self.assertEqual(call["audience"], "admin")
        self.assertTrue(call["allow_admin"])

    def test_the_cache_key_separates_the_two_audiences(self) -> None:
        user_key = retrieval._cache_key("same question", 6, "user")
        admin_key = retrieval._cache_key("same question", 6, "admin")
        self.assertNotEqual(user_key, admin_key)


class CitationRouteGateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.writer = FrameWriter(run_id="r", model="m")

    def test_a_normal_turn_never_links_an_admin_route(self) -> None:
        payload = [
            {"title": "Users", "route": "/admin/users", "content": "x"},
            {"title": "Docs", "route": "/docs", "content": "y"},
        ]
        sources = agent._sources_from_payload(payload, self.writer, allow_admin=False)
        by_title = {source["title"]: source for source in sources}
        self.assertEqual(by_title["Users"]["route"], "")
        self.assertEqual(by_title["Users"]["url"], "/docs")
        self.assertEqual(by_title["Docs"]["route"], "/docs")

    def test_a_non_route_is_replaced_rather_than_linked(self) -> None:
        sources = agent._sources_from_payload(
            [{"title": "Nope", "route": "not-a-route"}], self.writer, allow_admin=False
        )
        self.assertEqual(sources[0]["route"], "")
        self.assertEqual(sources[0]["url"], "/docs")

    def test_numbering_stays_run_global(self) -> None:
        self.writer.sources.append({"index": 1, "title": "earlier"})
        sources = agent._sources_from_payload(
            [{"title": "a"}, {"title": "b"}], self.writer, allow_admin=False
        )
        self.assertEqual([source["index"] for source in sources], [2, 3])


if __name__ == "__main__":
    unittest.main()

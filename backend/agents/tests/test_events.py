"""Unit tests for the agentflow event normalizer."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentflow import events  # noqa: E402


class NormalizeTests(unittest.TestCase):
    def test_text_delta(self) -> None:
        self.assertEqual(
            events.normalize({"data": "hello"}), {"type": "text", "data": "hello"}
        )

    def test_reasoning_delta_is_dropped(self) -> None:
        self.assertIsNone(events.normalize({"reasoningText": "thinking"}))
        self.assertEqual(events.normalize_many({"reasoningText": "thinking"}), [])

    def test_tool_start(self) -> None:
        event = events.normalize(
            {
                "current_tool_use": {
                    "name": "web_search",
                    "toolUseId": "t1",
                    "input": {"query": "x"},
                }
            }
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["type"], "tool.start")
        self.assertEqual(event["name"], "web_search")

    def test_tool_result_message(self) -> None:
        event = events.normalize_many(
            {
                "message": {
                    "role": "user",
                    "content": [
                        {
                            "toolResult": {
                                "toolUseId": "t1",
                                "status": "success",
                                "content": [{"text": "found 3 results"}],
                            }
                        }
                    ],
                }
            }
        )
        self.assertEqual(
            event,
            [
                {
                    "type": "tool.result",
                    "toolUseId": "t1",
                    "status": "success",
                    "data": "found 3 results",
                    "sources": [],
                }
            ],
        )

    def test_tool_result_message_expands_multiple(self) -> None:
        event = events.normalize_many(
            {
                "message": {
                    "content": [
                        {"toolResult": {"toolUseId": "a", "status": "success", "content": [{"text": "1"}]}},
                        {"toolResult": {"toolUseId": "b", "status": "error", "content": [{"text": "2"}]}},
                    ]
                }
            }
        )
        self.assertEqual([item["toolUseId"] for item in event], ["a", "b"])
        self.assertEqual([item["status"] for item in event], ["success", "error"])

    def test_tool_result_event_direct(self) -> None:
        event = events.normalize_many(
            {
                "type": "tool_result",
                "tool_result": {
                    "toolUseId": "t1",
                    "status": "success",
                    "content": [{"json": {"ok": True}}],
                },
            }
        )
        self.assertEqual(event[0]["type"], "tool.result")
        self.assertEqual(event[0]["toolUseId"], "t1")
        self.assertIn('"ok": true', event[0]["data"])

    def test_tool_result_extracts_knowledge_sources(self) -> None:
        payload = {
            "sources": [
                {
                    "index": 4,
                    "fileName": "resume.pdf",
                    "kbName": "my-career",
                    "page": 2,
                    "sourceUrl": "/v1/knowledge-bases/k1/documents/d1/file#page=2",
                    "snippet": "Creditsafe Technology",
                }
            ]
        }
        event = events.normalize_many(
            {
                "message": {
                    "content": [
                        {
                            "toolResult": {
                                "toolUseId": "t1",
                                "status": "success",
                                "content": [{"text": __import__("json").dumps(payload)}],
                            }
                        }
                    ]
                }
            }
        )
        self.assertEqual(len(event[0]["sources"]), 1)
        source = event[0]["sources"][0]
        self.assertEqual(source["kind"], "knowledge")
        self.assertEqual(source["index"], 4)
        self.assertEqual(source["title"], "resume.pdf")
        self.assertEqual(source["subtitle"], "my-career · page 2")

    def test_tool_result_reports_cache_provenance(self) -> None:
        payload = {
            "chunks": [],
            "sources": [],
            "meta": {
                "cache": {
                    "hit": True,
                    "kind": "semantic",
                    "backend": "redis",
                    "similarity": 0.9812,
                    "vectorId": "abc",
                }
            },
        }
        event = events.normalize_many(
            {
                "type": "tool_result",
                "tool_result": {
                    "toolUseId": "t1",
                    "status": "success",
                    "content": [{"text": __import__("json").dumps(payload)}],
                },
            }
        )
        self.assertEqual(
            event[0]["cache"],
            {"hit": True, "kind": "semantic", "backend": "redis", "similarity": 0.9812},
        )

    def test_tool_result_without_cache_omits_the_field(self) -> None:
        payload = {"sources": [], "meta": {"cache": {"hit": False, "kind": "none"}}}
        event = events.normalize_many(
            {
                "type": "tool_result",
                "tool_result": {
                    "toolUseId": "t1",
                    "status": "success",
                    "content": [{"text": __import__("json").dumps(payload)}],
                },
            }
        )
        # A miss still reports provenance (hit=False), but a payload with no
        # ``meta.cache`` at all leaves the frame untouched.
        self.assertEqual(event[0]["cache"], {"hit": False, "kind": "none"})
        plain = events.normalize_many(
            {
                "type": "tool_result",
                "tool_result": {
                    "toolUseId": "t2",
                    "status": "success",
                    "content": [{"text": '{"results": []}'}],
                },
            }
        )
        self.assertNotIn("cache", plain[0])

    def test_tool_result_reports_graph_provenance(self) -> None:
        payload = {
            "chunks": [],
            "sources": [],
            "relationships": [
                {
                    "subject": "Alice",
                    "predicate": "WORKS_AT",
                    "object": "Acme Corp",
                    "hop": 0,
                    "weight": 1.0,
                },
                {"subject": "", "predicate": "X", "object": "Y"},
            ],
            "meta": {
                "graph": {
                    "enabled": True,
                    "strategy": "graph",
                    "fallback": False,
                    "seeds": 2,
                    "nodes": 5,
                    "edges": 4,
                    "parents": 3,
                }
            },
        }
        event = events.normalize_many(
            {
                "type": "tool_result",
                "tool_result": {
                    "toolUseId": "t1",
                    "status": "success",
                    "content": [{"text": __import__("json").dumps(payload)}],
                },
            }
        )
        graph = event[0]["graph"]
        self.assertEqual(graph["strategy"], "graph")
        self.assertFalse(graph["fallback"])
        self.assertEqual(graph["seeds"], 2)
        # Only well-formed triples ride along, capped for the frame.
        self.assertEqual(
            graph["relationships"],
            [{"subject": "Alice", "predicate": "WORKS_AT", "object": "Acme Corp", "hop": 0}],
        )

    def test_tool_result_reports_graph_fallback(self) -> None:
        payload = {
            "sources": [],
            "relationships": [],
            "meta": {
                "graph": {
                    "enabled": True,
                    "strategy": "graph",
                    "fallback": True,
                    "reason": "no matching entities",
                    "seeds": 0,
                }
            },
        }
        event = events.normalize_many(
            {
                "type": "tool_result",
                "tool_result": {
                    "toolUseId": "t1",
                    "status": "success",
                    "content": [{"text": __import__("json").dumps(payload)}],
                },
            }
        )
        self.assertEqual(event[0]["graph"]["reason"], "no matching entities")
        self.assertTrue(event[0]["graph"]["fallback"])

    def test_tool_result_without_graph_omits_the_field(self) -> None:
        # A hybrid-only search (graph disabled) and an ordinary tool result both
        # leave the frame lean.
        hybrid = {
            "sources": [],
            "meta": {"graph": {"enabled": False, "strategy": "hybrid"}},
        }
        for payload in (hybrid, {"results": []}):
            event = events.normalize_many(
                {
                    "type": "tool_result",
                    "tool_result": {
                        "toolUseId": "t1",
                        "status": "success",
                        "content": [{"text": __import__("json").dumps(payload)}],
                    },
                }
            )
            self.assertNotIn("graph", event[0])

    def test_tool_result_extracts_web_sources(self) -> None:
        payload = {
            "results": [
                {"title": "Creditsafe", "url": "https://example.com", "highlights": ["hi"]}
            ]
        }
        event = events.normalize_many(
            {
                "type": "tool_result",
                "tool_result": {
                    "toolUseId": "t1",
                    "status": "success",
                    "content": [{"text": __import__("json").dumps(payload)}],
                },
            }
        )
        self.assertEqual(len(event[0]["sources"]), 1)
        self.assertEqual(event[0]["sources"][0]["kind"], "web")
        self.assertEqual(event[0]["sources"][0]["url"], "https://example.com")

    def test_normalize_many_single(self) -> None:
        self.assertEqual(events.normalize_many({"data": "hi"}), [{"type": "text", "data": "hi"}])

    def test_lifecycle_events_are_dropped(self) -> None:
        self.assertIsNone(events.normalize({"init_event_loop": True}))
        self.assertIsNone(events.normalize({"start_event_loop": True}))

    def test_force_stop_is_an_error(self) -> None:
        event = events.normalize({"force_stop": True, "force_stop_reason": "limit"})
        self.assertEqual(event, {"type": "run.error", "message": "limit"})

    def test_non_dict_is_ignored(self) -> None:
        self.assertIsNone(events.normalize("nope"))


if __name__ == "__main__":
    unittest.main()

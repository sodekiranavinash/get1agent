"""Unit tests for the evaluation-lab metrics and judge parsing.

Run with: ``make -C backend/services/user-api test``
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest import mock

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from src.evals import judge, metrics  # noqa: E402
from src.evals import agent_client, langfuse  # noqa: E402
from src.evals import playground  # noqa: E402


class RetrievalMetricsTests(unittest.TestCase):
    def test_no_expected_sources_is_omitted(self) -> None:
        self.assertEqual(metrics.retrieval_metrics([{"documentId": "a"}], []), {})

    def test_perfect_match(self) -> None:
        chunks = [
            {"documentId": "a", "page": 1},
            {"documentId": "b", "page": 2},
        ]
        expected = [{"documentId": "a", "page": 1}, {"documentId": "b", "page": 2}]
        result = metrics.retrieval_metrics(chunks, expected)
        self.assertEqual(result["context_recall"], 1.0)
        self.assertEqual(result["context_precision"], 1.0)
        self.assertEqual(result["hit_rate"], 1.0)
        self.assertEqual(result["mrr"], 1.0)

    def test_partial_recall_and_rank(self) -> None:
        chunks = [
            {"documentId": "x", "page": 9},
            {"documentId": "a", "page": 1},
            {"documentId": "b", "page": 2},
        ]
        expected = [{"documentId": "a", "page": 1}, {"documentId": "b", "page": 2}]
        result = metrics.retrieval_metrics(chunks, expected)
        self.assertEqual(result["context_recall"], 1.0)
        self.assertAlmostEqual(result["context_precision"], round(2 / 3, 4))
        self.assertEqual(result["hit_rate"], 1.0)
        # First relevant is at rank 2.
        self.assertEqual(result["mrr"], 0.5)

    def test_missing_relevant_lowers_recall(self) -> None:
        chunks = [{"documentId": "a", "page": 1}]
        expected = [{"documentId": "a", "page": 1}, {"documentId": "b", "page": 2}]
        result = metrics.retrieval_metrics(chunks, expected)
        self.assertEqual(result["context_recall"], 0.5)
        self.assertEqual(result["context_precision"], 1.0)
        self.assertEqual(result["hit_rate"], 1.0)

    def test_page_less_expected_matches_any_page(self) -> None:
        chunks = [{"documentId": "a", "page": 7}]
        expected = [{"documentId": "a", "page": None}]
        result = metrics.retrieval_metrics(chunks, expected)
        self.assertEqual(result["context_recall"], 1.0)
        self.assertEqual(result["mrr"], 1.0)

    def test_no_chunks_zeroes_metrics(self) -> None:
        result = metrics.retrieval_metrics([], [{"documentId": "a", "page": 1}])
        self.assertEqual(result["context_recall"], 0.0)
        self.assertEqual(result["context_precision"], 0.0)
        self.assertEqual(result["hit_rate"], 0.0)
        self.assertEqual(result["mrr"], 0.0)


class AggregateMetricsTests(unittest.TestCase):
    def test_averages_present_metrics_only(self) -> None:
        rows = [
            {"faithfulness": 1.0, "hit_rate": 1.0},
            {"faithfulness": 0.5, "hit_rate": 0.0},
            {"faithfulness": 1.0},  # hit_rate omitted for this case
        ]
        result = metrics.aggregate_metrics(rows)
        self.assertAlmostEqual(result["faithfulness"], 0.8333)
        self.assertEqual(result["faithfulness_cases"], 3)
        self.assertEqual(result["hit_rate"], 0.5)
        self.assertEqual(result["hit_rate_cases"], 2)
        self.assertNotIn("answer_correctness", result)

    def test_booleans_and_non_numeric_ignored(self) -> None:
        result = metrics.aggregate_metrics([{"faithfulness": True, "note": "x"}])
        self.assertEqual(result, {})


class ExtractJsonTests(unittest.TestCase):
    def test_plain_object(self) -> None:
        self.assertEqual(judge.extract_json('{"a": 1}'), {"a": 1})

    def test_fenced_object(self) -> None:
        text = 'Here you go:\n```json\n{"a": 2}\n```\n'
        self.assertEqual(judge.extract_json(text), {"a": 2})

    def test_surrounded_object(self) -> None:
        self.assertEqual(judge.extract_json('sure {"a": {"b": 3}} done'), {"a": {"b": 3}})

    def test_invalid_raises(self) -> None:
        with self.assertRaises(judge.JudgeError):
            judge.extract_json("not json")


class ScoreTests(unittest.TestCase):
    def test_clamps_and_coerces(self) -> None:
        self.assertEqual(judge._score(1.5), 1.0)
        self.assertEqual(judge._score(-2), 0.0)
        self.assertEqual(judge._score("0.25"), 0.25)
        self.assertEqual(judge._score(None), 0.0)


class TrajectoryMetricsTests(unittest.TestCase):
    def test_perfect_overlap(self) -> None:
        result = metrics.trajectory_metrics(
            ["search", "web", "search"], ["search", "search", "web"]
        )
        self.assertEqual(result["tool_calls"], 3.0)
        self.assertEqual(result["tool_precision"], 1.0)
        self.assertEqual(result["tool_recall"], 1.0)
        self.assertEqual(result["tool_f1"], 1.0)

    def test_no_expected_tools(self) -> None:
        self.assertEqual(metrics.trajectory_metrics(["a"], None), {"tool_calls": 1.0})

    def test_extra_calls_lower_precision(self) -> None:
        result = metrics.trajectory_metrics(["a", "b"], ["a"])
        self.assertEqual(result["tool_precision"], 0.5)
        self.assertEqual(result["tool_recall"], 1.0)
        self.assertAlmostEqual(result["tool_f1"], round(2 * 0.5 * 1.0 / 1.5, 4))


class AgentFrameTests(unittest.TestCase):
    def test_parses_data_line(self) -> None:
        self.assertEqual(
            agent_client._frames('data: {"type":"text","text":"hi"}'),
            {"type": "text", "text": "hi"},
        )

    def test_ignores_non_data_and_bad_json(self) -> None:
        self.assertIsNone(agent_client._frames("event: ping"))
        self.assertIsNone(agent_client._frames("data: not-json"))
        self.assertIsNone(agent_client._frames("data: "))


class OtlpPayloadTests(unittest.TestCase):
    def test_payload_shape(self) -> None:
        payload = langfuse._otlp_payload(
            trace_id="a" * 32,
            span_id="b" * 16,
            span_name="experiment-item",
            start_ns=1,
            end_ns=2,
            attributes=[langfuse._attr("k", "v")],
            user_id="u_1",
        )
        span = payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
        self.assertEqual(span["traceId"], "a" * 32)
        self.assertEqual(span["spanId"], "b" * 16)
        self.assertEqual(span["startTimeUnixNano"], "1")
        self.assertIn({"key": "k", "value": {"stringValue": "v"}}, span["attributes"])


class EmitExperimentTests(unittest.TestCase):
    def test_builds_experiment_attributes_and_numeric_scores(self) -> None:
        captured: dict = {"scores": []}

        def fake_post(payload, **kwargs):
            captured["otlp"] = payload

        def fake_request(method, path, payload=None, **kwargs):
            captured["scores"].append(payload)
            return {}

        import unittest.mock as mock

        with mock.patch.object(langfuse, "configured", return_value=True), mock.patch.object(
            langfuse, "_post_otlp", side_effect=fake_post
        ), mock.patch.object(langfuse, "request", side_effect=fake_request):
            trace_id = langfuse.emit_experiment_item(
                user_id="u_1",
                experiment_id="exp",
                experiment_name="name",
                experiment_description="desc",
                dataset_id="ds-id",
                item_id="item-id",
                item_input={"question": "q"},
                item_output="a",
                expected_output="e",
                metrics={"faithfulness": 1.0, "note": "x"},
                reasoning="grounded",
            )

        self.assertIsNotNone(trace_id)
        self.assertEqual(len(trace_id), 32)
        attributes = captured["otlp"]["resourceSpans"][0]["scopeSpans"][0]["spans"][0][
            "attributes"
        ]
        keys = {entry["key"] for entry in attributes}
        for key in (
            "langfuse.experiment.id",
            "langfuse.experiment.name",
            "langfuse.experiment.dataset.id",
            "langfuse.experiment.item.id",
            "langfuse.experiment.item.root_observation_id",
            "langfuse.observation.input",
            "langfuse.observation.output",
            "langfuse.experiment.item.expected_output",
        ):
            self.assertIn(key, keys)
        # Only numeric metrics become scores.
        names = [score["name"] for score in captured["scores"]]
        self.assertEqual(names, ["eval_faithfulness"])
        self.assertEqual(captured["scores"][0]["traceId"], trace_id)


class PlaygroundMessageTests(unittest.TestCase):
    def test_normalizes_roles_and_content(self) -> None:
        result = playground._clean_messages(
            [
                {"role": "SYSTEM", "content": "a"},
                {"role": "weird", "content": "b"},
                {"role": "user"},
            ]
        )
        self.assertEqual(
            result,
            [
                {"role": "system", "content": "a"},
                {"role": "user", "content": "b"},
                {"role": "user", "content": ""},
            ],
        )

    def test_rejects_empty(self) -> None:
        with self.assertRaises(playground.PlaygroundError):
            playground._clean_messages([])


class JudgeScoringTests(unittest.TestCase):
    def _chat(self, payload: dict):
        return mock.patch.object(judge, "_chat", return_value=json.dumps(payload))

    def test_faithfulness_fraction(self) -> None:
        payload = {
            "claims": [
                {"text": "a", "supported": True},
                {"text": "b", "supported": False},
                {"text": "c", "supported": True},
            ],
            "reasoning": "r",
        }
        with self._chat(payload):
            result = judge.judge_faithfulness("q", "ans", [{"text": "ctx"}])
        self.assertAlmostEqual(result["faithfulness"], round(2 / 3, 4))
        self.assertEqual(result["totalClaims"], 3)
        self.assertEqual(result["supportedClaims"], 2)
        self.assertFalse(result["claims"][1]["supported"])

    def test_faithfulness_vacuous_when_no_claims(self) -> None:
        with self._chat({"claims": [], "reasoning": "idk"}):
            result = judge.judge_faithfulness("q", "I don't know", [])
        self.assertEqual(result["faithfulness"], 1.0)
        self.assertEqual(result["totalClaims"], 0)

    def test_context_relevance_fraction(self) -> None:
        payload = {
            "passages": [
                {"index": 1, "relevant": True},
                {"index": 2, "relevant": False},
                {"index": 3, "relevant": True},
            ],
            "reasoning": "r",
        }
        with self._chat(payload):
            result = judge.judge_context_relevance(
                "q", [{"text": "a"}, {"text": "b"}, {"text": "c"}]
            )
        self.assertAlmostEqual(result["context_relevance"], round(2 / 3, 4))
        self.assertEqual(result["relevantPassages"], 2)
        self.assertEqual(result["totalPassages"], 3)

    def test_context_relevance_without_context(self) -> None:
        result = judge.judge_context_relevance("q", [])
        self.assertEqual(result["context_relevance"], 0.0)


if __name__ == "__main__":
    unittest.main()

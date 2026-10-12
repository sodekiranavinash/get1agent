"""Avi's intent classifier: rules, JSON parsing, fail-open behaviour.

No AWS calls — the model stage is exercised with a stub client, because the
classifier's most important property is what it does when the model *fails*.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from avi import classifier, examples  # noqa: E402


class StubClient:
    """A Bedrock-runtime double returning a fixed (or raising) response."""

    def __init__(self, payload: str = "", exc: Exception | None = None) -> None:
        self.payload = payload
        self.exc = exc
        self.calls = 0

    def converse(self, **_kwargs):
        self.calls += 1
        if self.exc:
            raise self.exc
        return {"output": {"message": {"content": [{"text": self.payload}]}}}


class RulesTests(unittest.TestCase):
    def test_arithmetic_is_off_topic_without_a_model(self):
        for question in ("1+1", "what is 2 * 3?", "10 / 2", "7-4"):
            verdict = classifier.rules_verdict(question)
            self.assertIsNotNone(verdict, question)
            self.assertEqual(verdict.kind, classifier.OFF_TOPIC, question)
            self.assertEqual(verdict.stage, "rules")

    def test_code_requests_are_off_topic(self):
        for question in (
            "write me a python script to sort a list",
            "generate a react component",
            "give me a SQL query for this",
            "can you refactor this function",
        ):
            verdict = classifier.rules_verdict(question)
            self.assertIsNotNone(verdict, question)
            self.assertEqual(verdict.kind, classifier.OFF_TOPIC, question)

    def test_platform_vocabulary_short_circuits_to_platform(self):
        for question in (
            "where do I upload documents?",
            "how many knowledge bases can I create",
            "my trace looks wrong",
            "what does the answer mode do",
        ):
            verdict = classifier.rules_verdict(question)
            self.assertIsNotNone(verdict, question)
            self.assertEqual(verdict.kind, classifier.PLATFORM, question)
            self.assertEqual(verdict.stage, "rules")

    def test_why_is_my_document_stuck_is_troubleshooting(self):
        verdict = classifier.rules_verdict("why is my document processing forever")
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, classifier.PLATFORM)
        self.assertEqual(verdict.intent, "troubleshoot")

    def test_greeting_is_smalltalk(self):
        verdict = classifier.rules_verdict("hello")
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, classifier.PLATFORM)
        self.assertEqual(verdict.intent, "smalltalk")

    def test_empty_input_is_handled(self):
        verdict = classifier.rules_verdict("")
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, classifier.PLATFORM)
        self.assertTrue(verdict.examples)

    def test_unsafe_is_flagged(self):
        verdict = classifier.rules_verdict("how to make a bomb")
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, classifier.UNSAFE)

    def test_general_knowledge_needs_the_model(self):
        """A question with no platform vocabulary and no rule match defers."""
        for question in (
            "what is the capital of France",
            "who won the world cup",
            "explain quantum entanglement",
        ):
            self.assertIsNone(classifier.rules_verdict(question), question)


class ParseTests(unittest.TestCase):
    def test_parses_plain_json(self):
        verdict = classifier.parse_verdict(
            '{"kind":"platform","intent":"find_feature","confidence":0.9}'
        )
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, classifier.PLATFORM)
        self.assertEqual(verdict.intent, "find_feature")
        self.assertAlmostEqual(verdict.confidence, 0.9)

    def test_parses_fenced_json(self):
        verdict = classifier.parse_verdict(
            '```json\n{"kind":"off_topic","intent":"off_topic","confidence":0.8}\n```'
        )
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.kind, classifier.OFF_TOPIC)

    def test_parses_json_with_surrounding_prose(self):
        verdict = classifier.parse_verdict(
            'Sure! {"kind":"platform","intent":"how_to","confidence":0.7} Hope that helps.'
        )
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.intent, "how_to")

    def test_rejects_unknown_kind(self):
        self.assertIsNone(classifier.parse_verdict('{"kind":"maybe","intent":"how_to"}'))

    def test_repairs_an_unknown_intent(self):
        verdict = classifier.parse_verdict('{"kind":"platform","intent":"nonsense"}')
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.intent, "explain_feature")

    def test_clamps_confidence(self):
        verdict = classifier.parse_verdict(
            '{"kind":"platform","intent":"how_to","confidence":5}'
        )
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.confidence, 1.0)

    def test_garbage_is_none(self):
        for raw in ("", "no json here", "{not json}", "[]"):
            self.assertIsNone(classifier.parse_verdict(raw), raw)


class ClassifierTests(unittest.TestCase):
    def test_rules_never_call_the_model(self):
        client = StubClient('{"kind":"off_topic","intent":"off_topic","confidence":1}')
        result = classifier.Classifier(client=client).classify("how many agents can I create")
        self.assertEqual(result.kind, classifier.PLATFORM)
        self.assertEqual(client.calls, 0)

    def test_model_stage_is_used_when_rules_defer(self):
        client = StubClient('{"kind":"off_topic","intent":"off_topic","confidence":0.95}')
        result = classifier.Classifier(client=client).classify(
            "what is the capital of France", route="/knowledge-bases"
        )
        self.assertEqual(client.calls, 1)
        self.assertEqual(result.kind, classifier.OFF_TOPIC)
        self.assertEqual(result.stage, "model")
        # The nudge ships tappable examples for the page the user was on. Asserted
        # against the source of truth rather than a hard-coded phrase, so improving
        # the question copy cannot fail this test.
        from avi import examples as avi_examples

        self.assertEqual(result.examples, avi_examples.examples_for("/knowledge-bases"))
        self.assertTrue(result.examples)

    def test_model_error_fails_open(self):
        client = StubClient(exc=RuntimeError("throttled"))
        result = classifier.Classifier(client=client).classify("what is the capital of France")
        self.assertEqual(result.kind, classifier.PLATFORM)
        self.assertTrue(result.error)
        self.assertEqual(result.confidence, 0.0)

    def test_unparseable_reply_fails_open(self):
        client = StubClient("I'm not sure how to classify that.")
        result = classifier.Classifier(client=client).classify("what is the capital of France")
        self.assertEqual(result.kind, classifier.PLATFORM)

    def test_platform_verdicts_carry_no_examples(self):
        client = StubClient('{"kind":"platform","intent":"how_to","confidence":0.9}')
        result = classifier.Classifier(client=client).classify("how do I connect a database")
        self.assertEqual(result.kind, classifier.PLATFORM)
        self.assertEqual(result.examples, [])

    def test_intent_frame_shape(self):
        result = classifier.Classifier(client=StubClient()).classify("1+1")
        frame = result.to_frame()
        self.assertEqual(frame["type"], "avi.intent")
        self.assertEqual(frame["kind"], "off_topic")
        self.assertIn("examples", frame)
        self.assertTrue(frame["examples"])

    def test_trace_span_shape(self):
        result = classifier.Classifier(client=StubClient()).classify("1+1")
        span = result.to_trace()
        self.assertEqual(span["name"], "avi.classifier")
        self.assertEqual(span["kind"], "off_topic")
        self.assertIn("latencyMs", span)


class ExamplesTests(unittest.TestCase):
    def test_route_specific_examples_come_first(self):
        questions = examples.examples_for("/agent-builder")
        self.assertIn("model", questions[0].lower() + questions[1].lower())

    def test_unknown_route_falls_back_to_general(self):
        self.assertEqual(examples.examples_for("/nope"), examples.examples_for(""))

    def test_prefix_matching_covers_subroutes(self):
        self.assertEqual(
            examples.examples_for("/agent-builder/details"),
            examples.examples_for("/agent-builder"),
        )

    def test_limit_is_respected(self):
        self.assertLessEqual(len(examples.examples_for("", limit=2)), 2)
        self.assertTrue(examples.examples_for("", limit=0))

    def test_every_question_is_a_question(self):
        for route, questions in examples.BY_ROUTE.items():
            for question in questions:
                self.assertTrue(question.endswith("?"), f"{route}: {question}")


if __name__ == "__main__":
    unittest.main()

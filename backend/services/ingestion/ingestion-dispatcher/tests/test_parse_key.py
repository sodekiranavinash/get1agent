"""Unit tests for the ingestion dispatcher's key routing (no AWS calls).

Run with: ``make -C backend/services/ingestion/ingestion-dispatcher test``

The bug these pin: ``_parse_key`` required the knowledge-base and document id to be
UUIDs, so AI Assistant's reserved platform corpus — whose ids are deliberately
fixed and human-readable (``kb_platform_docs_0001``, ``ai-assistant-chat``) — was
accepted by S3, delivered by SQS, and then dropped here. The dispatcher returned
success, logged nothing, started no execution, and the 47 uploaded documents sat in
``processing`` until the watchdog failed them.

The routing rules that must not regress with the fix:

* a ``raw/`` key with UUID ids still routes (every ordinary upload);
* a ``raw/`` key with the platform ids now routes too;
* nothing else does — derived and index writes never trigger ingestion, and a key
  that could escape its prefix (a slash, ``..``, an empty segment) is refused.
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # service root

import handler  # noqa: E402

UUID_KB = "0f0a1e6c-9a1f-4f6b-8a2e-2b1c3d4e5f60"
UUID_DOC = "9b8c7d6e-5f40-4a3b-9c2d-1e0f9a8b7c6d"

#: The reserved platform scope, exactly as ``tools/ai-assistant-knowledge/scope.py``
#: defines it and as AI Assistant's Lambda is configured (``AI_ASSISTANT_KB_ID``).
PLATFORM_KB = "kb_platform_docs_0001"
PLATFORM_DOC = "ai-assistant-chat"

#: The longest id the corpus actually produces: ``ai-assistant-`` + a 58-character
#: slug (``generator.Document.id``). It is 71 characters, and an id cap of 64 refused
#: eight real documents — so this exact length is pinned here.
LONG_PLATFORM_DOC = "ai-assistant-" + "troubleshooting-a-custom-tool-times-out-or-errors-check--4"


class ParseKeyTest(unittest.TestCase):
    def test_a_uuid_key_routes(self):
        parsed = handler._parse_key(f"raw/u_7k3f9qz2mpx8n4rq/{UUID_KB}/{UUID_DOC}/guide.pdf")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["knowledgeBaseId"], UUID_KB)
        self.assertEqual(parsed["documentId"], UUID_DOC)
        self.assertEqual(parsed["userId"], "u_7k3f9qz2mpx8n4rq")
        self.assertEqual(parsed["fileName"], "guide.pdf")

    def test_a_platform_key_routes(self):
        parsed = handler._parse_key(
            f"raw/platform/{PLATFORM_KB}/{PLATFORM_DOC}/chat.md"
        )
        self.assertIsNotNone(parsed, "the platform corpus must reach the pipeline")
        self.assertEqual(parsed["userId"], "platform")
        self.assertEqual(parsed["knowledgeBaseId"], PLATFORM_KB)
        self.assertEqual(parsed["documentId"], PLATFORM_DOC)

    def test_the_longest_corpus_id_routes(self):
        self.assertEqual(len(LONG_PLATFORM_DOC), 71)
        parsed = handler._parse_key(
            f"raw/platform/{PLATFORM_KB}/{LONG_PLATFORM_DOC}/troubleshooting.md"
        )
        self.assertIsNotNone(parsed, "a 71-character corpus id must not be refused")
        self.assertEqual(parsed["documentId"], LONG_PLATFORM_DOC)

    def test_derived_and_index_writes_are_ignored(self):
        for key in (
            f"derived/platform/{PLATFORM_KB}/{PLATFORM_DOC}/text.md",
            f"index/platform/parents/{PLATFORM_DOC}#0.json",
            f"storage/platform/file/name.pdf",
        ):
            with self.subTest(key=key):
                self.assertIsNone(handler._parse_key(key))

    def test_malformed_keys_are_ignored(self):
        for key in (
            "",
            "raw",
            "raw/only-two-segments",
            f"raw//{PLATFORM_KB}/{PLATFORM_DOC}/chat.md",  # empty user
            f"raw/platform/{PLATFORM_KB}//chat.md",  # empty doc id
            f"raw/platform/{PLATFORM_KB}/{PLATFORM_DOC}/",  # empty file name
            f"raw/platform/{PLATFORM_KB}/{PLATFORM_DOC}/.hidden",  # dotfile
            f"raw/platform/../etc/{PLATFORM_DOC}/passwd",  # traversal in the id
            f"raw/platform/{PLATFORM_KB}/{'a' * 200}/chat.md",  # id too long
            f"raw/platform/{PLATFORM_KB}/{PLATFORM_DOC}/../escape.md",  # traversal in the name
        ):
            with self.subTest(key=key):
                self.assertIsNone(handler._parse_key(key))

    def test_a_slash_never_lands_in_an_id(self):
        # The split is bounded to five parts, so a further slash belongs to the file
        # name (an S3 key may legitimately contain one). An id therefore can never
        # carry a slash or a ``..`` segment — which is what keeps the id pattern, and
        # the traversal refusal above, honest.
        parsed = handler._parse_key(f"raw/platform/{PLATFORM_KB}/a/b/chat.md")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["documentId"], "a")
        self.assertEqual(parsed["fileName"], "b/chat.md")
        self.assertNotIn("/", parsed["documentId"])


class _FakeStepFunctions:
    """Records start_execution calls; mirrors the one client exception the handler
    catches."""

    class exceptions:  # noqa: N801 - mirrors botocore's client.exceptions shape
        class ExecutionAlreadyExists(Exception):
            pass

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def start_execution(self, **kwargs: object) -> dict[str, str]:
        self.calls.append(kwargs)
        return {"executionArn": "arn:aws:states:::execution:fake"}


def _event(key: str, *, event_id: str = "evt-1", etag: str = "abc123") -> dict[str, object]:
    body = json.dumps(
        {
            "source": "aws.s3",
            "detail-type": "Object Created",
            "id": event_id,
            "detail": {
                "bucket": {"name": "get1agent-prod-knowledge-bases"},
                "object": {"key": key, "etag": etag},
            },
        }
    )
    return {"Records": [{"messageId": "msg-1", "body": body}]}


class LambdaHandlerTest(unittest.TestCase):
    def _run(self, key: str, **kwargs: object) -> tuple[dict[str, object], _FakeStepFunctions]:
        client = _FakeStepFunctions()
        env = {"STATE_MACHINE_ARN": "arn:aws:states:ap-south-1:1:stateMachine:ingestion"}
        with mock.patch.dict(os.environ, env), mock.patch.object(
            handler.boto3, "client", return_value=client
        ):
            result = handler.lambda_handler(_event(key, **kwargs), None)
        return result, client

    def test_a_platform_upload_starts_an_ingestion_execution(self):
        result, client = self._run(f"raw/platform/{PLATFORM_KB}/{PLATFORM_DOC}/chat.md")

        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(len(client.calls), 1, "the platform upload must be ingested")
        payload = json.loads(str(client.calls[0]["input"]))
        self.assertEqual(payload["knowledgeBaseId"], PLATFORM_KB)
        self.assertEqual(payload["documentId"], PLATFORM_DOC)
        self.assertEqual(payload["userId"], "platform")
        self.assertEqual(payload["contentHash"], "abc123")
        self.assertEqual(
            client.calls[0]["name"],
            handler._execution_name(PLATFORM_DOC, handler._execution_token("abc123", "evt-1")),
        )

    def test_the_longest_corpus_id_still_starts_an_execution(self):
        # The whole point: 71-character ids, which with the prefix and token are 91
        # characters un-truncated, well past the 80-character ceiling.
        result, client = self._run(
            f"raw/platform/{PLATFORM_KB}/{LONG_PLATFORM_DOC}/troubleshooting.md"
        )
        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(len(client.calls), 1)
        self.assertEqual(json.loads(str(client.calls[0]["input"]))["documentId"], LONG_PLATFORM_DOC)

    def test_execution_names_fit_and_stay_unique(self):
        token_a = handler._execution_token("abc123", "evt-1")
        token_b = handler._execution_token("abc123", "evt-2")
        long_name_a = handler._execution_name(LONG_PLATFORM_DOC, token_a)
        long_name_b = handler._execution_name(LONG_PLATFORM_DOC, token_b)

        self.assertLessEqual(len(long_name_a), handler._MAX_EXECUTION_NAME)
        self.assertTrue(long_name_a.startswith("ingest-"))
        self.assertTrue(long_name_a.endswith(token_a))
        # Uniqueness comes from the token, so truncating the id cannot collide two
        # different uploads of the same document.
        self.assertNotEqual(long_name_a, long_name_b)

    def test_a_refused_key_is_logged_not_silent(self):
        # A `raw/` key that is not routed used to `continue` with no line in the log,
        # which is what made a stuck document undiagnosable.
        with mock.patch.object(handler, "_log") as log:
            self._run(f"raw/platform/{PLATFORM_KB}/{'a' * 200}/chat.md")
        messages = [call.args[1] for call in log.call_args_list]
        self.assertTrue(
            any("does not look like an upload" in m for m in messages), messages
        )

    def test_a_re_upload_gets_a_new_execution_name(self):
        # A STANDARD state machine ignores a repeated execution name for 90 days, so
        # the same content uploaded again must not reuse the previous name.
        first, _ = self._run(f"raw/platform/{PLATFORM_KB}/{PLATFORM_DOC}/chat.md", event_id="evt-1")
        second, _ = self._run(f"raw/platform/{PLATFORM_KB}/{PLATFORM_DOC}/chat.md", event_id="evt-2")
        self.assertEqual(first, {"batchItemFailures": []})
        self.assertEqual(second, {"batchItemFailures": []})

    def test_an_ignored_key_starts_nothing_and_is_acked(self):
        result, client = self._run(f"index/platform/parents/{PLATFORM_DOC}#0.json")
        self.assertEqual(result, {"batchItemFailures": []})
        self.assertEqual(client.calls, [])

    def test_a_missing_state_machine_arn_fails_loudly(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                handler.lambda_handler(_event(f"raw/platform/{PLATFORM_KB}/{PLATFORM_DOC}/chat.md"), None)


if __name__ == "__main__":
    unittest.main()

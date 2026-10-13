"""Admin → AI Assistant corpus routes: status, and the re-ingest action.

Re-ingest is the one place an operator can make the platform *write* through the
ingestion pipeline, so the things worth pinning are its refusals and its
fan-out:

* it starts the **same** state machine the S3 → EventBridge → SQS dispatcher
  starts, with the same input shape — otherwise "re-ingest" would quietly mean
  something different from a real re-upload;
* an unconfigured deployment fails with a clear 503 instead of a stack trace;
* one bad document does not abandon the rest of the corpus;
* it never Scans: the document list is one Query of the reserved scope.

No AWS: the repository and `boto3` are replaced with recorders.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

SERVICE_ROOT = Path(__file__).resolve().parents[1]
PACKAGES = SERVICE_ROOT.parents[2] / "packages"
for extra in (str(SERVICE_ROOT), str(PACKAGES)):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import src.ai_assistant as admin  # noqa: E402


class _StepFunctions:
    """Stands in for the boto3 Step Functions client."""

    def __init__(self, fail_on: set[str] | None = None) -> None:
        self.executions: list[dict] = []
        self._fail_on = fail_on or set()

    def start_execution(self, **kwargs):
        document_id = json.loads(kwargs["input"])["documentId"]
        if document_id in self._fail_on:
            raise RuntimeError("boom")
        self.executions.append(kwargs)
        return {"executionArn": f"arn:{kwargs['name']}"}


def _document(doc_id: str, name: str = "guide.md") -> dict:
    return {"documentId": doc_id, "fileName": name, "status": "ready", "chunkCount": 12}


class _Recorder:
    def __init__(self, result):
        self.calls = 0
        self._result = result

    def __call__(self, *args, **kwargs):
        self.calls += 1
        return self._result


class ReingestTests(unittest.TestCase):
    def setUp(self) -> None:
        import os

        self._env = {
            key: os.environ.get(key)
            for key in ("INGESTION_STATE_MACHINE_ARN", "AI_ASSISTANT_KB_ID", "AI_ASSISTANT_SCOPE", "S3_BUCKET", "AWS_REGION")
        }
        os.environ.update(
            {
                "INGESTION_STATE_MACHINE_ARN": "arn:aws:states:ap-south-1:1:stateMachine:ingest",
                "AI_ASSISTANT_KB_ID": "kb_platform_docs_0001",
                "AI_ASSISTANT_SCOPE": "platform",
                "S3_BUCKET": "get1agent-prod-knowledge",
                "AWS_REGION": "ap-south-1",
            }
        )
        from data.repositories import documents as docs_repo

        self.documents = _Recorder(
            [_document("doc-1"), _document("doc-2", "faq.md")]
        )
        self._real_list = docs_repo.list_documents
        docs_repo.list_documents = self.documents  # type: ignore[assignment]
        self.sfn = _StepFunctions()
        import boto3

        self._boto_client = boto3.client
        boto3.client = lambda service, **kwargs: self.sfn  # type: ignore[assignment]

    def tearDown(self) -> None:
        import os

        import boto3

        from data.repositories import documents as docs_repo

        boto3.client = self._boto_client
        docs_repo.list_documents = self._real_list  # type: ignore[assignment]
        for key, value in self._env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _reingest(self, body: dict | None = None) -> tuple[int, dict]:
        response = admin.route({}, "POST", ["v1", "admin", "ai-assistant", "knowledge", "reingest"], body or {})
        assert response is not None
        return response["statusCode"], json.loads(response["body"])

    def test_it_starts_the_pipeline_for_every_document(self) -> None:
        status, body = self._reingest()
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 2)
        self.assertEqual(len(self.sfn.executions), 2)

    def test_the_state_machine_is_the_one_the_dispatcher_uses(self) -> None:
        self._reingest()
        for execution in self.sfn.executions:
            self.assertEqual(
                execution["stateMachineArn"], "arn:aws:states:ap-south-1:1:stateMachine:ingest"
            )

    def test_the_input_matches_the_dispatcher_shape(self) -> None:
        """Same keys the real dispatcher sends, so the stages cannot tell them apart."""
        self._reingest()
        payload = json.loads(self.sfn.executions[0]["input"])
        for key in ("userId", "knowledgeBaseId", "documentId", "fileName", "s3Key", "contentHash"):
            self.assertIn(key, payload)
        self.assertEqual(payload["userId"], "platform")
        self.assertEqual(payload["knowledgeBaseId"], "kb_platform_docs_0001")
        self.assertEqual(payload["documentId"], "doc-1")
        self.assertEqual(payload["s3Key"], "raw/platform/kb_platform_docs_0001/doc-1/guide.md")

    def test_execution_names_are_unique_so_a_click_always_runs(self) -> None:
        """A STANDARD state machine ignores a repeated name for 90 days."""
        self._reingest()
        _, _ = self._reingest()
        names = [execution["name"] for execution in self.sfn.executions]
        self.assertEqual(len(names), len(set(names)))

    def test_one_document_can_be_targeted(self) -> None:
        status, body = self._reingest({"documentId": "doc-2"})
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(json.loads(self.sfn.executions[0]["input"])["documentId"], "doc-2")

    def test_an_unknown_document_is_404(self) -> None:
        status, body = self._reingest({"documentId": "nope"})
        self.assertEqual(status, 404)
        self.assertEqual(self.sfn.executions, [])

    def test_an_unconfigured_deployment_is_503_not_a_crash(self) -> None:
        import os

        os.environ.pop("INGESTION_STATE_MACHINE_ARN", None)
        status, body = self._reingest()
        self.assertEqual(status, 503)
        self.assertIn("not configured", body["error"])
        self.assertEqual(self.sfn.executions, [])

    def test_one_failing_document_does_not_abandon_the_rest(self) -> None:
        self.sfn = _StepFunctions(fail_on={"doc-1"})
        import boto3

        boto3.client = lambda service, **kwargs: self.sfn  # type: ignore[assignment]
        status, body = self._reingest()
        self.assertEqual(status, 200)
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["failed"]), 1)
        self.assertEqual(body["failed"][0]["documentId"], "doc-1")

    def test_every_document_failing_is_502(self) -> None:
        self.sfn = _StepFunctions(fail_on={"doc-1", "doc-2"})
        import boto3

        boto3.client = lambda service, **kwargs: self.sfn  # type: ignore[assignment]
        status, body = self._reingest()
        self.assertEqual(status, 502)
        self.assertEqual(body["count"], 0)
        self.assertEqual(len(body["failed"]), 2)

    def test_an_empty_corpus_is_409(self) -> None:
        self.documents = _Recorder([])
        from data.repositories import documents as docs_repo

        docs_repo.list_documents = self.documents  # type: ignore[assignment]
        status, body = self._reingest()
        self.assertEqual(status, 409)

    def test_it_reads_the_corpus_with_one_query(self) -> None:
        self._reingest()
        self.assertEqual(self.documents.calls, 1)

    def test_the_scope_comes_from_configuration(self) -> None:
        import os

        os.environ["AI_ASSISTANT_KB_ID"] = "kb_other"
        status, body = self._reingest()
        self.assertEqual(status, 200)
        self.assertEqual(body["kbId"], "kb_other")


class KnowledgeStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        from data.repositories import documents as docs_repo

        self._real_list = docs_repo.list_documents
        docs_repo.list_documents = lambda kb_id: [  # type: ignore[assignment]
            _document("d1"),
            {"documentId": "d2", "fileName": "b.md", "status": "failed"},
        ]

    def tearDown(self) -> None:
        from data.repositories import documents as docs_repo

        docs_repo.list_documents = self._real_list  # type: ignore[assignment]

    def test_get_reports_status_counts(self) -> None:
        response = admin.route({}, "GET", ["v1", "admin", "ai-assistant", "knowledge"], {})
        assert response is not None
        body = json.loads(response["body"])
        self.assertEqual(response["statusCode"], 200)
        self.assertEqual(body["count"], 2)
        self.assertEqual(body["statuses"], {"ready": 1, "failed": 1})

    def test_reingest_rejects_get(self) -> None:
        response = admin.route(
            {}, "GET", ["v1", "admin", "ai-assistant", "knowledge", "reingest"], {}
        )
        assert response is not None
        self.assertEqual(response["statusCode"], 405)

    def test_knowledge_rejects_an_unsupported_method(self) -> None:
        response = admin.route({}, "PUT", ["v1", "admin", "ai-assistant", "knowledge"], {})
        assert response is not None
        self.assertEqual(response["statusCode"], 405)


if __name__ == "__main__":
    unittest.main()

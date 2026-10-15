"""`Storage.put_json_conditional` maps *both* of S3's lost-race errors.

The term index keeps one shared object per token and writes it with an `If-Match`
ETag, so two documents indexed at once collide on the vocabulary they have in
common. S3 reports that race two different ways, and only one of them used to be
translated:

* ``412 PreconditionFailed`` — the ETag has moved on;
* ``409 ConditionalRequestConflict`` — another conditional write to the same key is
  in flight, so this one could not be evaluated.

`term_index._read_modify_write` retries on the module's own ``PreconditionFailed``,
so the raw 409 escaped the retry loop and failed the whole ingestion stage — which
is exactly what a 47-document corpus upload did.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP.parents[1] / "packages"))

from botocore.exceptions import ClientError  # noqa: E402
from core.storage import PreconditionFailed, Storage  # noqa: E402


def _client_error(code: str, status: int) -> ClientError:
    return ClientError(
        {
            "Error": {"Code": code, "Message": "conflict"},
            "ResponseMetadata": {"HTTPStatusCode": status},
        },
        "PutObject",
    )


class _FailingS3:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def put_object(self, **_kwargs: object) -> None:
        raise self.error


class PutJsonConditionalTest(unittest.TestCase):
    def _store(self, error: Exception) -> Storage:
        store = Storage(bucket="b")
        store._client = _FailingS3(error)  # bypass boto3 entirely  # noqa: SLF001
        return store

    def test_an_etag_mismatch_is_mapped(self) -> None:
        with self.assertRaises(PreconditionFailed):
            self._store(_client_error("PreconditionFailed", 412)).put_json_conditional(
                "index/u/terms/token.json", {"df": 1}, "etag"
            )

    def test_a_concurrent_write_conflict_is_mapped(self) -> None:
        with self.assertRaises(PreconditionFailed):
            self._store(
                _client_error("ConditionalRequestConflict", 409)
            ).put_json_conditional("index/u/terms/token.json", {"df": 1}, "etag")

    def test_an_unrelated_error_is_not_swallowed(self) -> None:
        with self.assertRaises(ClientError):
            self._store(_client_error("AccessDenied", 403)).put_json_conditional(
                "index/u/terms/token.json", {"df": 1}, None
            )


if __name__ == "__main__":
    unittest.main()

"""Unit tests for the storage service (no AWS calls).

Run with: ``make -C backend/services/mcp/storage test``

The happy-path tests use a tiny in-memory S3 double and an in-memory storage
repository double (the same shape as the integration suite's ``fake_storage``)
so they run under stdlib ``unittest`` without moto or a DynamoDB table.
"""

from __future__ import annotations

import base64
import sys
import unittest
from pathlib import Path
from unittest import mock

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND / "packages"))  # shared core/data/retrieval
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # service root

from src import service  # noqa: E402

USER = "u_7k3f9qz2mpx8n4rq"
OTHER = "u_zzzzzzzzzzzzzzzz"


class _FakeStorage:
    """Minimal in-memory stand-in for ``core.storage.Storage``."""

    def __init__(self) -> None:
        self.data: dict[str, bytes] = {}

    def put_bytes(self, key: str, data: bytes, content_type: str = "x") -> None:
        self.data[key] = data

    def get_bytes(self, key: str) -> bytes:
        return self.data[key]

    def delete(self, key: str) -> None:
        self.data.pop(key, None)

    def presign_get(self, key: str, expires_in: int = 3600) -> str:
        return f"https://s3.test/{key}"


class _FakeRepo:
    """In-memory stand-in for ``data.repositories.storage``."""

    def __init__(self) -> None:
        self.items: dict[tuple[str, str], dict] = {}

    def storage_item(self, **kwargs) -> dict:
        timestamp = kwargs.get("created_at") or "2026-01-01T00:00:00+00:00"
        return {
            "fileId": kwargs["file_id"],
            "userId": kwargs["user_id"],
            "fileName": kwargs["file_name"],
            "s3Key": kwargs["s3_key"],
            "contentType": kwargs.get("content_type"),
            "sizeBytes": kwargs["size_bytes"],
            "status": kwargs.get("status", "ready"),
            "contentHash": kwargs.get("content_hash"),
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }

    def put_file(self, item: dict) -> dict:
        self.items[(item["userId"], item["fileId"])] = item
        return item

    def get_file(self, user_id: str, file_id: str) -> dict | None:
        return self.items.get((user_id, file_id))

    def list_files(self, user_id: str) -> list[dict]:
        return [item for (owner, _), item in self.items.items() if owner == user_id]

    def delete_file(self, user_id: str, file_id: str) -> dict | None:
        return self.items.pop((user_id, file_id), None)


class HelperTests(unittest.TestCase):
    def test_safe_filename_strips_paths_and_symbols(self) -> None:
        self.assertEqual(service._safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(service._safe_filename("a b!c.txt"), "a b_c.txt")
        self.assertEqual(service._safe_filename(""), "file")

    def test_infer_format(self) -> None:
        self.assertEqual(service._infer_format("application/json", b"{}"), "json")
        self.assertEqual(service._infer_format("text/plain", b"hi"), "text")
        self.assertEqual(service._infer_format("application/octet-stream", b"\xff\xfe\x00"), "base64")
        self.assertEqual(service._infer_format("", b"plain"), "text")

    def test_clamp_bounds(self) -> None:
        self.assertEqual(service._clamp(None, 20_000, 1000, 200_000), 20_000)
        self.assertEqual(service._clamp("15000", 20_000, 1000, 200_000), 15_000)
        self.assertEqual(service._clamp(999_999, 20_000, 1000, 200_000), 200_000)
        self.assertEqual(service._clamp(True, 20_000, 1000, 200_000), 20_000)

    def test_default_content_type(self) -> None:
        self.assertEqual(service._default_content_type("report.json", "text"), "application/json")
        self.assertEqual(service._default_content_type("notes.txt", "text"), "text/plain")
        self.assertEqual(service._default_content_type("blob.bin", "base64"), "application/octet-stream")


class ServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = _FakeStorage()
        self.repo = _FakeRepo()
        self._patches = [
            mock.patch.object(service, "_storage", lambda: self.storage),
            mock.patch.object(service, "storage_repo", self.repo),
        ]
        for patcher in self._patches:
            patcher.start()

    def tearDown(self) -> None:
        for patcher in self._patches:
            patcher.stop()

    def test_write_list_read_delete_roundtrip(self) -> None:
        written = service.write_file(USER, {"fileName": "hello.txt", "content": "hi"})
        self.assertIsNone(written["error"])
        file_id = written["file"]["id"]
        self.assertEqual(written["file"]["fileName"], "hello.txt")
        self.assertEqual(written["file"]["contentType"], "text/plain")
        self.assertEqual(written["file"]["sizeBytes"], 2)
        self.assertTrue(written["file"]["downloadUrl"].startswith("https://s3.test/"))
        self.assertEqual(written["usage"]["fileCount"], 1)
        self.assertTrue(any(key.startswith(f"storage/{USER}/") for key in self.storage.data))

        listed = service.list_files(USER)
        self.assertIsNone(listed["error"])
        self.assertEqual([item["id"] for item in listed["files"]], [file_id])

        read = service.read_file(USER, {"fileId": file_id})
        self.assertIsNone(read["error"])
        self.assertEqual(read["format"], "text")
        self.assertEqual(read["content"], "hi")
        self.assertFalse(read["truncated"])

        # Files are scoped by userId: another user cannot read them.
        self.assertEqual(service.read_file(OTHER, {"fileId": file_id})["error"]["code"], "not_found")

        deleted = service.delete_file(USER, {"fileId": file_id})
        self.assertTrue(deleted["deleted"])
        self.assertEqual(deleted["fileId"], file_id)
        self.assertNotIn(file_id, [item["id"] for item in service.list_files(USER)["files"]])
        self.assertEqual(self.storage.data, {})
        self.assertEqual(service.delete_file(USER, {"fileId": file_id})["error"]["code"], "not_found")

    def test_write_json_reads_parsed(self) -> None:
        written = service.write_file(
            USER, {"fileName": "data.json", "content": '{"a":1}', "contentType": "application/json"}
        )
        read = service.read_file(USER, {"fileId": written["file"]["id"]})
        self.assertEqual(read["format"], "json")
        self.assertIn('"a": 1', read["content"])

    def test_write_base64_binary(self) -> None:
        encoded = base64.b64encode(b"\xff\xfe\x00").decode("ascii")
        written = service.write_file(
            USER, {"fileName": "blob.bin", "content": encoded, "encoding": "base64"}
        )
        self.assertIsNone(written["error"])
        read = service.read_file(USER, {"fileId": written["file"]["id"]})
        self.assertEqual(read["format"], "base64")
        self.assertEqual(read["content"], encoded)

    def test_read_truncates_at_max_chars(self) -> None:
        written = service.write_file(USER, {"fileName": "big.txt", "content": "x" * 5_000})
        read = service.read_file(USER, {"fileId": written["file"]["id"], "maxChars": 1000})
        self.assertTrue(read["truncated"])
        self.assertEqual(len(read["content"]), 1000)

    def test_write_requires_name_and_content(self) -> None:
        self.assertEqual(service.write_file(USER, {})["error"]["code"], "invalid_request")
        self.assertEqual(
            service.write_file(USER, {"fileName": "x.txt"})["error"]["code"], "invalid_request"
        )
        self.assertEqual(
            service.write_file(USER, {"fileName": "x.txt", "content": "x", "encoding": "hex"})[
                "error"
            ]["code"],
            "invalid_request",
        )

    def test_write_enforces_file_limit(self) -> None:
        # Pre-seed the repo directly so the next write is over the count limit.
        for index in range(service.STORAGE_MAX_FILES):
            self.repo.put_file(
                self.repo.storage_item(
                    file_id=f"f{index}",
                    user_id=USER,
                    file_name="x.txt",
                    s3_key=f"storage/{USER}/f{index}/x.txt",
                    content_type="text/plain",
                    size_bytes=1,
                )
            )
        out = service.write_file(USER, {"fileName": "one-too-many.txt", "content": "x"})
        self.assertEqual(out["error"]["code"], "storage_full")

    def test_write_enforces_file_size_limit(self) -> None:
        too_big = "x" * (service.STORAGE_MAX_FILE_BYTES + 1)
        out = service.write_file(USER, {"fileName": "big.bin", "content": too_big})
        self.assertEqual(out["error"]["code"], "file_too_large")

    def test_read_missing_file(self) -> None:
        self.assertEqual(service.read_file(USER, {"fileId": "nope"})["error"]["code"], "not_found")
        self.assertEqual(service.read_file(USER, {})["error"]["code"], "invalid_request")


if __name__ == "__main__":
    unittest.main()

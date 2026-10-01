"""Unit tests for storage-file attachment resolution."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "packages"))

from agentflow import attachments  # noqa: E402


class ResolveFileIdsTests(unittest.TestCase):
    def test_saved_config_files(self) -> None:
        config = {"input": {"fileIds": ["a", "b"]}}
        self.assertEqual(attachments.resolve_file_ids({}, config), ["a", "b"])

    def test_payload_override_wins(self) -> None:
        config = {"input": {"fileIds": ["a"]}}
        self.assertEqual(attachments.resolve_file_ids({"fileIds": ["c"]}, config), ["c"])

    def test_empty_override_clears(self) -> None:
        config = {"input": {"fileIds": ["a"]}}
        self.assertEqual(attachments.resolve_file_ids({"fileIds": []}, config), [])

    def test_dedupes_and_caps(self) -> None:
        ids = ["a", "a", "b", "c", "d", "e", "f"]
        resolved = attachments.resolve_file_ids({"fileIds": ids}, {})
        self.assertEqual(len(resolved), attachments.MAX_ATTACHMENTS)
        self.assertEqual(resolved[0], "a")


class ExtractTextTests(unittest.TestCase):
    def test_plain_text(self) -> None:
        self.assertEqual(
            attachments._extract_text(b"hello world", "note.txt"), "hello world"
        )

    def test_unsupported_type_is_empty(self) -> None:
        self.assertEqual(attachments._extract_text(b"\x00\x01", "blob.bin"), "")


if __name__ == "__main__":
    unittest.main()

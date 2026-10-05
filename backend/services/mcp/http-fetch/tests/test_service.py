"""Unit tests for the http-fetch service helpers (no AWS calls).

Run with: ``make -C backend/services/mcp/http-fetch test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND / "packages"))  # shared core/data/retrieval
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # service root

from src import service  # noqa: E402


class ClampTests(unittest.TestCase):
    def test_clamp_bounds(self) -> None:
        self.assertEqual(service._clamp(None, 30, 1, 60), 30)
        self.assertEqual(service._clamp("10", 30, 1, 60), 10)
        self.assertEqual(service._clamp(999, 30, 1, 60), 60)
        self.assertEqual(service._clamp(True, 30, 1, 60), 30)


class FormatTests(unittest.TestCase):
    def test_infer_json_and_text_and_binary(self) -> None:
        self.assertEqual(service._infer_format("application/json", b"{}"), "json")
        self.assertEqual(service._infer_format("text/plain", b"hi"), "text")
        self.assertEqual(
            service._infer_format("application/octet-stream", b"\xff\xfe\x00"),
            "base64",
        )
        self.assertEqual(service._infer_format("", b"plain"), "text")


class DecodeTests(unittest.TestCase):
    def test_json_is_parsed(self) -> None:
        fmt, content, truncated = service._decode(
            "application/json", b'{"a": 1}', "auto", 1000
        )
        self.assertEqual(fmt, "json")
        self.assertEqual(content, {"a": 1})
        self.assertFalse(truncated)

    def test_text_is_truncated(self) -> None:
        fmt, content, truncated = service._decode("text/plain", b"abcdef", "text", 3)
        self.assertEqual(fmt, "text")
        self.assertEqual(content, "abc")
        self.assertTrue(truncated)

    def test_binary_is_base64(self) -> None:
        fmt, content, _ = service._decode(
            "application/octet-stream", b"\x00\x01", "base64", 1000
        )
        self.assertEqual(fmt, "base64")
        self.assertEqual(content, "AAE=")


if __name__ == "__main__":
    unittest.main()

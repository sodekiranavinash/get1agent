"""Unit tests for the http-fetch service helpers (no AWS calls).

Run with: ``make -C backend/services/http-fetch test``
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(BACKEND / "packages"))  # shared core/data/retrieval
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # service root

from src import service  # noqa: E402


class FilenameTests(unittest.TestCase):
    def test_safe_filename_strips_paths_and_symbols(self) -> None:
        self.assertEqual(service._safe_filename("../../etc/passwd"), "passwd")
        self.assertEqual(service._safe_filename("a b!c.txt"), "a b_c.txt")
        self.assertEqual(service._safe_filename(""), "file")

    def test_extension_from_content_type(self) -> None:
        self.assertEqual(service._extension_for("application/json", "https://x/y"), ".json")
        self.assertEqual(service._extension_for("text/html; charset=utf-8", "https://x/y"), ".html")
        self.assertEqual(service._extension_for("application/octet-stream", "https://x/y"), ".bin")

    def test_extension_prefers_url_path(self) -> None:
        self.assertEqual(service._extension_for("application/json", "https://x/report.csv"), ".csv")

    def test_name_from_url_derives_and_appends_extension(self) -> None:
        self.assertEqual(
            service._name_from_url("https://api.example.com/v1/users", "application/json"),
            "users.json",
        )
        self.assertEqual(
            service._name_from_url("https://example.com/", "text/html"),
            "response.html",
        )


class FormatTests(unittest.TestCase):
    def test_infer_json_and_text_and_binary(self) -> None:
        self.assertEqual(service._infer_format("application/json", b"{}"), "json")
        self.assertEqual(service._infer_format("text/plain", b"hi"), "text")
        self.assertEqual(service._infer_format("application/octet-stream", b"\xff\xfe\x00"), "base64")
        self.assertEqual(service._infer_format("", b"plain"), "text")


class ClampTests(unittest.TestCase):
    def test_clamp_bounds(self) -> None:
        self.assertEqual(service._clamp(None, 30, 1, 60), 30)
        self.assertEqual(service._clamp("10", 30, 1, 60), 10)
        self.assertEqual(service._clamp(999, 30, 1, 60), 60)
        self.assertEqual(service._clamp(True, 30, 1, 60), 30)


if __name__ == "__main__":
    unittest.main()

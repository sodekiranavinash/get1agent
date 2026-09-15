"""Unit tests for the static guard and the sandbox prelude.

Run with: ``make -C backend/services/code-interpreter test``
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from src import guard  # noqa: E402


class GuardCheckTests(unittest.TestCase):
    def test_allows_data_science_code(self) -> None:
        code = "import numpy as np\nprint(np.array([1, 2, 3]).sum())\n"
        self.assertTrue(guard.check(code).ok)

    def test_allows_os_path(self) -> None:
        self.assertTrue(guard.check("import os\nprint(os.path.join('a', 'b'))").ok)

    def test_blocks_heavy_ml_import(self) -> None:
        result = guard.check("import torch")
        self.assertFalse(result.ok)
        self.assertIn("torch", result.reason or "")

    def test_blocks_aliased_heavy_ml_import(self) -> None:
        self.assertFalse(guard.check("import torch as t").ok)

    def test_blocks_from_import(self) -> None:
        self.assertFalse(guard.check("from transformers import pipeline").ok)

    def test_blocks_network_import(self) -> None:
        self.assertFalse(guard.check("import requests").ok)

    def test_blocks_dynamic_exec(self) -> None:
        self.assertFalse(guard.check("exec('print(1)')").ok)

    def test_blocks_dunder_import(self) -> None:
        self.assertFalse(guard.check("__import__('torch')").ok)

    def test_blocks_dangerous_os_attribute(self) -> None:
        result = guard.check("import os\nos.system('ls')")
        self.assertFalse(result.ok)
        self.assertIn("os.system", result.reason or "")

    def test_blocks_pip_install_string(self) -> None:
        self.assertFalse(guard.check("print('pip install numpy')").ok)

    def test_blocks_model_download_string(self) -> None:
        self.assertFalse(guard.check("url = 'https://example.com/model.bin'").ok)

    def test_blocks_from_pretrained(self) -> None:
        self.assertFalse(
            guard.check("m = 'x'\nm.from_pretrained('bert-base')").ok
        )

    def test_blocks_syntax_error(self) -> None:
        result = guard.check("def f(:")
        self.assertFalse(result.ok)
        self.assertIn("Syntax", result.reason or "")

    def test_blocks_oversized_code(self) -> None:
        self.assertFalse(guard.check("x = 1\n" * 1000, max_bytes=100).ok)

    def test_allowed_modules_override(self) -> None:
        self.assertTrue(guard.check("import torch", allowed_extra="torch").ok)

    def test_blocked_modules_override(self) -> None:
        self.assertFalse(guard.check("import numpy", blocked_extra="numpy").ok)


class PreludeTests(unittest.TestCase):
    def test_prelude_blocks_import_at_runtime(self) -> None:
        script = guard.prelude() + "\nimport subprocess\n"
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("blocked by policy", proc.stderr)

    def test_prelude_allows_safe_import(self) -> None:
        script = guard.prelude() + "\nimport json\nprint(json.dumps({'ok': True}))\n"
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn('"ok": true', proc.stdout)


if __name__ == "__main__":
    unittest.main()

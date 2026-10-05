"""Unit tests for the static guard and the sandbox prelude.

Run with: ``make -C backend/services/mcp/code-interpreter test``
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))
# The guard now lives in the shared `core` package, bundled at deploy time.
sys.path.insert(0, str(SRC.parents[1] / "packages"))

from core.sandbox import guard  # noqa: E402


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

    def test_allows_urllib_parse(self) -> None:
        self.assertTrue(guard.check("import urllib.parse").ok)
        self.assertTrue(guard.check("from urllib.parse import urljoin").ok)

    def test_blocks_urllib_request(self) -> None:
        self.assertFalse(guard.check("import urllib.request").ok)
        self.assertFalse(guard.check("from urllib.request import urlopen").ok)

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

    def test_blocks_download_command_string(self) -> None:
        self.assertFalse(guard.check("cmd = 'git clone https://github.com/x/y'").ok)

    def test_allows_bare_url_literal(self) -> None:
        # A parser may carry an example/default URL in a docstring or constant.
        self.assertTrue(guard.check("base = 'https://example.com'\nprint(base)").ok)

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

    def test_prelude_allows_urllib_parse(self) -> None:
        script = (
            guard.prelude()
            + "\nimport urllib.parse\n"
            + "print(urllib.parse.urljoin('https://a.com/x/', '../b'))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("https://a.com/b", proc.stdout)

    def test_prelude_blocks_urllib_request(self) -> None:
        script = guard.prelude() + "\nimport urllib.request\n"
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("blocked by policy", proc.stderr)


class NetworkPreludeTests(unittest.TestCase):
    """The network-enabled sandbox (`allow_network`) used by the MCP Builder."""

    def test_check_allows_http_stack(self) -> None:
        for code in (
            "import requests",
            "import urllib.request",
            "import httpx",
            "import socket",
        ):
            self.assertTrue(guard.check(code, allow_network=True).ok, code)

    def test_check_still_blocks_heavy_and_dangerous(self) -> None:
        for code in (
            "import torch",
            "import subprocess",
            "import ctypes",
            "exec('print(1)')",
            "x = 'curl https://a'",
        ):
            self.assertFalse(guard.check(code, allow_network=True).ok, code)

    def test_prelude_blocks_private_address(self) -> None:
        script = (
            guard.prelude(allow_network=True)
            + "\nimport socket\n"
            + "s = socket.socket()\n"
            + "try:\n"
            + "    s.connect(('127.0.0.1', 9))\n"
            + "except PermissionError:\n"
            + "    print('blocked')\n"
        )
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertIn("blocked", proc.stdout)

    def test_prelude_enforces_connection_cap(self) -> None:
        script = (
            guard.prelude(allow_network=True, max_connections=1)
            + "\nimport socket\n"
            + "msgs = []\n"
            + "for _ in range(2):\n"
            + "    s = socket.socket()\n"
            + "    try:\n"
            + "        s.connect(('127.0.0.1', 9))\n"
            + "    except PermissionError as exc:\n"
            + "        msgs.append(str(exc))\n"
            + "    finally:\n"
            + "        s.close()\n"
            + "print('|'.join(msgs))\n"
        )
        proc = subprocess.run(
            [sys.executable, "-I", "-c", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertIn("limit reached", proc.stdout)


if __name__ == "__main__":
    unittest.main()

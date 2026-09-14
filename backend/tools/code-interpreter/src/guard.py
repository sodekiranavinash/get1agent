"""Static + runtime policy guard for LLM-generated Python.

The AgentCore Code Interpreter already runs each session in an isolated microVM
(its own CPU, memory and filesystem). This guard is a defence-in-depth and
abuse/cost-control layer on top of that isolation. It blocks:

* OS/shell escape and process spawning (``subprocess``, ``pty``, ``ctypes``,
  dangerous ``os.*`` calls);
* network egress and cloud SDKs (so a user cannot download models or data);
* dynamic code execution (``exec``/``eval``/``importlib``);
* heavy machine-learning frameworks (``torch``, ``tensorflow``, ...).

Two layers enforce the policy:

* ``check`` — a static AST/literal pass run before any code reaches AWS. A
  blocked snippet never starts a sandbox session.
* ``prelude`` — a small Python prologue prepended to every execution that
  installs a ``sys.addaudithook`` inside the sandbox, so a bypassed static
  check still fails at import/exec time. Audit hooks cannot be removed once
  installed.

This is intentionally conservative. A determined attacker can still bypass a
Python-level check; the microVM remains the real isolation boundary.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass

# Root modules that are blocked outright at import time. Keep this list focused
# on abuse/cost control: anything that can spawn processes, reach the network,
# download models, or execute code dynamically.
DENY_MODULES: frozenset[str] = frozenset(
    {
        # Process / native code
        "subprocess",
        "pty",
        "ctypes",
        "cffi",
        "multiprocessing",
        "resource",
        # Network + cloud SDKs
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib2",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "poplib",
        "imaplib",
        "telnetlib",
        "xmlrpc",
        "websocket",
        "websockets",
        "paramiko",
        "boto3",
        "botocore",
        "sagemaker",
        "redis",
        "pymongo",
        "psycopg2",
        "pymysql",
        # Dynamic code
        "importlib",
        "runpy",
        "code",
        "codeop",
        "compileall",
        "pickle",
        "marshal",
        "dill",
        "cloudpickle",
        "shelve",
        "imp",
        # Heavy ML / model downloads
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "keras",
        "jax",
        "flax",
        "transformers",
        "datasets",
        "diffusers",
        "sentence_transformers",
        "sentencepiece",
        "tokenizers",
        "huggingface_hub",
        "accelerate",
        "peft",
        "trl",
        "bitsandbytes",
        "deepspeed",
        "onnx",
        "onnxruntime",
        "mxnet",
        "paddle",
        "theano",
        "caffe2",
        "sklearn",
        "scikit_learn",
        "xgboost",
        "lightgbm",
        "catboost",
        "spacy",
        "gensim",
        "nltk",
        "timm",
        "open_clip",
        "cv2",
    }
)

# Calls whose bare name is always blocked.
DENY_CALLS: frozenset[str] = frozenset({"__import__", "exec", "eval", "compile"})

# Dotted call targets that are blocked. A prefix match covers e.g. ``os.execv``.
DENY_ATTRS: tuple[str, ...] = (
    "os.system",
    "os.popen",
    "os.exec",
    "os.spawn",
    "os.fork",
    "os.forkpty",
    "os.kill",
    "os.killpg",
    "os.setuid",
    "os.setgid",
    "os.setreuid",
    "os.setregid",
    "os.chroot",
    "os.putenv",
    "os.unsetenv",
    "os.remove",
    "os.unlink",
    "os.rmdir",
    "os.removedirs",
    "shutil.rmtree",
    "pickle.loads",
    "pickle.load",
    "marshal.loads",
    "marshal.load",
    "importlib.import_module",
    "importlib.reload",
    "importlib.__import__",
    "builtins.__import__",
    "builtins.exec",
    "builtins.eval",
    "builtins.compile",
    "ctypes",
    "socket",
    "subprocess",
    "pty",
    "multiprocessing",
)

# Download / install / model-fetch markers scanned in string literals and the
# raw source (so concatenated or f-string URLs are still caught).
_DOWNLOAD_RE = re.compile(
    r"("
    r"pip3?\s+install|python\s+-m\s+pip|conda\s+install|"
    r"from_pretrained|torch\.hub|load_dataset|huggingface|"
    r"wget\s|curl\s|git\s+clone|"
    r"https?://|ftp://"
    r")",
    re.IGNORECASE,
)

# Audit events blocked at runtime inside the sandbox.
DENY_AUDIT_EVENTS: tuple[str, ...] = (
    "os.system",
    "subprocess.Popen",
    "socket.connect",
    "socket.bind",
    "socket.getaddrinfo",
    "ctypes.dlopen",
    "ctypes.dlsym",
)


@dataclass(frozen=True)
class GuardResult:
    """Outcome of a static policy check."""

    ok: bool
    reason: str | None = None
    detail: str | None = None


def _split_modules(raw: str) -> set[str]:
    return {part.strip().lower() for part in (raw or "").split(",") if part.strip()}


def deny_set(blocked_extra: str = "", allowed_extra: str = "") -> frozenset[str]:
    """The effective deny set: built-ins + ``BLOCKED_MODULES`` - ``ALLOWED_MODULES``."""
    deny = set(DENY_MODULES)
    deny |= _split_modules(blocked_extra)
    deny -= _split_modules(allowed_extra)
    return frozenset(deny)


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    current: ast.AST | None = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _import_roots(tree: ast.AST) -> list[tuple[str, int]]:
    roots: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.append((alias.name.split(".")[0].lower(), node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                roots.append((node.module.split(".")[0].lower(), node.lineno))
    return roots


def check(
    code: str,
    *,
    max_bytes: int = 102_400,
    blocked_extra: str = "",
    allowed_extra: str = "",
) -> GuardResult:
    """Run the static policy pass over ``code``."""
    if not isinstance(code, str) or not code.strip():
        return GuardResult(False, "Empty code", "code must be a non-empty string")
    if len(code.encode("utf-8")) > max_bytes:
        return GuardResult(
            False,
            "Code is too large",
            f"code exceeds the {max_bytes} byte limit",
        )

    try:
        tree = ast.parse(code, mode="exec")
    except SyntaxError as exc:
        return GuardResult(
            False,
            "Syntax error",
            f"line {exc.lineno}: {exc.msg}",
        )

    deny = deny_set(blocked_extra, allowed_extra)
    for root, lineno in _import_roots(tree):
        if root in deny:
            return GuardResult(
                False,
                f"Import of '{root}' is blocked by policy",
                f"line {lineno}",
            )

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in DENY_CALLS:
                return GuardResult(
                    False,
                    f"Call to '{func.id}' is blocked by policy",
                    f"line {node.lineno}",
                )
            dotted = _dotted(func)
            if dotted:
                for prefix in DENY_ATTRS:
                    if dotted == prefix or dotted.startswith(prefix + "."):
                        return GuardResult(
                            False,
                            f"Call to '{dotted}' is blocked by policy",
                            f"line {node.lineno}",
                        )

    match = _DOWNLOAD_RE.search(code)
    if match:
        return GuardResult(
            False,
            "Downloading files, installing packages or fetching models is blocked",
            f"matched {match.group(0).strip()!r}",
        )

    return GuardResult(True)


def prelude(*, blocked_extra: str = "", allowed_extra: str = "") -> str:
    """Return the sandbox prologue that installs the runtime audit hook.

    Prepended to every execution. It is idempotent: the ``sys`` flag prevents a
    duplicate hook when the same sandbox is reused across calls.
    """
    deny = sorted(deny_set(blocked_extra, allowed_extra))
    events = sorted(DENY_AUDIT_EVENTS)
    return (
        "import sys as _g1_sys\n"
        "if not getattr(_g1_sys, '_get1agent_guard', False):\n"
        "    _g1_sys._get1agent_guard = True\n"
        f"    _g1_deny = frozenset({deny!r})\n"
        f"    _g1_events = frozenset({events!r})\n"
        "    def _g1_hook(_g1_event, _g1_args):\n"
        "        if _g1_event == 'import':\n"
        "            _g1_name = str(_g1_args[0]) if _g1_args else ''\n"
        "            _g1_root = _g1_name.split('.')[0]\n"
        "            if _g1_root in _g1_deny:\n"
        "                raise PermissionError(\n"
        "                    \"import of '\" + _g1_root + \"' is blocked by policy\"\n"
        "                )\n"
        "        elif _g1_event in _g1_events:\n"
        "            raise PermissionError(\n"
        "                \"operation '\" + _g1_event + \"' is blocked by policy\"\n"
        "            )\n"
        "    _g1_sys.addaudithook(_g1_hook)\n"
    )

"""Static + runtime policy guard for LLM-generated Python.

The AgentCore Code Interpreter already runs each session in an isolated microVM
(its own CPU, memory and filesystem). This guard is a defence-in-depth and
abuse/cost-control layer on top of that isolation. It blocks:

* OS/shell escape and process spawning (``subprocess``, ``pty``, ``ctypes``,
  dangerous ``os.*`` calls);
* network egress and cloud SDKs (so a user cannot download models or data),
  unless the sandbox is explicitly granted ``allow_network`` — in which case
  only the HTTP(S) stack is unblocked and every outbound connection is still
  counted and range-checked against private/reserved addresses;
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

# Submodules of otherwise-blocked packages that are safe to import.
# ``urllib.parse`` is pure string manipulation (no sockets) — the one piece of
# ``urllib`` a parser legitimately needs (e.g. ``urljoin`` for relative links).
# Every other ``urllib`` submodule (``request``/``error``/…) stays blocked.
ALLOW_MODULES: frozenset[str] = frozenset({"urllib.parse"})

# Network modules that are lifted from the deny set when a sandbox is explicitly
# granted internet access (``allow_network``). Only the HTTP(S) stack is
# unblocked; other protocols stay denied so the surface stays focused on calling
# web APIs. Even when allowed, outbound connections are counted and
# private/loopback/link-local/reserved destinations are refused at runtime.
NETWORK_MODULES: frozenset[str] = frozenset(
    {
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib2",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "websocket",
        "websockets",
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

# Download / install / model-fetch markers scanned in the raw source. Network
# *imports* (``urllib.request``, ``requests``, ``http``, ``socket``) and the
# runtime socket audit hook already prevent egress, so a bare URL string literal
# is NOT blocked — a parser may legitimately carry an example or default URL in
# a docstring. Only explicit download/install commands and model-fetch markers
# are blocked here.
_DOWNLOAD_RE = re.compile(
    r"("
    r"pip3?\s+install|python\s+-m\s+pip|conda\s+install|"
    r"from_pretrained|torch\.hub|load_dataset|huggingface|"
    r"wget\s|curl\s|git\s+clone"
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


def deny_set(
    blocked_extra: str = "",
    allowed_extra: str = "",
    *,
    allow_network: bool = False,
) -> frozenset[str]:
    """The effective deny set: built-ins + ``BLOCKED_MODULES`` - ``ALLOWED_MODULES``.

    ``allow_network`` lifts the HTTP(S) stack (``NETWORK_MODULES``) from the deny
    set so a tool may call web APIs; every other abuse/cost control (process
    spawning, native code, dynamic code, heavy ML, cloud SDKs) stays in place.
    """
    deny = set(DENY_MODULES)
    if allow_network:
        deny -= NETWORK_MODULES
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


def _import_names(tree: ast.AST) -> list[tuple[str, int]]:
    """Full dotted module names imported by the code, with line numbers."""
    names: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append((alias.name.lower(), node.lineno))
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            if node.module:
                names.append((node.module.lower(), node.lineno))
    return names


def check(
    code: str,
    *,
    max_bytes: int = 102_400,
    blocked_extra: str = "",
    allowed_extra: str = "",
    allow_network: bool = False,
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

    deny = deny_set(blocked_extra, allowed_extra, allow_network=allow_network)
    for name, lineno in _import_names(tree):
        root = name.split(".")[0]
        if name in ALLOW_MODULES:
            continue
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


def prelude(
    *,
    blocked_extra: str = "",
    allowed_extra: str = "",
    allow_network: bool = False,
    max_connections: int = 25,
) -> str:
    """Return the sandbox prologue that installs the runtime audit hook.

    Prepended to every execution. It is idempotent: the ``sys`` flag prevents a
    duplicate hook when the same sandbox is reused across calls, and the
    per-execution connection counter is reset at the top of every run.

    When ``allow_network`` is true the socket block is lifted, but outbound
    connections are still counted (``max_connections`` per execution) and
    private/loopback/link-local/reserved destinations are refused.
    """
    deny = sorted(deny_set(blocked_extra, allowed_extra, allow_network=allow_network))
    allow = sorted(name.lower() for name in ALLOW_MODULES)
    # Parent packages of an allowed submodule must load too (importing
    # ``urllib.parse`` first imports ``urllib``), but the submodule itself is
    # what gets allow-listed, so ``urllib.request`` is still denied.
    allow_parents = sorted(
        {name.rsplit(".", 1)[0] for name in allow if "." in name}
    )

    if allow_network:
        # Socket events are no longer denied outright; they are counted and
        # range-checked instead. Process/native-code guards stay.
        events = sorted(
            {"os.system", "subprocess.Popen", "ctypes.dlopen", "ctypes.dlsym"}
        )
        net_events = sorted({"socket.connect", "socket.sendto", "socket.sendmsg"})
        extra = (
            f"    _g1_net_events = frozenset({net_events!r})\n"
            f"    _g1_max_conn = {max(1, int(max_connections))}\n"
            "    import ipaddress as _g1_ipaddress\n"
            "    def _g1_conn_addr(_g1_args):\n"
            "        for _g1_a in _g1_args:\n"
            "            if isinstance(_g1_a, (tuple, list)) and _g1_a and isinstance(_g1_a[0], str):\n"
            "                return _g1_a[0]\n"
            "            if isinstance(_g1_a, str):\n"
            "                return _g1_a\n"
            "        return None\n"
            "    def _g1_blocked_ip(_g1_host):\n"
            "        try:\n"
            "            _g1_addr = _g1_ipaddress.ip_address(_g1_host)\n"
            "        except ValueError:\n"
            "            return True\n"
            "        if getattr(_g1_addr, 'ipv4_mapped', None):\n"
            "            _g1_addr = _g1_addr.ipv4_mapped\n"
            "        return (_g1_addr.is_private or _g1_addr.is_loopback or _g1_addr.is_link_local or _g1_addr.is_multicast or _g1_addr.is_reserved or _g1_addr.is_unspecified)\n"
        )
        body = (
            "    def _g1_hook(_g1_event, _g1_args):\n"
            "        if _g1_event == 'import':\n"
            "            _g1_name = str(_g1_args[0]).lower() if _g1_args else ''\n"
            "            _g1_root = _g1_name.split('.')[0]\n"
            "            if _g1_name in _g1_allow or _g1_name in _g1_allow_parents:\n"
            "                return\n"
            "            if _g1_root in _g1_deny:\n"
            "                raise PermissionError('import of ' + _g1_root + ' is blocked by policy')\n"
            "        elif _g1_event in _g1_net_events:\n"
            "            _g1_run = getattr(_g1_sys, '_g1_run', None)\n"
            "            if _g1_run is not None:\n"
            "                _g1_run['n'] = _g1_run.get('n', 0) + 1\n"
            "                if _g1_run['n'] > _g1_max_conn:\n"
            "                    raise PermissionError('network connection limit reached for this run')\n"
            "            _g1_host = _g1_conn_addr(_g1_args)\n"
            "            if _g1_host is not None and _g1_blocked_ip(_g1_host):\n"
            "                raise PermissionError('connections to private, loopback or reserved addresses are blocked by policy')\n"
            "        elif _g1_event in _g1_events:\n"
            "            raise PermissionError('operation ' + _g1_event + ' is blocked by policy')\n"
        )
    else:
        events = sorted(DENY_AUDIT_EVENTS)
        extra = ""
        body = (
            "    def _g1_hook(_g1_event, _g1_args):\n"
            "        if _g1_event == 'import':\n"
            "            _g1_name = str(_g1_args[0]).lower() if _g1_args else ''\n"
            "            _g1_root = _g1_name.split('.')[0]\n"
            "            if _g1_name in _g1_allow or _g1_name in _g1_allow_parents:\n"
            "                return\n"
            "            if _g1_root in _g1_deny:\n"
            "                raise PermissionError('import of ' + _g1_root + ' is blocked by policy')\n"
            "        elif _g1_event in _g1_events:\n"
            "            raise PermissionError('operation ' + _g1_event + ' is blocked by policy')\n"
        )

    return (
        "import sys as _g1_sys\n"
        "_g1_sys._g1_run = {'n': 0}\n"
        "if not getattr(_g1_sys, '_get1agent_guard', False):\n"
        "    _g1_sys._get1agent_guard = True\n"
        f"    _g1_deny = frozenset({deny!r})\n"
        f"    _g1_events = frozenset({events!r})\n"
        f"    _g1_allow = frozenset({allow!r})\n"
        f"    _g1_allow_parents = frozenset({allow_parents!r})\n"
        + extra
        + body
        + "    _g1_sys.addaudithook(_g1_hook)\n"
    )

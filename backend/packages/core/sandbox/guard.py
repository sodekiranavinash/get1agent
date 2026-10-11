"""Static + runtime policy guard for LLM-generated Python.

The AgentCore Code Interpreter already runs each session in an isolated microVM
(its own CPU, memory and filesystem), so this guard is a lightweight
**abuse/cost-control** layer on top of that isolation. It blocks exactly one
class of imports:

* heavy machine-learning frameworks (``torch``, ``tensorflow``, ``transformers``,
  ``sklearn``, ...) — so a tool cannot pull a multi-GB model or burn the run
  budget on ML.

Everything else is permitted: process spawning (``subprocess``), native code
(``ctypes``), dynamic code (``eval``/``exec``/``importlib``), arbitrary
third-party packages and package installation. The microVM remains the real
isolation boundary.

Network is governed separately by ``allow_network``:

* when the sandbox is granted internet access, only the HTTP(S) stack is
  reachable and every outbound connection is counted (``max_connections``) and
  range-checked against private/loopback/link-local/reserved/metadata
  addresses;
* when it is not (the admin kill switch is off, or the calculation-only
  ``code-interpreter`` tool), the network stack is denied outright.

Two layers enforce the policy:

* ``check`` — a static AST pass run before any code reaches AWS.
* ``prelude`` — a small Python prologue prepended to every execution that
  installs a ``sys.addaudithook`` inside the sandbox, so a bypassed static
  check still fails at import/connect time. Audit hooks cannot be removed once
  installed.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# The only blocked family of modules: heavy machine-learning frameworks. They
# stay blocked on purpose — not for isolation, but to stop a tool downloading a
# model or exhausting the run budget on ML.
ML_MODULES: frozenset[str] = frozenset(
    {
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

# Public alias for the blocked-module set.
DENY_MODULES: frozenset[str] = ML_MODULES

# The HTTP(S) stack. Not blocked when network is allowed; withheld (as a group)
# when the sandbox is offline so an offline sandbox cannot reach out at all.
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

# Socket audit events refused when the sandbox is offline (network kill switch).
_OFFLINE_AUDIT_EVENTS: tuple[str, ...] = (
    "socket.connect",
    "socket.bind",
    "socket.getaddrinfo",
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
    """The effective deny set: heavy-ML + ``BLOCKED_MODULES`` - ``ALLOWED_MODULES``.

    When the sandbox is offline (``allow_network`` false) the HTTP(S) stack is
    added so nothing can reach the network; every other class of module is
    permitted.
    """
    deny = set(ML_MODULES)
    if not allow_network:
        deny |= NETWORK_MODULES
    deny |= _split_modules(blocked_extra)
    deny -= _split_modules(allowed_extra)
    return frozenset(deny)


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
        if root in deny:
            return GuardResult(
                False,
                f"Import of '{root}' is blocked by policy",
                f"line {lineno}",
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

    Only the heavy-ML imports are refused. When ``allow_network`` is true,
    outbound connections are counted (``max_connections`` per execution) and
    private/loopback/link-local/reserved destinations are refused; when it is
    false, the socket audit events are refused outright.
    """
    deny = sorted(deny_set(blocked_extra, allowed_extra, allow_network=allow_network))

    if allow_network:
        # Nothing but imports is refused; sockets are counted and range-checked.
        events: tuple[str, ...] = ()
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
        )
    else:
        events = tuple(sorted(_OFFLINE_AUDIT_EVENTS))
        extra = ""
        body = (
            "    def _g1_hook(_g1_event, _g1_args):\n"
            "        if _g1_event == 'import':\n"
            "            _g1_name = str(_g1_args[0]).lower() if _g1_args else ''\n"
            "            _g1_root = _g1_name.split('.')[0]\n"
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
        + extra
        + body
        + "    _g1_sys.addaudithook(_g1_hook)\n"
    )

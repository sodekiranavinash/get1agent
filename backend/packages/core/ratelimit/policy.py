"""Rate-limit policies: which endpoint gets which windows.

A **policy** is an ordered list of windows (shortest first) applied to one
identity — the caller's internal ``userId``, the AI Assistant's hashed guest
bucket, or ``global`` for a shared account-level cap such as Bedrock's
requests-per-minute quota.

Two things live here:

* :data:`DEFAULT_POLICIES` — the limits in force out of the box, one entry per
  protected surface. They are deliberately *not* one flat number: an agent run,
  a custom-tool test and a document upload cost wildly different amounts, so
  each gets its own shape (a per-minute burst plus an hourly/daily ceiling).
* :func:`for_route` — the mapping from ``(method, path segments)`` to a policy,
  used by the API middleware. **Reads are never limited** — the point of the
  limiter is to bound work that *spends* something (a model call, an upload, a
  sandbox run), and leaving GETs out also keeps the Redis op count low, which
  matters on a small managed instance.

Any policy can be overridden at runtime with a ``RATELIMIT_POLICY`` JSON object
(e.g. ``{"evals.run": [[10, 3600]], "api.default": []}``); an empty list means
"no cap". Env is the escape hatch the platform already uses everywhere else
(``core.network``, ``core.ratelimit_bedrock``), and it keeps an incident fix to
a variable change rather than a deploy.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

SECOND = 1
MINUTE = 60
BURST = 180
HOUR = 3600
DAY = 86_400

_WINDOW_NAMES = {SECOND: "second", MINUTE: "minute", BURST: "burst", HOUR: "hour", DAY: "day"}


@dataclass(frozen=True)
class Window:
    """One limit inside a policy."""

    name: str
    limit: int
    seconds: int

    @property
    def window_ms(self) -> int:
        return max(int(self.seconds), 1) * 1000


@dataclass(frozen=True)
class Policy:
    """An ordered set of windows enforced against one identity."""

    id: str
    windows: tuple[Window, ...]
    description: str = ""

    @property
    def tightest(self) -> Window | None:
        """The window a caller is most likely to meet (shortest first)."""
        return self.windows[0] if self.windows else None


def window_name(seconds: int) -> str:
    return _WINDOW_NAMES.get(int(seconds), f"{int(seconds)}s")


def _make(pairs: list[tuple[int, int]], *, description: str = "") -> tuple[Window, ...]:
    """``[(limit, seconds)]`` -> windows, shortest first, uniquely named."""
    windows: list[Window] = []
    seen: dict[str, int] = {}
    for limit, seconds in sorted(pairs, key=lambda pair: pair[1]):
        if limit <= 0 or seconds <= 0:
            continue
        name = window_name(seconds)
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            name = f"{name}{seen[name]}"
        windows.append(Window(name=name, limit=int(limit), seconds=int(seconds)))
    return tuple(windows)


#: The default shape of the platform: one entry per protected surface.
DEFAULTS: dict[str, tuple[list[tuple[int, int]], str]] = {
    # A generous floor for any mutating call not named below. It exists so a
    # runaway client is bounded, not so it is throttled in normal use.
    "api.default": ([(600, MINUTE), (10_000, HOUR)], "Any mutating API call"),
    # Agent runs are the most expensive request on the platform: a plan, several
    # model calls and tool calls. The per-minute cap stops a loop; the hourly cap
    # bounds a script; the daily cap bounds a patient one.
    "agent.session": ([(10, MINUTE), (120, HOUR)], "Launch an agent-run MicroVM session"),
    # Documents: presign + complete + delete. Uploading is bandwidth-bound and
    # per-user, so an hourly ceiling is the useful one.
    "knowledge.write": ([(300, HOUR), (2000, DAY)], "Upload/change knowledge-base documents"),
    # MCP Builder generation spends a large Bedrock call per turn.
    "custom-tools.generate": ([(30, HOUR), (200, DAY)], "MCP Builder tool generation"),
    "custom-tools.test": ([(30, MINUTE), (300, HOUR)], "MCP Builder tool test run"),
    # Evaluations run many turns per run; they are the heaviest platform spend.
    "evals.run": ([(10, HOUR), (50, DAY)], "Start an evaluation run"),
    "playground.run": ([(120, HOUR)], "Playground replay / judge"),
    "vault.test": ([(20, MINUTE), (120, HOUR)], "Test a provider key against its API"),
    "mcp.call": ([(120, MINUTE), (2000, HOUR)], "Call a remote MCP tool"),
    "guardrail.test": ([(60, HOUR)], "Apply a guardrail to sample text"),
    "storage.upload": ([(120, HOUR)], "Upload a storage file"),
    "skills.import": ([(30, HOUR)], "Import a skill from a repository or registry"),
    # Web search / code interpreter go through the same MCP call path, so the
    # per-tool windows above are the useful ones; this bounds the aggregate.
    "tool.call": ([(240, MINUTE), (4000, HOUR)], "Agent tool calls (aggregate)"),
}

#: AI Assistant windows come from its admin-editable settings, not from here —
#: only the policy *ids* are shared so the usage endpoint can report them.
AI_ASSISTANT_KINDS: tuple[str, ...] = ("ai-assistant-burst", "ai-assistant-hour", "ai-assistant-day")

#: ``(method, path segments, policy)``. ``*`` matches exactly one segment; a
#: shorter tuple matches as a prefix. First match wins, so the specific rules
#: must precede ``api.default``.
ROUTE_RULES: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("POST", ("v1", "agent-run", "session"), "agent.session"),
    ("POST", ("v1", "custom-tools", "generate"), "custom-tools.generate"),
    ("POST", ("v1", "custom-tools", "sessions", "*", "turn"), "custom-tools.generate"),
    ("POST", ("v1", "custom-tools", "test"), "custom-tools.test"),
    ("POST", ("v1", "evals", "runs"), "evals.run"),
    ("POST", ("v1", "lab", "playground", "run"), "playground.run"),
    ("POST", ("v1", "lab", "playground", "judge"), "playground.run"),
    ("POST", ("v1", "vault", "test"), "vault.test"),
    ("POST", ("v1", "vault", "secrets", "*", "test"), "vault.test"),
    ("POST", ("v1", "vault", "models"), "vault.test"),
    ("POST", ("v1", "guardrails", "test"), "guardrail.test"),
    ("POST", ("v1", "mcp", "connections", "*", "call"), "mcp.call"),
    ("POST", ("v1", "mcp", "connections", "*", "token"), "mcp.call"),
    ("POST", ("v1", "storage", "presign"), "storage.upload"),
    ("POST", ("v1", "storage", "files", "*", "complete"), "storage.upload"),
    ("POST", ("v1", "agent-skills", "import"), "skills.import"),
    ("POST", ("v1", "agent-skills", "import", "preview"), "skills.import"),
    ("POST", ("v1", "agent-skills", "resolve-repo"), "skills.import"),
    # Document writes. ``POST /v1/knowledge-bases/…/documents/presign`` is the
    # shape the SPA uses; ``inline`` and ``complete`` are the other two writers.
    ("POST", ("v1", "knowledge-bases", "*", "documents", "*"), "knowledge.write"),
    ("DELETE", ("v1", "knowledge-bases", "*", "documents", "*"), "knowledge.write"),
)

#: Prefixes that must never be limited here (public or already bounded).
EXEMPT_PREFIXES: tuple[tuple[str, ...], ...] = (
    ("v1", "traces"),
    ("v1", "ai-assistant"),
)

#: Methods that never consume a slot — the limiter bounds spending, not reads.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


def policy_id_for_route(method: str, segments: list[str]) -> str:
    """Resolve a request to a policy id, or ``""`` when it is not limited."""
    verb = (method or "GET").upper()
    if verb in SAFE_METHODS:
        return ""
    for prefix in EXEMPT_PREFIXES:
        if tuple(segments[: len(prefix)]) == prefix:
            return ""
    for rule_method, rule_path, rule_policy in ROUTE_RULES:
        if verb != rule_method or len(segments) < len(rule_path):
            continue
        if all(
            expected == "*" or segments[index] == expected
            for index, expected in enumerate(rule_path)
        ):
            return rule_policy
    return "api.default"


def _overrides() -> dict[str, list[tuple[int, int]]]:
    raw = (os.environ.get("RATELIMIT_POLICY") or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    out: dict[str, list[tuple[int, int]]] = {}
    for key, value in parsed.items():
        if not isinstance(value, list):
            continue
        pairs: list[tuple[int, int]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            try:
                pairs.append((int(item[0]), int(item[1])))
            except (TypeError, ValueError):
                continue
        out[str(key)] = pairs
    return out


def get(policy_id: str) -> Policy | None:
    """The effective policy for ``policy_id`` (env override, then defaults)."""
    if not policy_id:
        return None
    overrides = _overrides()
    if policy_id in overrides:
        return Policy(id=policy_id, windows=_make(overrides[policy_id]))
    entry = DEFAULTS.get(policy_id)
    if entry is None:
        return None
    pairs, description = entry
    return Policy(id=policy_id, windows=_make(pairs), description=description)


def all_policies() -> list[Policy]:
    """Every configured policy, for the usage surfaces."""
    policies: list[Policy] = []
    for policy_id in sorted(set(DEFAULTS) | set(_overrides())):
        resolved = get(policy_id)
        if resolved is not None:
            policies.append(resolved)
    return policies

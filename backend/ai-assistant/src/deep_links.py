"""Resolve where a feature lives, and validate a deep link before offering it.

A wrong link is worse than no link: AI Assistant telling someone to "open the Agent
builder" and then 404ing destroys trust in every other answer. So the allow-list
is **generated from the real route table** (``App.tsx``) at corpus-build time and
imported here, rather than guessed or parsed at run time.

The widget only ever offers ``public`` and ``user`` routes. Admin routes are
present in the catalogue (the admin page's AI Assistant can explain them) but are never
handed to a non-admin caller.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_HERE = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Feature:
    path: str
    title: str
    group: str = ""
    audience: str = "user"
    note: str = ""

    @property
    def label(self) -> str:
        return self.title or self.path


def _load_json(name: str) -> dict[str, Any]:
    path = _HERE / name
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_CATALOGUE: dict[str, Any] | None = None


def catalogue() -> dict[str, Any]:
    """The generated route catalogue (empty when the corpus was never built)."""
    global _CATALOGUE
    if _CATALOGUE is None:
        _CATALOGUE = _load_json("features.json")
        if os.environ.get("AI_ASSISTANT_FEATURES_JSON"):
            _CATALOGUE = _load_json(os.environ["AI_ASSISTANT_FEATURES_JSON"]) or _CATALOGUE
    return _CATALOGUE


def refresh() -> None:
    """Drop the cached catalogue (tests, and a rebuilt corpus)."""
    global _CATALOGUE
    _CATALOGUE = None


def _static_paths() -> set[str]:
    return {str(path) for path in catalogue().get("paths") or []}


def _dynamic_prefixes() -> list[str]:
    return [str(prefix) for prefix in catalogue().get("dynamicPrefixes") or []]


def _features() -> list[Feature]:
    rows = catalogue().get("features") or []
    out: list[Feature] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("path"):
            continue
        out.append(
            Feature(
                path=str(row["path"]),
                title=str(row.get("title") or ""),
                group=str(row.get("group") or ""),
                audience=str(row.get("audience") or "user"),
                note=str(row.get("note") or ""),
            )
        )
    return out


def _doc_anchors() -> list[str]:
    return [str(anchor) for anchor in catalogue().get("docAnchors") or []]


def is_valid(path: str, *, allow_admin: bool = False) -> bool:
    """Whether ``path`` is a real in-app route this caller may open."""
    if not path:
        return False
    cleaned = path.split("#", 1)[0].split("?", 1)[0]
    if not cleaned.startswith("/"):
        return False
    if cleaned.startswith("/admin") and not allow_admin:
        return False

    # A `/docs#<section>` link is valid only when the Documentation page renders
    # that section. Checked *before* the static-path shortcut below, which would
    # otherwise accept any fragment at all, because `/docs` is of course a real
    # route. The catalogue lists the anchors, so one that exists nowhere in the DOM
    # is refused and the citation falls back to a link that works. Without the list
    # (an older catalogue) keep the old permissive answer rather than breaking
    # every docs link.
    if cleaned == "/docs":
        fragment = path.partition("#")[2]
        if not fragment:
            return True
        anchors = _doc_anchors()
        return not anchors or fragment in anchors

    if cleaned in _static_paths():
        return True
    # A dynamic route is valid once the caller supplies a concrete id.
    for prefix in _dynamic_prefixes():
        if cleaned == prefix or cleaned.startswith(prefix + "/"):
            return True

    # An unknown path may still be a real route the catalogue missed; refuse
    # rather than risk a dead link.
    return False


def normalize(path: str, *, allow_admin: bool = False) -> str:
    """Return a safe, canonical path — or an empty string when it is not real."""
    if not path:
        return ""
    cleaned = str(path).strip()
    if not cleaned.startswith("/"):
        # Accept a bare page name and look it up by label.
        found = find(cleaned, allow_admin=allow_admin)
        return found.path if found else ""
    if is_valid(cleaned, allow_admin=allow_admin):
        # Preserve a docs anchor, drop a query string (it is not stable).
        anchor = cleaned.split("#", 1)[1] if "#" in cleaned else ""
        base = cleaned.split("#", 1)[0].split("?", 1)[0]
        return f"{base}#{anchor}" if anchor else base
    return ""


def find(query: str, *, allow_admin: bool = False) -> Feature | None:
    """Find the feature a user means, by label, group, or path fragment."""
    if not query:
        return None
    needle = re.sub(r"[^a-z0-9]+", " ", query.lower()).strip()
    if not needle:
        return None

    candidates = [
        feature
        for feature in _features()
        if allow_admin or feature.audience != "admin"
    ]

    # Path match first: "the agent builder page" → /agent-builder.
    slug = needle.replace(" ", "-")
    for feature in candidates:
        if feature.path.strip("/") == slug:
            return feature

    # Exact title, then title containment, then note containment.
    for feature in candidates:
        if re.sub(r"[^a-z0-9]+", " ", feature.title.lower()).strip() == needle:
            return feature
    for feature in candidates:
        title = re.sub(r"[^a-z0-9]+", " ", feature.title.lower())
        if needle and (needle in title or title in needle):
            return feature
    for feature in candidates:
        haystack = re.sub(
            r"[^a-z0-9]+", " ", f"{feature.title} {feature.group} {feature.note}".lower()
        )
        if needle in haystack:
            return feature
    return None


def catalog_text(*, allow_admin: bool = False) -> str:
    """A compact catalogue for the agent's system prompt.

    Only the routes the caller may open, grouped, so the model can propose a link
    without inventing one.
    """
    grouped: dict[str, list[Feature]] = {}
    for feature in _features():
        if not allow_admin and feature.audience == "admin":
            continue
        grouped.setdefault(feature.group or "Pages", []).append(feature)

    lines: list[str] = []
    for group, features in grouped.items():
        lines.append(f"### {group}")
        for feature in sorted(features, key=lambda item: item.path):
            note = f" — {feature.note}" if feature.note else ""
            lines.append(f"- {feature.label}: `{feature.path}`{note}")
        lines.append("")
    return "\n".join(lines).strip()


# --------------------------------------------------------------------------- #
# Route grounding: nothing the model writes becomes a link to a page that is not
# in the catalogue above.
# --------------------------------------------------------------------------- #

#: The three shapes a route reaches the reader in — a Markdown link, a route in
#: brackets with no target, and a code span — as **one** alternation, so a route
#: is only ever rewritten once and a rewrite cannot be re-matched.
#:
#: These are exactly the shapes the widget turns into a link (`ChatAnswer`):
#: `CitationLink` renders the first, `linkBareRoutes` the second and `RouteCode`
#: the third. A route written as ordinary prose is never linkified, so it needs
#: nothing here either.
_ROUTE_FORMS = re.compile(
    r"\[(?P<label>[^\]\n]*)\]\((?P<target>[^)\s]+)\)"
    r"|\[(?P<bare>/[^\]\[\s()]+)\](?!\()"
    r"|`(?P<code>[^`\n]+)`"
)

#: An in-app path, as opposed to `https://…`, `mailto:…`, `#fragment` or `//host`.
_INTERNAL = re.compile(r"^/(?!/)")


def sanitize_answer(text: str, *, allow_admin: bool = False) -> str:
    """Drop links to pages that do not exist, keeping the words.

    Citations are already checked against the catalogue, but the **answer** was
    not: the model could write any path it liked and the widget would render it as
    a link. Asked where to import a skill, it read that `/agent-skills` has a
    *Skills Registry* tab, invented `/skills-registry` from the tab's name, and
    handed the reader a 404. A wrong link is worse than no link, so:

    * a link to a real route is left exactly as written;
    * a link whose **label** names a real page is corrected to that page, which
      is what "open the [Metrics](/metric)" deserves;
    * anything else keeps its words and loses its target — the sentence still
      reads, it just no longer promises a page;
    * a `code` span holding an unknown route loses its backticks, because the
      widget would otherwise link it;
    * anything that is not an in-app path (`https://…`, `#anchor`) is untouched.
    """
    def replace(match: re.Match[str]) -> str:
        target = match.group("target")
        if target is not None:
            if not _INTERNAL.match(target) or is_valid(target, allow_admin=allow_admin):
                return match.group(0)
            label = match.group("label") or ""
            resolved = normalize(label, allow_admin=allow_admin)
            return f"[{label}]({resolved})" if resolved else label
        bare = match.group("bare")
        if bare is not None:
            # The route is the whole content, so there is no label to fall back
            # to: keep the characters, drop the brackets that make it a link.
            return match.group(0) if is_valid(bare, allow_admin=allow_admin) else bare
        code = match.group("code") or ""
        if _INTERNAL.match(code) and not is_valid(code, allow_admin=allow_admin):
            return code
        return match.group(0)

    return _ROUTE_FORMS.sub(replace, text)


def _safe_prefix(text: str) -> int:
    """How much of ``text`` may be emitted now.

    Everything **before** the last construct a later chunk could still change:
    an unclosed code span, an unclosed ``[``, a ``](target`` with no ``)`` yet, or
    a ``[…]`` sitting at the very end that may still gain its ``(target)``. In
    ordinary prose this holds nothing at all.
    """
    limit = len(text)

    if text.count("`") % 2:
        limit = text.rfind("`")

    depth = 0
    last_open = -1
    for index, char in enumerate(text):
        if char == "[":
            if depth == 0:
                last_open = index
            depth += 1
        elif char == "]" and depth:
            depth -= 1

    if last_open != -1:
        if depth:
            limit = min(limit, last_open)
        else:
            after = text.find("]", last_open) + 1
            if text[after : after + 1] == "(":
                if ")" not in text[after:]:
                    limit = min(limit, last_open)
            elif not text[after:].strip():
                limit = min(limit, last_open)

    return max(limit, 0)


class RouteFilter:
    """Stream one answer through :func:`sanitize_answer`.

    A construct cannot be judged until it is complete, so the filter holds back
    the single construct still being written — a handful of characters — and
    emits everything before it already sanitised. :meth:`flush` releases the tail
    once the model has stopped.
    """

    def __init__(self, *, allow_admin: bool = False) -> None:
        self._allow_admin = allow_admin
        self._buffer = ""

    def feed(self, delta: str) -> str:
        """Take one model chunk and return the text safe to emit now."""
        if not delta:
            return ""
        self._buffer += delta
        safe = _safe_prefix(self._buffer)
        if safe <= 0:
            return ""
        chunk, self._buffer = self._buffer[:safe], self._buffer[safe:]
        return sanitize_answer(chunk, allow_admin=self._allow_admin)

    def flush(self) -> str:
        """Release what is still held back. Call once, when the model stops."""
        chunk, self._buffer = self._buffer, ""
        return sanitize_answer(chunk, allow_admin=self._allow_admin)

    @property
    def pending(self) -> bool:
        """Whether a half-written construct is still held back.

        A caller must not read "nothing has been emitted" as "the model said
        nothing" — the answer may be entirely inside the buffer.
        """
        return bool(self._buffer)

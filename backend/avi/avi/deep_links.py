"""Resolve where a feature lives, and validate a deep link before offering it.

A wrong link is worse than no link: Avi telling someone to "open the Agent
builder" and then 404ing destroys trust in every other answer. So the allow-list
is **generated from the real route table** (``App.tsx``) at corpus-build time and
imported here, rather than guessed or parsed at run time.

The widget only ever offers ``public`` and ``user`` routes. Admin routes are
present in the catalogue (the admin page's Avi can explain them) but are never
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
        if os.environ.get("AVI_FEATURES_JSON"):
            _CATALOGUE = _load_json(os.environ["AVI_FEATURES_JSON"]) or _CATALOGUE
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

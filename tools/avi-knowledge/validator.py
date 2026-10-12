"""Validate Avi's corpus before it is allowed near the index.

A bad document is worse than a missing one: Avi would quote a dead link, an
invented limit or a secret. The checks are deliberately blunt and run in CI as
well as locally, so a document that would mislead a user fails the build.

What is checked:

* frontmatter shape (required keys, known audience, stable id);
* no admin-console route while ``generator.INCLUDE_ADMIN_PAGES`` is off;
* the `route` is a **real route** in the application's route table;
* no dead relative links and no empty/duplicated titles;
* no secrets (keys, tokens, connection strings) leaked from a source file;
* a size cap per document and an overall cap for the corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from generator import INCLUDE_ADMIN_PAGES, Document, is_admin_console_route
from sources import doc_anchors
from sources import RouteInfo

MAX_DOCUMENT_CHARS = 60_000
MAX_CORPUS_CHARS = 1_500_000
MIN_BODY_CHARS = 80

REQUIRED_KEYS = ("id", "title", "route", "group", "audience", "source", "tags")
AUDIENCES = ("public", "user", "admin")

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("aws access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("aws secret", re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*\S{20,}")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.")),
    ("bearer token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._-]{30,}")),
    ("auth0 secret", re.compile(r"(?i)client_secret\s*[:=]\s*\S{16,}")),
    ("password", re.compile(r"(?i)\bpassword\s*[:=]\s*\S{8,}")),
    ("openai key", re.compile(r"\bsk-[A-Za-z0-9]{32,}\b")),
)

#: Phrases that would make Avi state something it cannot know. The placeholder
#: markers are matched case-sensitively as standalone words: the product
#: documentation legitimately talks about an agent's "todo list", so a
#: case-insensitive substring match would reject real content.
FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("placeholder text", re.compile(r"\b(TODO|FIXME|XXX)\b")),
    ("placeholder text", re.compile(r"(?i)\blorem ipsum\b")),
    ("placeholder text", re.compile(r"(?i)\bas an ai language model\b")),
)


@dataclass
class Problem:
    document_id: str
    message: str

    def __str__(self) -> str:
        return f"{self.document_id}: {self.message}"


def _route_exists(route: str, routes: set[str]) -> bool:
    path = route.split("#", 1)[0]
    if path in routes:
        return True
    for known in routes:
        if ":" in known:
            prefix = known.split(":", 1)[0].rstrip("/")
            if prefix and (path == prefix or path.startswith(prefix + "/")):
                return True
    return False


def _docs_anchor(route: str) -> str:
    """The ``#fragment`` of a ``/docs`` link, or ``""`` for any other route."""
    path, _, fragment = route.partition("#")
    if path == "/docs" and fragment:
        return fragment
    return ""


def validate(
    documents: Iterable[Document],
    routes: list[RouteInfo],
    *,
    rendered: list[str] | None = None,
) -> list[Problem]:
    """Return every problem found (empty means the corpus is safe to ingest).

    ``rendered`` lets the caller validate the exact bytes that will be written
    (post-normalisation); the checks fall back to rendering on demand so the
    validator is still usable on its own.
    """
    problems: list[Problem] = []
    known_routes = {route.path for route in routes}
    anchors = doc_anchors()
    seen_ids: dict[str, int] = {}
    seen_titles: dict[str, str] = {}
    total = 0

    for index, document in enumerate(documents):
        total += len(document.body)
        rendered_text = rendered[index] if rendered else document.render()

        for key in REQUIRED_KEYS:
            if not getattr(document, key, None):
                problems.append(Problem(document.id, f"missing frontmatter key {key!r}"))

        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,63}", document.id):
            problems.append(
                Problem(document.id, "id must be lowercase-hyphen (2-64 chars)")
            )
        seen_ids[document.id] = seen_ids.get(document.id, 0) + 1

        if document.audience not in AUDIENCES:
            problems.append(
                Problem(document.id, f"unknown audience {document.audience!r}")
            )

        if not INCLUDE_ADMIN_PAGES and is_admin_console_route(document.route):
            # The switch is off, so an admin-console page in the corpus would end
            # up ingested and answerable. Fail the build instead of publishing it.
            problems.append(
                Problem(
                    document.id,
                    f"admin-console route {document.route!r} must not be in Avi's corpus "
                    "(see generator.INCLUDE_ADMIN_PAGES)",
                )
            )

        if not _route_exists(document.route, known_routes):
            problems.append(
                Problem(document.id, f"route {document.route!r} is not in the route table")
            )

        # A fragment has to name something the page renders. `_route_exists` strips
        # it (so `/docs#anything` passed), which is how sixteen citations shipped
        # pointing at per-question anchors that exist nowhere in the DOM.
        anchor = _docs_anchor(document.route)
        if anchor and anchor not in anchors:
            problems.append(
                Problem(
                    document.id,
                    f"docs anchor #{anchor} is not a section the Documentation page "
                    "renders (a FAQ/troubleshooting spin-off is not an anchor — link "
                    "its parent section instead)",
                )
            )

        if len(document.body.strip()) < MIN_BODY_CHARS:
            problems.append(
                Problem(document.id, f"body is shorter than {MIN_BODY_CHARS} chars")
            )
        if len(rendered_text) > MAX_DOCUMENT_CHARS:
            problems.append(
                Problem(document.id, f"document exceeds {MAX_DOCUMENT_CHARS} chars")
            )

        normalized_title = document.title.strip().lower()
        if normalized_title in seen_titles and seen_titles[normalized_title] != document.id:
            problems.append(
                Problem(
                    document.id,
                    f"title duplicates {seen_titles[normalized_title]!r}",
                )
            )
        seen_titles.setdefault(normalized_title, document.id)

        # A relative markdown link would break inside the product.
        for match in re.finditer(r"\]\((?!https?://|#|/)([^)]+)\)", document.body):
            problems.append(
                Problem(document.id, f"relative link {match.group(1)!r} would break")
            )

        for label, pattern in SECRET_PATTERNS:
            if pattern.search(rendered_text):
                problems.append(Problem(document.id, f"looks like it contains a {label}"))

        for phrase, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(document.body):
                problems.append(Problem(document.id, f"contains {phrase}"))

    for document_id, count in seen_ids.items():
        if count > 1:
            problems.append(Problem(document_id, f"duplicate document id ({count}×)"))

    if total > MAX_CORPUS_CHARS:
        problems.append(Problem("<corpus>", f"corpus exceeds {MAX_CORPUS_CHARS} chars"))

    return problems


def summary(documents: list[Document]) -> str:
    from collections import Counter

    by_audience = Counter(document.audience for document in documents)
    by_source = Counter(document.source for document in documents)
    chars = sum(len(document.body) for document in documents)
    words = sum(len(document.body.split()) for document in documents)
    lines = [
        f"documents : {len(documents)}",
        f"audience  : " + ", ".join(f"{k}={v}" for k, v in sorted(by_audience.items())),
        f"source    : " + ", ".join(f"{k}={v}" for k, v in sorted(by_source.items())),
        f"size      : {chars:,} chars · {words:,} words",
    ]
    return "\n".join(lines)

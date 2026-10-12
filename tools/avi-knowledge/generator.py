"""Generate Avi's corpus from the repository.

Every document is derived from a file that is already the source of truth, and is
written to ``knowledge/avi/`` as committed markdown: reviewable in a pull request,
deterministic across machines, and diffable in CI so Avi can never answer from a
stale document.

The output is deliberately plain markdown with frontmatter — the ingestion
pipeline extracts and chunks it, and the chunker uses the heading structure for
breadcrumbs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from sources import (
    REPO_ROOT,
    DocSection,
    RouteInfo,
    doc_anchors,
    load_docs,
    load_limits,
    load_navigation,
    load_routes,
)

OUTPUT_DIR = REPO_ROOT / "knowledge" / "avi"
MANIFEST_NAME = "manifest.json"
SCHEMA_VERSION = 1

#: Documents can be addressed to different audiences. The widget only ever
#: retrieves `public` and `user`; the `admin` audience stays supported by the
#: mechanism (see ``INCLUDE_ADMIN_PAGES`` below) but is not published today.
AUDIENCES = ("public", "user", "admin")

#: THE admin-console kill switch — the one place to flip it back.
#:
#: When ``False`` (the product decision), admin-console routes (``/admin``,
#: ``/admin/*`` and ``/administration``) are **never** generated into Avi's
#: corpus and are **never** written into the ``features.json`` deep-link
#: allow-list. Avi is the assistant every signed-in user and every guest can
#: open, so it must never surface admin-console content to users — not as an
#: answer, not as a citation, and not as a link.
#:
#: The audience mechanism itself is deliberately untouched: documents still
#: carry ``audience:`` frontmatter, ``validator.AUDIENCES`` still accepts
#: ``admin``, and the retrieval/deep-link layers still filter on it
#: (``retrieval._audience_allowed``, ``deep_links.is_valid(allow_admin=…)``).
#: Set this to ``True`` to publish the admin pages again; nothing else moves.
INCLUDE_ADMIN_PAGES = False


def is_admin_console_route(path: str) -> bool:
    """Whether ``path`` is an admin-console route (``/admin``, ``/admin/*``,
    ``/administration``)."""
    return path in ("/admin", "/administration") or path.startswith("/admin/")


#: Docs sections that document a page whose route is not simply ``/<section id>``.
#: Everything else is resolved by trying ``/<id>`` against the real route table.
DOC_SECTION_PAGES: dict[str, str] = {
    "schedules": "/scheduled-jobs",
    "mcp-tools": "/tools",
    "agents-library": "/agent-store",
    "workflows-store": "/workflow-store",
}


def doc_route(section: Any, routes: set[str]) -> str:
    """Where a documentation section should link.

    The **real page** it documents when one exists, and the ``/docs#<id>`` anchor
    only when the content genuinely has no page of its own (concepts, the FAQ).

    This matters because a citation is a promise: Avi used to link every docs
    section to its anchor, so "where do I build an agent?" offered
    ``/docs#agent-builder`` — a trip to the docs page to read about the page you
    asked for, instead of ``/agent-builder``, the page itself.
    """
    page = DOC_SECTION_PAGES.get(section.id, f"/{section.id}")
    if page in routes:
        return page
    return section.anchor


@dataclass
class Document:
    id: str
    title: str
    route: str
    group: str
    audience: str
    source: str
    tags: list[str]
    body: str
    questions: list[str] = field(default_factory=list)

    @property
    def filename(self) -> str:
        return f"{self.id}.md"

    def render(self) -> str:
        frontmatter = [
            "---",
            f"id: {self.id}",
            f"title: {_yaml_scalar(self.title)}",
            f"route: {_yaml_scalar(self.route)}",
            f"group: {_yaml_scalar(self.group)}",
            f"audience: {self.audience}",
            f"source: {self.source}",
            f"tags: [{', '.join(_yaml_scalar(tag) for tag in self.tags)}]",
        ]
        if self.questions:
            frontmatter.append("questions:")
            frontmatter.extend(f"  - {_yaml_scalar(q)}" for q in self.questions)
        frontmatter.append("---")
        body = self.body.strip()
        return "\n".join(frontmatter) + "\n\n" + body + "\n"


def _yaml_scalar(value: str) -> str:
    text = str(value).replace("\n", " ").strip()
    if text and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 .,:/#()\-–—&'+|]*", text):
        # Quote anything with a leading/trailing space or a YAML-special start.
        if not text.endswith(" ") and not text.startswith("%"):
            return text
    return '"' + text.replace('"', '\\"') + '"'


# --------------------------------------------------------------------------- #
# Docs → documents                                                             #
# --------------------------------------------------------------------------- #


def _render_blocks(section: DocSection) -> str:
    parts: list[str] = []
    for block in section.blocks:
        if block.kind == "paragraph":
            parts.append(block.text)
        elif block.kind == "steps":
            parts.append("\n".join(f"{i}. {item}" for i, item in enumerate(block.items, 1)))
        elif block.kind == "bullets":
            parts.append("\n".join(f"- {item}" for item in block.items))
        elif block.kind == "callout":
            label = block.title or block.tone.title() or "Note"
            parts.append(f"**{label}** — {block.text}")
        elif block.kind == "code":
            parts.append(f"```{block.language}\n{block.code}\n```")
    return "\n\n".join(part for part in parts if part.strip())


def _route_exists(route: str, routes: set[str]) -> bool:
    """Whether a route (ignoring any ``#anchor``) is in the real route table."""
    path = route.split("#", 1)[0]
    if path in routes:
        return True
    # Dynamic segments (/chat/conversation/:conversationId) match their prefix.
    for known in routes:
        if ":" in known:
            prefix = known.split(":", 1)[0].rstrip("/")
            if prefix and path.startswith(prefix):
                return True
    return False


def docs_documents(routes: set[str]) -> list[Document]:
    """One document per documentation section, plus one per FAQ/troubleshooting
    question (so a literal user question matches a curated answer).

    A section that documents an **admin-console** page is tagged ``audience:
    admin`` in ``docs.ts`` and is skipped entirely while ``INCLUDE_ADMIN_PAGES``
    is off: citing "Platform status" to someone asking what they can do here is
    both wrong and a link they cannot open.
    """
    documents: list[Document] = []
    sections = load_docs()
    for section in sections:
        if getattr(section, "audience", "user") == "admin" and not INCLUDE_ADMIN_PAGES:
            continue
        body_parts = [f"# {section.title}"]
        if section.summary:
            body_parts.append(section.summary)
        rendered = _render_blocks(section)
        if rendered:
            body_parts.append(rendered)
        body = "\n\n".join(body_parts)

        if section.id.startswith(("faq-", "troubleshooting-")):
            # A curated single-question document: the question *is* the title, so
            # lexical retrieval matches the user's phrasing directly.
            #
            # It links to its **parent section**, not to a synthetic per-question
            # anchor: the docs page renders one element per section and nothing in
            # the DOM carries `#faq-do-i-need-a-bedrock-…`, so the old link landed
            # nowhere at all. Landing on the FAQ is the honest promise.
            documents.append(
                Document(
                    id=section.id,
                    title=section.title,
                    route=_parent_anchor(section, routes),
                    group="Help",
                    audience="user",
                    source="docs",
                    tags=["faq", "troubleshooting", "help"],
                    body=body,
                    questions=[section.summary],
                )
            )
            continue

        documents.append(
            Document(
                id=section.id,
                title=section.title,
                route=doc_route(section, routes),
                group=section.group_title or "Documentation",
                audience="public" if section.group == "start" else "user",
                source="docs",
                tags=["docs", section.group],
                body=body,
            )
        )
    return documents


def _parent_anchor(section: Any, routes: set[str]) -> str:
    """The anchor of the FAQ/troubleshooting section a spin-off came from.

    A spin-off id is ``<parent>-<slug>-<n>``; the DOM id is the parent alone.
    """
    for parent in ("faq", "troubleshooting"):
        if section.id.startswith(f"{parent}-"):
            return doc_route(SimpleNamespace(id=parent, anchor=f"/docs#{parent}"), routes)
    return section.anchor


# --------------------------------------------------------------------------- #
# Routes + navigation → the feature catalogue                                  #
# --------------------------------------------------------------------------- #


def _nav_index() -> dict[str, Any]:
    links = load_navigation("navigation/sidebarLinks.ts")
    by_path: dict[str, Any] = {}

    def walk(rows: list[Any], parent: str = "") -> None:
        for row in rows:
            by_path[row.to] = {"label": row.label, "tooltip": row.tooltip, "parent": parent}
            walk(row.children, row.label)

    walk(links)
    return by_path


#: One short, human explanation per route, written here because the source of
#: truth for "what is this page for" is the product, not the code. A route with
#: no entry here still appears in the catalogue (it just carries its nav label).
ROUTE_NOTES: dict[str, str] = {
    "/dashboard": "Workspace KPIs — agents, workflows, 30-day tokens, AI credits, recent runs and quick actions.",
    "/chat": "Ask an agent or a workflow a question and watch it plan, call tools and answer with cited sources.",
    "/storage": "Standalone files you can attach to an agent for a single run. Never ingested or indexed.",
    "/knowledge-bases": "Create a knowledge base, upload documents, and watch them extract, embed and index until ready.",
    "/agent-builder": "Build an agent on a canvas: prompt, model, reasoning, answer mode, knowledge, tools, skills and a schedule.",
    "/workflow-builder": "Wire several agents into a deterministic graph or a dynamic swarm, with a host agent coordinating.",
    "/mcp-builder": "Build your own Python tool by chatting, then test it against a generated argument form.",
    "/agent-skills": "Reusable instructions in the strands format, with allowed tools, importable from a registry or a repo.",
    "/tools": "Every MCP server available to your agents, with per-tool enable toggles.",
    "/agent-store": "The public agent library: install someone else's published agent as your own copy.",
    "/workflow-store": "Every workflow you have built.",
    "/scheduled-jobs": "Scheduled runs for your agents and workflows, with their next run time.",
    "/playground": "The prompt playground for trying a model without saving an agent.",
    "/evaluations": "Datasets, judges and scored runs over your agents.",
    "/traces": "Every run's trace: spans, tool calls, tokens and cost.",
    "/metrics": "Aggregate usage and quality metrics.",
    "/memory": "What your agents remember about you, and the switch to forget it.",
    "/vault": "Encrypted secrets; select one as the model to bill runs to your own provider key.",
    "/guardrails": "Bedrock guardrails that filter prompts and answers.",
    "/usage": "Your AI credits, token usage, and the limits that apply to your account.",
    "/settings": "Workspace settings: theme, defaults and preferences.",
    "/docs": "The full in-app documentation, grouped by area.",
    "/architecture": "Interactive architecture diagrams, including the Avi tab.",
    "/status": "Platform status and the AWS services behind it.",
    "/changelog": "What shipped, newest first.",
    "/support": "Message the admins, or open a security report.",
    "/admin": "The admin console: users, credits, MCP integrations, platform status, support and security inboxes.",
    "/admin/avi": "Avi controls: kill switch, models, limits, feedback, evaluations, traces and the knowledge corpus.",
}


def feature_documents(routes: list[RouteInfo]) -> list[Document]:
    nav = _nav_index()
    documents: list[Document] = []

    user_paths: list[str] = []
    admin_paths: list[str] = []
    for route in sorted({item.path for item in routes}):
        if route in {"/", "/login", "/logout", "/authorization/callback"}:
            continue
        if ":" in route:
            continue
        if is_admin_console_route(route):
            admin_paths.append(route)
        else:
            user_paths.append(route)

    if not INCLUDE_ADMIN_PAGES:
        # Drop the admin catalogue document (and with it every admin route) from
        # the corpus. The loop above still classifies the routes, so flipping
        # INCLUDE_ADMIN_PAGES restores the document unchanged.
        admin_paths = []

    for audience, paths, title, doc_id in (
        ("user", user_paths, "Feature index — every page in the workspace", "feature-index"),
        ("admin", admin_paths, "Feature index — the admin console", "admin-feature-index"),
    ):
        lines: list[str] = [
            f"# {title}",
            "",
            "Each row is a real page in the product, with the route to open it.",
            "",
        ]
        for path in paths:
            meta = nav.get(path) or {}
            label = meta.get("label") or _label_from_path(path)
            parent = meta.get("parent")
            tooltip = meta.get("tooltip")
            note = ROUTE_NOTES.get(path) or tooltip or ""
            location = f"{parent} → {label}" if parent else label
            lines.append(f"- **{location}** — open it at `{path}`. {note}".rstrip())
        if not paths:
            continue
        documents.append(
            Document(
                id=doc_id,
                title=title,
                route="/admin" if audience == "admin" else "/dashboard",
                group="Features",
                audience=audience,
                source="navigation",
                tags=["features", "navigation", "routes", "where", "find"],
                body="\n".join(lines),
                questions=[
                    "Where do I find a feature?",
                    "Which page does what?",
                ],
            )
        )
    return documents


def _label_from_path(path: str) -> str:
    tail = path.rsplit("/", 1)[-1] or path
    return tail.replace("-", " ").strip().title()


# --------------------------------------------------------------------------- #
# Limits → a document generated from the enforcing constants                  #
# --------------------------------------------------------------------------- #


def limits_document() -> Document:
    rows = load_limits()
    areas: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        areas.setdefault(str(row["area"]), []).append(row)

    lines = [
        "# Platform limits",
        "",
        "These are the limits the product enforces. They are generated from the",
        "constants in the code, so they are exact — and a per-account override can",
        "raise some of them, which is why the **Usage** page shows the numbers that",
        "actually apply to your account.",
        "",
    ]
    for area, area_rows in areas.items():
        lines.append(f"## {area}")
        lines.append("")
        for row in area_rows:
            lines.append(f"- **{row['limit']}**: {row['value']}")
        lines.append("")
    lines.append(
        "To see your own effective limits, open the Usage page at `/usage`."
    )
    return Document(
        id="platform-limits",
        title="Platform limits",
        route="/usage",
        group="Manage",
        audience="user",
        source="code",
        tags=["limits", "quota", "maximum", "how many", "usage", "billing"],
        body="\n".join(lines),
        questions=[
            "How many knowledge bases can I create?",
            "What is the maximum file size?",
            "How many agents am I allowed?",
        ],
    )


# --------------------------------------------------------------------------- #
# Curated overview documents                                                  #
# --------------------------------------------------------------------------- #

#: The handful of documents that explain the product itself. Written here rather
#: than scraped, because "what is this platform" is product copy, not code.
OVERVIEW_DOCUMENTS: tuple[dict[str, Any], ...] = (
    {
        "id": "what-is-get1agent",
        "title": "What is get1agent?",
        "route": "/docs#getting-started",
        "group": "Getting started",
        "audience": "public",
        "tags": ["overview", "introduction", "what", "platform", "capabilities"],
        "questions": [
            "What is this platform?",
            "What can I build here?",
            "What does get1agent do?",
        ],
        "body": """# What is get1agent?

get1agent (OneAgent) is a workspace for building, running and evaluating AI agents
on your own data. You assemble an agent from four building blocks:

- **Knowledge** — retrieval over documents you upload, with hybrid semantic and
  keyword search and a citation back to the exact source page.
- **Tools** — web search, a code interpreter, HTTP fetch, a managed browser,
  storage and any remote MCP server you connect.
- **Skills** — reusable instructions the agent loads only when they apply.
- **Models** — curated models on Amazon Bedrock, or your own provider key.

You can then wire several agents into a **workflow**, run them on a **schedule**,
score them in the **evaluation lab**, and inspect every run on the **Traces**
page.

The platform is fully AWS-native: embeddings, reranking, every model call, the
agent platform, tracing and caching all run on AWS, and your data is private to
your account.
""",
    },
    {
        "id": "what-can-i-do-here",
        "title": "What can I do on this platform?",
        "route": "/dashboard",
        "group": "Getting started",
        "audience": "public",
        "tags": ["capabilities", "use cases", "what can i do", "examples", "build"],
        "questions": [
            "What can I do with this platform?",
            "What are the main features?",
            "Give me examples of what I can build.",
        ],
        "body": """# What can I do on this platform?

The short version: give an agent your documents and tools, then ask it questions.

Things people build here:

1. **A question-answering assistant over their own documents.** Upload files to a
   knowledge base; ask in Chat; every answer cites the document and page it came
   from.
2. **A multi-step research agent.** Give it web search and HTTP fetch so it can
   look things up and combine sources.
3. **A data tool.** Let the agent fetch a JSON API and run calculations over it
   in the code interpreter.
4. **A multi-agent workflow.** One host agent coordinates specialists, either in
   a fixed graph or a dynamic swarm.
5. **A scheduled digest.** Run an agent every morning and read the result in
   Chat.
6. **A custom tool.** Describe the Python tool you want in the MCP Builder and
   use it from any agent.
7. **A measured pipeline.** Score answers in Evaluations and watch cost and
   latency in Metrics and Traces.

Where to start: create a knowledge base, upload a document, build an agent on the
canvas, then ask it something in Chat.
""",
    },
    {
        "id": "avi-what-is-avi",
        "title": "What is Avi?",
        "route": "/dashboard",
        "group": "Help",
        "audience": "public",
        "tags": ["avi", "assistant", "help", "chatbot", "who are you"],
        "questions": [
            "What is Avi?",
            "Who are you?",
            "Are you a human?",
            "How do I use Avi?",
        ],
        "body": """# What is Avi?

Avi is the assistant built into this product. It lives behind the button in the
bottom-right corner of every page and answers questions about the platform:
what a feature does, where to find it, how to do something, and what the limits
are.

What Avi is good at:

- Explaining any feature and linking you straight to the page that does it.
- Answering "how do I …" questions with the actual steps.
- Telling you the real limits and where to see your own usage.

What Avi does not do:

- It does not answer general questions, write code for you, or do maths
  unrelated to the platform.
- It does not read your documents unless you ask about them.
- For anything it cannot answer, it will point you to the Support page so a human
  can help.

Avi answers only from the product's own documentation, so if something is not
documented yet it will say so rather than guess.
""",
    },
)


# --------------------------------------------------------------------------- #
# Assembly                                                                     #
# --------------------------------------------------------------------------- #


def feature_catalogue(routes: list[RouteInfo]) -> dict[str, Any]:
    """The generated, importable route catalogue used to validate deep links.

    Avi must never propose a route that does not exist, so the allow-list is
    generated from the real route table and shipped with the package rather than
    parsed from TSX at run time. ``dynamicPrefixes`` cover parameterised routes
    (``/chat/conversation/:id``) whose concrete id a caller supplies.
    """
    nav = _nav_index()
    paths: list[str] = []
    dynamic: list[str] = []
    features: list[dict[str, Any]] = []

    for route in sorted({item.path for item in routes}):
        if route in {"/login", "/logout", "/authorization/callback", "/"}:
            continue
        if "*" in route:
            # A catch-all (``/*`` → NotFound) is not a destination Avi may link to.
            continue
        is_admin = is_admin_console_route(route)
        if is_admin and not INCLUDE_ADMIN_PAGES:
            # Admin-console routes are withheld from the allow-list (including
            # their dynamic prefixes) so Avi can never deep-link into the admin
            # console. See INCLUDE_ADMIN_PAGES.
            continue
        if ":" in route:
            prefix = route.split(":", 1)[0].rstrip("/")
            if prefix and prefix not in dynamic:
                dynamic.append(prefix)
            continue
        paths.append(route)

        meta = nav.get(route) or {}
        features.append(
            {
                "path": route,
                "title": str(meta.get("label") or _label_from_path(route)),
                "group": str(meta.get("parent") or ("Admin" if is_admin else "Pages")),
                "audience": "admin" if is_admin else "user",
                "note": ROUTE_NOTES.get(route) or str(meta.get("tooltip") or ""),
            }
        )

    return {
        "schemaVersion": SCHEMA_VERSION,
        "paths": paths,
        "dynamicPrefixes": dynamic,
        "features": features,
        # The `#fragment`s the Documentation page renders. Without this the agent
        # could only check that a `/docs` link pointed at `/docs` and had to accept
        # any fragment — which is how citations to per-question anchors that exist
        # nowhere in the DOM (`/docs#troubleshooting-a-custom-tool-times-out--4`)
        # were offered, and dead-ended. `deep_links.is_valid` now checks the anchor
        # against this list, so a stale index cannot produce a dead link either.
        "docAnchors": sorted(doc_anchors()),
    }


def build_documents() -> list[Document]:
    """Every corpus document, deterministically ordered."""
    routes = load_routes()
    by_path: dict[str, RouteInfo] = {}
    for route in routes:
        by_path.setdefault(route.path, route)

    documents: list[Document] = []
    documents.extend(
        Document(source="curated", **spec) for spec in OVERVIEW_DOCUMENTS
    )
    documents.extend(docs_documents(set(by_path)))
    documents.extend(feature_documents(list(by_path.values())))
    documents.append(limits_document())

    seen: set[str] = set()
    for document in documents:
        if document.id in seen:
            raise ValueError(f"duplicate corpus document id {document.id!r}")
        seen.add(document.id)
    return sorted(documents, key=lambda item: item.id)

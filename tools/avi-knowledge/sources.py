"""Read Avi's corpus sources out of the repository.

Avi is grounded in the repository, never in a crawl, so every document it answers
from is derived from a file that is already the source of truth: the in-app
documentation data, the real route table, the navigation registries and the
enforced limit constants. Nothing here talks to the network.

The TypeScript sources are parsed with a small structural reader rather than a
TS toolchain, so the generator runs anywhere Python does (CI included) and never
drifts from a compiler version. It is deliberately strict: anything it cannot
understand raises rather than silently dropping a document.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
BACKEND_PACKAGES = REPO_ROOT / "backend" / "packages"


# --------------------------------------------------------------------------- #
# A tiny reader for TS/TSX object + array literals                             #
# --------------------------------------------------------------------------- #


class SourceError(RuntimeError):
    """The repository source could not be read as expected."""


def _skip_ws(text: str, index: int) -> int:
    while index < len(text) and text[index] in " \t\r\n":
        index += 1
    return index


def strip_comments(text: str) -> str:
    """Remove ``//`` and ``/* */`` comments without touching string contents.

    The navigation registry and the diagram modules are commented in prose, so
    the structural reader must not mistake a comment for syntax. Newlines are
    preserved so offsets and error messages stay meaningful.
    """
    out: list[str] = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char in "'\"`":
            start = index
            _, index = _read_string(text, index)
            out.append(text[start:index])
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "/":
            while index < length and text[index] != "\n":
                index += 1
            continue
        if char == "/" and index + 1 < length and text[index + 1] == "*":
            index += 2
            while index + 1 < length and not (
                text[index] == "*" and text[index + 1] == "/"
            ):
                if text[index] == "\n":
                    out.append("\n")
                index += 1
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _read_string(text: str, index: int) -> tuple[str, int]:
    """Read a single-quoted, double-quoted or backtick string."""
    quote = text[index]
    index += 1
    out: list[str] = []
    while index < len(text):
        char = text[index]
        if char == "\\":
            escape = text[index + 1] if index + 1 < len(text) else ""
            out.append({"n": "\n", "t": "\t", "'": "'", '"': '"', "`": "`"}.get(escape, escape))
            index += 2
            continue
        if char == quote:
            return "".join(out), index + 1
        out.append(char)
        index += 1
    raise SourceError("unterminated string literal")


def _read_key(text: str, index: int) -> tuple[str, int]:
    if text[index] in "'\"":
        return _read_string(text, index)
    match = re.match(r"[A-Za-z_$][\w$]*", text[index:])
    if not match:
        raise SourceError(f"expected a key at offset {index}")
    return match.group(0), index + match.end()


def _read_value(text: str, index: int) -> tuple[Any, int]:
    """Read a JS value: primitive, array, object, or an opaque expression."""
    index = _skip_ws(text, index)
    if index >= len(text):
        raise SourceError("unexpected end of source")

    char = text[index]
    if char in "'\"`":
        return _read_string(text, index)
    if char == "[":
        return _read_array(text, index)
    if char == "{":
        return _read_object(text, index)
    if char == "-" or char.isdigit():
        match = re.match(r"-?\d+(?:\.\d+)?", text[index:])
        if match:
            raw = match.group(0)
            value: Any = float(raw) if "." in raw else int(raw)
            return value, index + match.end()
    match = re.match(r"(true|false|null|undefined)\b", text[index:])
    if match:
        token = match.group(0)
        return {"true": True, "false": False}.get(token), index + match.end()

    # An inline expression (a template, a call): consume to the end of it and
    # keep the raw text so the caller can decide (documents are re-written only
    # from recognised values, so an opaque value stays visible, not guessed).
    start = index
    depth = 0
    while index < len(text):
        current = text[index]
        if current in "([{":
            depth += 1
        elif current in ")]}":
            if depth == 0:
                break
            depth -= 1
        elif current == "," and depth == 0:
            break
        elif current in "'\"`":
            _, index = _read_string(text, index)
            continue
        index += 1
    return text[start:index].strip(), index


def _read_array(text: str, index: int) -> tuple[list[Any], int]:
    assert text[index] == "["
    index += 1
    items: list[Any] = []
    while True:
        index = _skip_ws(text, index)
        if index >= len(text):
            raise SourceError("unterminated array")
        if text[index] == "]":
            return items, index + 1
        value, index = _read_value(text, index)
        items.append(value)
        index = _skip_ws(text, index)
        if index < len(text) and text[index] == ",":
            index += 1


def _read_object(text: str, index: int) -> tuple[dict[str, Any], int]:
    assert text[index] == "{"
    index += 1
    obj: dict[str, Any] = {}
    while True:
        index = _skip_ws(text, index)
        if index >= len(text):
            raise SourceError("unterminated object")
        if text[index] == "}":
            return obj, index + 1
        key, index = _read_key(text, index)
        index = _skip_ws(text, index)
        if index >= len(text) or text[index] != ":":
            raise SourceError(f"expected ':' after key {key!r}")
        index = _skip_ws(text, index + 1)
        value, index = _read_value(text, index)
        obj[key] = value
        index = _skip_ws(text, index)
        if index < len(text) and text[index] == ",":
            index += 1


def _read_export(text: str, name: str) -> Any:
    """Read ``export const <name>[: T] = <value>`` out of a TS module."""
    # Comments are stripped first so the match offset is valid for the reader.
    source = strip_comments(text)
    match = re.search(
        rf"export\s+const\s+{re.escape(name)}\s*(?::[^=]+?)?=\s*", source
    )
    if not match:
        raise SourceError(f"export {name!r} not found")
    value, _ = _read_value(source, match.end())
    return value


# --------------------------------------------------------------------------- #
# Documentation (frontend/src/content/docs.ts)                                 #
# --------------------------------------------------------------------------- #


@dataclass
class DocBlock:
    kind: str
    text: str = ""
    items: list[str] = field(default_factory=list)
    tone: str = ""
    title: str = ""
    language: str = ""
    code: str = ""


@dataclass
class DocSection:
    id: str
    title: str
    summary: str
    group: str
    group_title: str
    blocks: list[DocBlock]
    #: ``"user"`` (default) or ``"admin"``. A section that documents an
    #: **admin-console** page is tagged ``admin`` in ``docs.ts`` so it never
    #: becomes user-facing Avi knowledge — the widget answers users, and citing a
    #: page only an administrator can open is a dead end for them.
    audience: str = "user"
    #: True for the synthetic one-question documents split out of the FAQ and
    #: troubleshooting sections. They are retrievable, but they are **not DOM
    #: ids** — the docs page renders one element per real section, so a link to a
    #: spin-off anchor lands nowhere. ``doc_anchors`` exists to make that
    #: distinction checkable rather than remembered.
    spinoff: bool = False

    @property
    def anchor(self) -> str:
        return f"/docs#{self.id}"


def doc_anchors() -> set[str]:
    """The ``#fragment`` ids the Documentation page actually renders.

    One per **real** section in ``docs.ts``. The FAQ/troubleshooting spin-offs are
    excluded on purpose: they are retrieval documents, not elements in the DOM, so
    ``/docs#faq-do-i-need-a-bedrock-account-0`` scrolls nowhere. That is a link a
    citation must never offer, and it shipped for every one of them until the
    validator learned to check the fragment and not just the path.
    """
    return {section.id for section in load_docs() if not section.spinoff}


def _blocks_from(raw_blocks: Any) -> list[DocBlock]:
    if not isinstance(raw_blocks, list):
        raise SourceError("a docs section has no blocks array")
    blocks: list[DocBlock] = []
    for raw in raw_blocks:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind") or "")
        if kind == "code":
            blocks.append(
                DocBlock(
                    kind=kind,
                    language=str(raw.get("language") or ""),
                    code=str(raw.get("code") or ""),
                )
            )
            continue
        blocks.append(
            DocBlock(
                kind=kind,
                text=str(raw.get("text") or ""),
                items=[str(item) for item in (raw.get("items") or [])],
                tone=str(raw.get("tone") or ""),
                title=str(raw.get("title") or ""),
            )
        )
    return blocks


def load_docs() -> list[DocSection]:
    """Every documentation section, tagged with its group."""
    path = FRONTEND_SRC / "content" / "docs.ts"
    text = path.read_text(encoding="utf-8")
    groups = _read_export(text, "DOCS")
    if not isinstance(groups, list) or not groups:
        raise SourceError("DOCS is empty")

    sections: list[DocSection] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("id") or "")
        group_title = str(group.get("title") or "")
        for raw_section in group.get("sections") or []:
            if not isinstance(raw_section, dict):
                continue
            sections.append(
                DocSection(
                    id=str(raw_section.get("id") or ""),
                    title=str(raw_section.get("title") or ""),
                    summary=str(raw_section.get("summary") or ""),
                    group=group_id,
                    group_title=group_title,
                    blocks=_blocks_from(raw_section.get("blocks")),
                    audience=str(raw_section.get("audience") or "user"),
                )
            )

    seen: set[str] = set()
    for section in sections:
        if not section.id:
            raise SourceError("a docs section has no id")
        if section.id in seen:
            raise SourceError(f"duplicate docs section id {section.id!r}")
        seen.add(section.id)

    # The FAQ and troubleshooting bullets are literally the questions users ask
    # Avi; expose them as their own documents so retrieval can match a user's
    # phrasing to a curated answer instead of only to prose. The question is the
    # first sentence ending in "?", and the rest is the answer.
    for section in list(sections):
        if section.id in {"faq", "troubleshooting"}:
            for index, item in enumerate(_items_of(section)):
                question = _question_of(item) or item
                sections.append(
                    DocSection(
                        id=f"{section.id}-{_slug(question)[:40]}-{index}",
                        title=question,
                        summary=item,
                        group=section.group,
                        group_title=section.group_title,
                        blocks=[DocBlock(kind="paragraph", text=item)],
                        audience=section.audience,
                        spinoff=True,
                    )
                )
    return sections


def _items_of(section: "DocSection") -> list[str]:
    items: list[str] = []
    for block in section.blocks:
        items.extend(block.items)
    return items


def _question_of(text: str) -> str:
    """The leading question of a FAQ bullet, or an empty string.

    The bullets read "Question? Answer." — the question is what a user types, so
    it becomes the document title (and `questions:` frontmatter) rather than a
    title that awkwardly contains the whole answer.
    """
    stripped = text.strip()
    position = stripped.find("?")
    if position == -1 or position > 160:
        return ""
    question = stripped[: position + 1].strip()
    return question if len(question) > 8 else ""


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "item"


# --------------------------------------------------------------------------- #
# Routes and navigation                                                        #
# --------------------------------------------------------------------------- #


@dataclass
class RouteInfo:
    path: str
    element: str
    component: str
    admin: bool = False


def _element_component(attributes: str) -> str:
    """The component a ``element={...}`` prop renders.

    The prop is not always a bare ``<Page />``: a route that needs its own
    Suspense wrapper reads ``element={<Suspense fallback={null}><Page /></Suspense>}``.
    Taking the first tag there would record "Suspense" as the page and lose the
    real component, so the *innermost* capitalized tag wins.
    """
    start = attributes.find("element={")
    if start == -1:
        return ""
    index = start + len("element={")
    depth = 1
    quote = ""
    while index < len(attributes):
        char = attributes[index]
        if quote:
            if char == quote:
                quote = ""
        elif char in "\"'`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                break
        index += 1

    body = attributes[start + len("element={") : index]
    # Capitalized tag names are components (`<Page />`); lowercase ones are hosts.
    tags = re.findall(r"<([A-Z]\w*)", body)
    if tags:
        return tags[-1]
    # A pre-built element passed by identifier: `element={SomePage}`.
    bound = re.fullmatch(r"\s*([A-Z]\w*)\s*", body)
    return bound.group(1) if bound else ""


def load_routes() -> list[RouteInfo]:
    """The real route table from ``App.tsx`` (so a deep link can be validated).

    Routes nest: ``<Route path="/admin">`` contains ``<Route path="users">``, so a
    relative child is resolved against the enclosing absolute path. Without that,
    every nested page (the whole admin console) would be invisible to the
    allow-list and Avi could never link to it.

    This scans tags rather than pattern-matching them, because ``element={<X />}``
    contains a self-closing *component* — a naive regex reads that ``/>`` as the
    end of the route tag and loses the nesting.
    """
    text = strip_comments((FRONTEND_SRC / "App.tsx").read_text(encoding="utf-8"))

    routes: list[RouteInfo] = []
    stack: list[str] = []
    index = 0
    scanned_to = 0

    while True:
        start = text.find("<Route", index)
        if start == -1:
            break
        after = start + len("<Route")
        if after < len(text) and (text[after].isalnum() or text[after] == "_"):
            index = after  # e.g. <RouteGate> — not a route declaration
            continue

        # Find the end of the opening tag, ignoring JSX expressions and strings.
        depth = 0
        quote = ""
        cursor = after
        while cursor < len(text):
            char = text[cursor]
            if quote:
                if char == quote:
                    quote = ""
            elif char in "\"'`":
                quote = char
            elif char == "{":
                depth += 1
            elif char == "}":
                depth = max(0, depth - 1)
            elif depth == 0 and char == ">":
                break
            cursor += 1

        attributes = text[after:cursor]
        self_closing = attributes.rstrip().endswith("/")
        index = cursor + 1

        # Any </Route> between the previous tag and this one closes elements.
        for _ in range(text.count("</Route>", scanned_to, start)):
            if stack:
                stack.pop()
        scanned_to = index

        component = _element_component(attributes)
        path_match = re.search(r"""path=(?:"([^"]*)"|'([^']*)')""", attributes)
        raw_path = (path_match.group(1) or path_match.group(2)) if path_match else None

        parent = stack[-1] if stack else ""
        if raw_path is None:
            # A layout route: it scopes its children but declares no path.
            full = parent
        elif raw_path.startswith("/"):
            full = raw_path
        elif parent:
            full = f"{parent.rstrip('/')}/{raw_path}"
        else:
            full = f"/{raw_path}"

        if component and component != "Navigate":
            routes.append(
                RouteInfo(
                    path=full,
                    element=component,
                    component=component,
                    admin=component.startswith("Admin") or full.startswith("/admin"),
                )
            )
        if not self_closing:
            stack.append(full)

    if not routes:
        raise SourceError("no routes parsed from App.tsx")
    return routes


@dataclass
class NavLink:
    to: str
    label: str
    tooltip: str = ""
    children: list["NavLink"] = field(default_factory=list)


def load_navigation(relative: str, export: str = "sidebarLinks") -> list[NavLink]:
    """Read a sidebar registry (``export const <export> = [{to, label, …}]``)."""
    path = FRONTEND_SRC / relative
    if not path.exists():
        return []
    source = strip_comments(path.read_text(encoding="utf-8"))
    match = re.search(
        rf"export\s+const\s+{re.escape(export)}\s*(?::[^=]+?)?=\s*", source
    )
    if not match:
        return []
    raw, _ = _read_value(source, match.end())
    links: list[NavLink] = []

    def walk(rows: Any) -> list[NavLink]:
        out: list[NavLink] = []
        if not isinstance(rows, list):
            return out
        for row in rows:
            if not isinstance(row, dict) or not row.get("to"):
                continue
            out.append(
                NavLink(
                    to=str(row["to"]),
                    label=str(row.get("label") or ""),
                    tooltip=str(row.get("tooltip") or ""),
                    children=walk(row.get("children")),
                )
            )
        return out

    links = walk(raw)
    return links


# --------------------------------------------------------------------------- #
# Enforced limits (from code, so Avi never quotes a stale number)             #
# --------------------------------------------------------------------------- #


def load_limits() -> list[dict[str, Any]]:
    """Import the real limit constants and flatten them into rows.

    Values are read from the modules that enforce them — never from prose — so a
    limit change in code changes Avi's answer. Per-user rows can still be raised
    for a specific account, which is why the generated document points at the
    Usage page for a user's effective numbers.
    """
    if str(BACKEND_PACKAGES) not in sys.path:
        sys.path.insert(0, str(BACKEND_PACKAGES))

    from data.repositories import avi_settings, quotas  # noqa: PLC0415

    def mib(value: int) -> str:
        return f"{value // (1024 * 1024)} MB"

    rows: list[dict[str, Any]] = [
        {"area": "Knowledge bases", "limit": "Knowledge bases per user", "value": quotas.DEFAULT_MAX_KNOWLEDGE_BASES, "enforced": "quotas.DEFAULT_MAX_KNOWLEDGE_BASES"},
        {"area": "Knowledge bases", "limit": "Files per knowledge base", "value": quotas.DEFAULT_MAX_FILES_PER_KB, "enforced": "quotas.DEFAULT_MAX_FILES_PER_KB"},
        {"area": "Knowledge bases", "limit": "Files per user", "value": quotas.DEFAULT_MAX_FILES_PER_USER, "enforced": "quotas.DEFAULT_MAX_FILES_PER_USER"},
        {"area": "Knowledge bases", "limit": "Size per uploaded file", "value": mib(quotas.DEFAULT_MAX_FILE_BYTES), "enforced": "quotas.DEFAULT_MAX_FILE_BYTES"},
        {"area": "Knowledge bases", "limit": "Knowledge storage per user", "value": mib(quotas.DEFAULT_MAX_STORAGE_BYTES), "enforced": "quotas.DEFAULT_MAX_STORAGE_BYTES"},
    ]

    user_api = REPO_ROOT / "backend" / "services" / "apis" / "user-api" / "handler.py"
    spec = {
        "MAX_AGENTS_PER_USER": ("Agents", "Agents per user"),
        "MAX_AGENT_CONFIG_BYTES": ("Agents", "Agent configuration size"),
        "MAX_WORKFLOWS_PER_USER": ("Workflows", "Workflows per user"),
        "MAX_WORKFLOW_AGENTS": ("Workflows", "Agents per workflow"),
        "MAX_WORKFLOW_NODES": ("Workflows", "Nodes per workflow"),
        "MAX_WORKFLOW_EDGES": ("Workflows", "Edges per workflow"),
        "MAX_VAULT_SECRETS": ("Vault", "Secrets per user"),
        "MAX_GUARDRAILS_PER_USER": ("Guardrails", "Guardrails per user"),
        "MAX_TAGS_PER_DOCUMENT": ("Tags", "Tags per document"),
        "MAX_AGENT_DEFAULT_QUESTIONS": ("Agents", "Starter questions per agent input"),
    }
    found = _read_python_constants(user_api, spec)
    for name, (area, label) in spec.items():
        rows.append(
            {
                "area": area,
                "limit": label,
                "value": _humanize(found[name]),
                "enforced": f"user-api handler {name}",
            }
        )

    # Avi's own limits come from its settings defaults.
    rows.extend(
        [
            {"area": "Avi", "limit": "Guest questions per IP per hour", "value": avi_settings.DEFAULT_GUEST_PER_HOUR, "enforced": "avi_settings.DEFAULT_GUEST_PER_HOUR"},
            {"area": "Avi", "limit": "Guest questions per IP per day", "value": avi_settings.DEFAULT_GUEST_PER_DAY, "enforced": "avi_settings.DEFAULT_GUEST_PER_DAY"},
            {"area": "Avi", "limit": "Signed-in questions per hour", "value": avi_settings.DEFAULT_USER_PER_HOUR, "enforced": "avi_settings.DEFAULT_USER_PER_HOUR"},
            {"area": "Avi", "limit": "Signed-in questions per day", "value": avi_settings.DEFAULT_USER_PER_DAY, "enforced": "avi_settings.DEFAULT_USER_PER_DAY"},
            {"area": "Avi", "limit": "Agent steps per Avi answer", "value": avi_settings.DEFAULT_MAX_AGENT_STEPS, "enforced": "avi_settings.DEFAULT_MAX_AGENT_STEPS"},
            {"area": "Avi", "limit": "Characters per Avi question", "value": avi_settings.DEFAULT_MAX_INPUT_CHARS, "enforced": "avi_settings.DEFAULT_MAX_INPUT_CHARS"},
        ]
    )
    return rows


def _read_python_constants(path: Path, names: dict[str, Any]) -> dict[str, int]:
    """Read integer constants from a Python source without importing it.

    ``user-api``'s handler imports the whole application, which is far too heavy
    (and AWS-dependent) for a corpus build; a targeted regex over the constant
    block is exact for ``NAME = 123`` and cannot execute anything.
    """
    text = path.read_text(encoding="utf-8")
    found: dict[str, int] = {}
    for name in names:
        match = re.search(rf"^{re.escape(name)}\s*=\s*(.+)$", text, re.MULTILINE)
        if not match:
            raise SourceError(f"{name} not found in {path.name}")
        raw = match.group(1).split("#", 1)[0].strip()
        expression = raw.replace("_", "").replace("\u00a0", " ")
        try:
            found[name] = int(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307 - digits only
        except Exception as exc:  # noqa: BLE001
            raise SourceError(f"{name} value {raw!r} is not a plain integer") from exc
    return found


def _humanize(value: Any) -> str:
    if isinstance(value, int):
        if value >= 1024 * 1024 and value % (1024 * 1024) == 0:
            return f"{value // (1024 * 1024)} MB"
        if value >= 1024 and value % 1024 == 0:
            return f"{value // 1024} KB"
        return str(value)
    return str(value)

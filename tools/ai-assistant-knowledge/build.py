"""Build, validate, upload and drift-check AI Assistant's corpus.

Commands
--------
``check``      generate in memory, validate, print a summary (no writes)
``build``      write ``knowledge/ai-assistant/*.md`` + ``manifest.json``
``verify``     rebuild in memory and fail if the committed corpus differs (CI)
``upload``     put the corpus in S3 and register the document items, then wait
``bootstrap``  create the reserved ``platform-docs`` knowledge base once

Run from the repo root:

    python3 tools/ai-assistant-knowledge/build.py build
    python3 tools/ai-assistant-knowledge/build.py verify
    python3 tools/ai-assistant-knowledge/build.py upload
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import eval_cases  # noqa: E402
from generator import (  # noqa: E402
    MANIFEST_NAME,
    SCHEMA_VERSION,
    OUTPUT_DIR,
    build_documents,
    feature_catalogue,
)
from scope import (  # noqa: E402
    KB_DESCRIPTION,
    PLATFORM_CHUNK_OVERLAP,
    PLATFORM_CHUNK_SIZE,
    PLATFORM_EMBED_MODEL,
    PLATFORM_EMBEDDING_DIM,
    PLATFORM_IMAGE_EMBED_MODEL,
    PLATFORM_KB_ID,
    PLATFORM_KB_NAME,
    PLATFORM_USER_ID,
)
from sources import REPO_ROOT, load_routes  # noqa: E402
from validator import summary, validate  # noqa: E402

#: A section larger than this is subdivided, so the platform chunker (which packs
#: paragraph units greedily to its character budget) lands one heading-delimited
#: section — breadcrumb included — in one chunk. This is what makes retrieval
#: align with meaning without changing the shared chunker for user uploads.
MAX_SECTION_CHARS = 900


def normalize_for_chunking(document: Any) -> str:
    """Rewrite a document so each heading section is one retrieval-sized chunk.

    Every section keeps a breadcrumb heading, so a chunk retrieved from the middle
    of a long page still says which page and which part it came from — the single
    biggest retrieval win for a question-shaped corpus.
    """
    title = document.title
    body = document.body.strip()
    lines = body.splitlines()

    sections: list[tuple[str, list[str]]] = []
    heading = ""
    buffer: list[str] = []

    def flush() -> None:
        if buffer or heading:
            sections.append((heading, list(buffer)))

    for line in lines:
        if re.match(r"^#{1,6}\s+\S", line):
            flush()
            heading = line.lstrip("#").strip()
            buffer = []
            continue
        buffer.append(line)
    flush()

    out: list[str] = []
    for heading_text, chunk_lines in sections:
        text = "\n".join(chunk_lines).strip()
        if not text and not heading_text:
            continue
        parts = [title]
        # A section heading that merely repeats the document title must not be
        # repeated in the breadcrumb ("Platform limits > Platform limits > …").
        if heading_text and heading_text.strip().lower() != title.strip().lower():
            parts.append(heading_text)
        crumb = " > ".join(part for part in parts if part)
        for piece in _split_section(text):
            out.append(f"## {crumb}\n\n{piece}".strip())
    # The first line of a file is its title, so a file that starts with a
    # breadcrumb heading is fine — the section heading carries the page name.
    return "\n\n".join(out)


def _split_section(text: str) -> list[str]:
    """Split one section into <= MAX_SECTION_CHARS paragraphs-preserving pieces."""
    if not text:
        return [""]
    if len(text) <= MAX_SECTION_CHARS:
        return [text]

    pieces: list[str] = []
    current: list[str] = []
    size = 0
    for paragraph in re.split(r"\n\s*\n", text):
        block = paragraph.strip()
        if not block:
            continue
        if len(block) > MAX_SECTION_CHARS:
            # A single huge block (a long list or a code fence): split on lines.
            if current:
                pieces.append("\n\n".join(current))
                current, size = [], 0
            pieces.extend(_split_long_block(block))
            continue
        if size + len(block) > MAX_SECTION_CHARS and current:
            pieces.append("\n\n".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block) + 2
    if current:
        pieces.append("\n\n".join(current))
    return pieces


def _split_long_block(block: str) -> list[str]:
    out: list[str] = []
    current: list[str] = []
    size = 0
    for line in block.splitlines():
        if size + len(line) > MAX_SECTION_CHARS and current:
            out.append("\n".join(current))
            current, size = [], 0
        current.append(line)
        size += len(line) + 1
    if current:
        out.append("\n".join(current))
    return out


def render_document(document: Any) -> str:
    """The exact file contents for one document (normalised body)."""
    normalized = normalize_for_chunking(document)
    clone = type(document)(**{**document.__dict__, "body": normalized})
    return clone.render()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_manifest(documents: list[Any]) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for document in documents:
        rendered = render_document(document)
        entries.append(
            {
                "id": document.id,
                "title": document.title,
                "route": document.route,
                "group": document.group,
                "audience": document.audience,
                "source": document.source,
                "tags": list(document.tags),
                "fileName": document.filename,
                "chars": len(rendered),
                "hash": _content_hash(rendered),
            }
        )
    return {
        "schemaVersion": SCHEMA_VERSION,
        "kb": {
            "userId": PLATFORM_USER_ID,
            "name": PLATFORM_KB_NAME,
            "kbId": PLATFORM_KB_ID,
            "chunkSize": PLATFORM_CHUNK_SIZE,
            "chunkOverlap": PLATFORM_CHUNK_OVERLAP,
        },
        "count": len(entries),
        "documents": entries,
    }


# --------------------------------------------------------------------------- #
# Commands                                                                     #
# --------------------------------------------------------------------------- #


def _load() -> tuple[list[Any], list[Any]]:
    """Generate the raw documents and validate the **rendered** corpus.

    Rendering is a pure function of the raw document, so validation and writing
    both call :func:`render_document`. Nothing here mutates a document (doing so
    would normalise twice and double the breadcrumb).
    """
    documents = build_documents()
    rendered = [render_document(document) for document in documents]
    return documents, validate(documents, load_routes(), rendered=rendered)


#: The route catalogue the agent validates deep links against. It is generated
#: into the service package (not the corpus) because it is code-facing data: the
#: agent refuses to propose a route that is not in it.
FEATURES_PATH = REPO_ROOT / "backend" / "ai-assistant" / "src" / "features.json"

#: The example questions the widget opens with. Generated from the **backend's**
#: canonical list so the nudge examples and the starters cannot drift apart.
STARTERS_PATH = REPO_ROOT / "frontend" / "src" / "content" / "aiAssistantStarters.ts"

#: The evaluation dataset. Committed so a change to it is reviewable, and
#: regenerated with the corpus so it never names a page that no longer exists.
EVAL_PATH = REPO_ROOT / "tools" / "ai-assistant-knowledge" / "eval" / "ai-assistant-eval.jsonl"


def render_starters() -> str:
    """Emit the frontend starters from ``backend/ai-assistant/ai-assistant/examples.py``."""
    packages = REPO_ROOT / "backend" / "packages"
    service = REPO_ROOT / "backend" / "ai-assistant"
    for extra in (service, packages):
        if str(extra) not in sys.path:
            sys.path.insert(0, str(extra))

    from src import examples  # noqa: PLC0415

    by_route = {
        route: list(questions) for route, questions in sorted(examples.BY_ROUTE.items())
    }
    general = list(examples.GENERAL)
    max_examples = int(examples.MAX_EXAMPLES)
    starter_count = int(examples.STARTER_COUNT)
    starter_route_count = int(examples.STARTER_ROUTE_COUNT)

    body = json.dumps(by_route, indent=2)
    general_body = json.dumps(general, indent=2)
    return (
        "/**\n"
        " * Example questions AI Assistant offers — GENERATED, do not edit by hand.\n"
        " *\n"
        " * Source of truth: `backend/ai-assistant/ai-assistant/examples.py` (the same list the\n"
        " * off-topic nudge ships as tappable chips). Regenerate with\n"
        " * `make ai-assistant-knowledge`; CI fails if this file is stale.\n"
        " */\n"
        "\n"
        f"export const MAX_EXAMPLES = {max_examples}\n"
        "\n"
        f"export const STARTER_COUNT = {starter_count}\n"
        f"export const STARTER_ROUTE_COUNT = {starter_route_count}\n"
        "\n"
        "export const AI_ASSISTANT_GENERAL_EXAMPLES: string[] = "
        f"{general_body}\n"
        "\n"
        "export const AI_ASSISTANT_ROUTE_EXAMPLES: Record<string, string[]> = "
        f"{body}\n"
        "\n"
        "/** Route-specific questions first, then the general pool. Deterministic. */\n"
        "export function examplesFor(pathname: string, limit = MAX_EXAMPLES): string[] {\n"
        "  const specific = matchRoute(pathname)\n"
        "  const combined = [...specific, ...AI_ASSISTANT_GENERAL_EXAMPLES.filter((q) => !specific.includes(q))]\n"
        "  return combined.slice(0, Math.max(1, limit))\n"
        "}\n"
        "\n"
        "/**\n"
        " * The questions the dialog opens with.\n"
        " *\n"
        " * A couple from this page plus a random sample of the general pool, so opening\n"
        " * AI Assistant again offers something different instead of the same static four. Called\n"
        " * once per opening (the caller memoises on `open`), not per render.\n"
        " */\n"
        "export function startersFor(pathname: string, count = STARTER_COUNT): string[] {\n"
        "  const specific = shuffle(matchRoute(pathname)).slice(0, STARTER_ROUTE_COUNT)\n"
        "  const chosen = new Set(specific)\n"
        "  const rest = shuffle(AI_ASSISTANT_GENERAL_EXAMPLES).filter((q) => !chosen.has(q))\n"
        "  return [...specific, ...rest].slice(0, Math.max(1, count))\n"
        "}\n"
        "\n"
        "function shuffle<T>(items: T[]): T[] {\n"
        "  const out = [...items]\n"
        "  for (let i = out.length - 1; i > 0; i -= 1) {\n"
        "    const j = Math.floor(Math.random() * (i + 1))\n"
        "    ;[out[i], out[j]] = [out[j], out[i]]\n"
        "  }\n"
        "  return out\n"
        "}\n"
        "\n"
        "function matchRoute(pathname: string): string[] {\n"
        "  const path = pathname.split('?')[0].split('#')[0]\n"
        "  let best: string[] = []\n"
        "  let bestLength = 0\n"
        "  for (const [prefix, questions] of Object.entries(AI_ASSISTANT_ROUTE_EXAMPLES)) {\n"
        "    if (path === prefix || path.startsWith(`${prefix}/`)) {\n"
        "      if (prefix.length > bestLength) {\n"
        "        best = questions\n"
        "        bestLength = prefix.length\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "  return best\n"
        "}\n"
    )


def render_features() -> str:
    catalogue = feature_catalogue(load_routes())
    return json.dumps(catalogue, indent=2, sort_keys=True) + "\n"


def cmd_check() -> int:
    documents, problems = _load()
    print(summary(documents))
    catalogue = feature_catalogue(load_routes())
    print(
        f"routes    : {len(catalogue['paths'])} static · "
        f"{len(catalogue['dynamicPrefixes'])} dynamic · "
        f"{len(catalogue['features'])} catalogue rows"
    )
    print(f"eval      : {eval_cases.summary(eval_cases.build_cases())}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\ncorpus is valid")
    return 0


def cmd_build() -> int:
    documents, problems = _load()
    if problems:
        print(f"{len(problems)} problem(s) — refusing to write the corpus:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {document.filename for document in documents}
    for stale in OUTPUT_DIR.glob("*.md"):
        if stale.name not in wanted:
            # A renamed or removed section would otherwise linger in the index.
            stale.unlink()
            print(f"removed stale {stale.name}")

    for document in documents:
        path = OUTPUT_DIR / document.filename
        path.write_text(render_document(document), encoding="utf-8")

    manifest = build_manifest(documents)
    (OUTPUT_DIR / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # The route allow-list lives with the service, so the agent can refuse to
    # propose a link that does not exist.
    FEATURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    FEATURES_PATH.write_text(render_features(), encoding="utf-8")
    STARTERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STARTERS_PATH.write_text(render_starters(), encoding="utf-8")

    cases = eval_cases.build_cases()
    EVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    EVAL_PATH.write_text(eval_cases.render_jsonl(cases), encoding="utf-8")

    print(summary(documents))
    print(f"\nwrote {len(documents)} documents to {OUTPUT_DIR.relative_to(REPO_ROOT)}")
    print(f"wrote the route catalogue to {FEATURES_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote the widget starters to {STARTERS_PATH.relative_to(REPO_ROOT)}")
    print(f"wrote {eval_cases.summary(cases)} to {EVAL_PATH.relative_to(REPO_ROOT)}")
    return 0


def cmd_verify() -> int:
    """Fail when the committed corpus is not what the repository would produce."""
    documents, problems = _load()
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    if not OUTPUT_DIR.exists():
        print(f"corpus directory {OUTPUT_DIR} is missing — run `make ai-assistant-knowledge`")
        return 1

    drifted: list[str] = []
    for document in documents:
        path = OUTPUT_DIR / document.filename
        expected = render_document(document)
        if not path.exists():
            drifted.append(f"missing: {document.filename}")
        elif path.read_text(encoding="utf-8") != expected:
            drifted.append(f"changed: {document.filename}")

    committed = {path.name for path in OUTPUT_DIR.glob("*.md")}
    expected_names = {document.filename for document in documents}
    drifted.extend(f"stale: {name}" for name in sorted(committed - expected_names))

    manifest = json.loads((OUTPUT_DIR / MANIFEST_NAME).read_text(encoding="utf-8"))
    if manifest.get("count") != len(documents):
        drifted.append("manifest count is out of date")

    if not FEATURES_PATH.exists():
        drifted.append("missing: backend/ai-assistant/ai-assistant/features.json")
    elif FEATURES_PATH.read_text(encoding="utf-8") != render_features():
        drifted.append("changed: backend/ai-assistant/ai-assistant/features.json (a route moved)")

    if not STARTERS_PATH.exists():
        drifted.append("missing: frontend/src/content/aiAssistantStarters.ts")
    elif STARTERS_PATH.read_text(encoding="utf-8") != render_starters():
        drifted.append("changed: frontend/src/content/aiAssistantStarters.ts (examples moved)")

    cases = eval_cases.build_cases()
    if not EVAL_PATH.exists():
        drifted.append("missing: tools/ai-assistant-knowledge/eval/ai-assistant-eval.jsonl")
    elif EVAL_PATH.read_text(encoding="utf-8") != eval_cases.render_jsonl(cases):
        drifted.append("changed: tools/ai-assistant-knowledge/eval/ai-assistant-eval.jsonl (corpus moved)")

    if drifted:
        print("AI Assistant's corpus is out of date — run `make ai-assistant-knowledge` and commit it:")
        for item in drifted[:40]:
            print(f"  - {item}")
        if len(drifted) > 40:
            print(f"  … and {len(drifted) - 40} more")
        return 1

    print(summary(documents))
    print("\ncorpus matches the repository")
    return 0


def _require_backend() -> None:
    packages = REPO_ROOT / "backend" / "packages"
    if str(packages) not in sys.path:
        sys.path.insert(0, str(packages))


def cmd_bootstrap() -> int:
    """Create (or confirm) the reserved knowledge base. Idempotent."""
    _require_backend()
    from data.repositories import knowledge_bases as kb_repo  # noqa: PLC0415

    existing = kb_repo.get_kb(PLATFORM_USER_ID, PLATFORM_KB_ID)
    if existing:
        print(
            f"platform knowledge base already exists: {existing.get('name')} "
            f"({existing.get('kbId')}) status={existing.get('status')}"
        )
        return 0

    item = kb_repo.create_kb(
        PLATFORM_USER_ID,
        kb_id=PLATFORM_KB_ID,
        name=PLATFORM_KB_NAME,
        description=KB_DESCRIPTION,
        status="ready",
        embed_model=PLATFORM_EMBED_MODEL,
        image_embed_model=PLATFORM_IMAGE_EMBED_MODEL,
        embedding_dim=PLATFORM_EMBEDDING_DIM,
        chunk_size=PLATFORM_CHUNK_SIZE,
        chunk_overlap=PLATFORM_CHUNK_OVERLAP,
    )
    print(f"created knowledge base {item['name']} ({item['kbId']})")
    print(
        "next: python3 tools/ai-assistant-knowledge/build.py upload   "
        "(writes raw/platform/… so the ingestion pipeline picks it up)"
    )
    return 0


#: Every corpus document id starts with this, so a prune can never touch anything
#: else that happens to live in the reserved platform knowledge base.
DOC_ID_PREFIX = "ai-assistant-"


def vector_store_mode() -> str:
    """The vector store ``retrieval.s3_vectors`` will use, resolved the same way.

    Mirrored rather than imported so this stays a *report* — the deployed corpus
    lives in **S3 Vectors**, while this tool runs outside the Lambda that has that
    environment, so an operator has to be told when the vectors were not purged.
    """
    return (
        os.environ.get("VECTOR_STORE")
        or os.environ.get("VECTOR_MODE")
        or ("s3vectors" if os.environ.get("S3_VECTOR_BUCKET") else "local")
    ).strip().lower()


def prune_removed_documents(
    kb_id: str, keep_ids: set[str], *, storage: Any | None = None
) -> list[str]:
    """Delete ``ai-assistant-*`` documents that are no longer in the corpus.

    The corpus is **generated**, so it is authoritative: an ingest reconciles
    rather than only adding. Without this, a document deleted from the repository
    stays in the index forever and keeps being cited — which is exactly how an
    admin-console page survived its own removal from `knowledge/ai-assistant/`, and why a
    re-ingest alone could not fix an answer that named it.

    Returns the removed document ids. A failure on one document is reported and
    skipped: a stale document is bad, but an aborted ingest is worse.
    """
    from core.storage import Storage  # noqa: PLC0415
    from data.repositories import documents as docs_repo  # noqa: PLC0415
    from data.repositories import events as events_repo  # noqa: PLC0415
    from retrieval import layout  # noqa: PLC0415
    from retrieval.maintenance import delete_document_index  # noqa: PLC0415
    from retrieval.s3_vectors import vector_store  # noqa: PLC0415

    storage = storage or Storage()
    store = vector_store(storage)
    removed: list[str] = []
    for item in docs_repo.list_documents(kb_id):
        doc_id = str(item.get("docId") or "")
        if not doc_id.startswith(DOC_ID_PREFIX) or doc_id in keep_ids:
            continue
        try:
            # The same sequence user-api uses to delete a document, so the
            # vectors, postings, parents, manifest and staged artifacts all go.
            delete_document_index(storage, store, PLATFORM_USER_ID, doc_id)
            events_repo.delete_events_for_document(doc_id)
            docs_repo.delete_document(doc_id)
            storage.delete_prefix(
                f"{layout.RAW_PREFIX}/{PLATFORM_USER_ID}/{kb_id}/{doc_id}/"
            )
            storage.delete_prefix(
                f"{layout.DERIVED_PREFIX}/{PLATFORM_USER_ID}/{kb_id}/{doc_id}/"
            )
            removed.append(doc_id)
        except Exception as exc:  # noqa: BLE001 - report and keep going
            print(f"  could not prune {doc_id}: {exc}", file=sys.stderr)
    return removed


def cmd_upload() -> int:
    """Put the corpus in S3 and register each document, then wait for indexing."""
    documents, problems = _load()
    if problems:
        print(f"{len(problems)} problem(s) — refusing to upload:")
        for problem in problems:
            print(f"  - {problem}")
        return 1

    _require_backend()
    from core.storage import Storage  # noqa: PLC0415
    from data.repositories import documents as docs_repo  # noqa: PLC0415
    from data.repositories import knowledge_bases as kb_repo  # noqa: PLC0415
    from retrieval.layout import raw_key  # noqa: PLC0415

    kb = kb_repo.get_kb(PLATFORM_USER_ID, PLATFORM_KB_ID)
    if not kb:
        print("the platform knowledge base does not exist — run `bootstrap` first")
        return 1

    storage = Storage()
    kb_id = str(kb["kbId"])

    # Reconcile first: a document dropped from the corpus must stop being
    # answerable, and only a prune removes it from the index.
    keep = {f"{DOC_ID_PREFIX}{document.id}" for document in documents}
    pruned = prune_removed_documents(kb_id, keep, storage=storage)
    if pruned:
        print(f"pruned {len(pruned)} document(s) no longer in the corpus: {', '.join(pruned)}")
        if vector_store_mode() != "s3vectors":
            # The deployed KB's vectors are in S3 Vectors and only the Lambda that
            # owns that environment can reach them. The DynamoDB items, parents,
            # postings and manifests are gone either way, so a stale vector is
            # dropped at hydration rather than answered — but say so.
            print(
                "  note: vector entries were purged with VECTOR_STORE="
                f"{vector_store_mode()}. Against the deployed corpus, re-run with "
                "VECTOR_STORE=s3vectors (and S3_VECTOR_BUCKET) to remove them too."
            )

    uploaded = 0
    for document in documents:
        text = render_document(document)
        doc_id = f"ai-assistant-{document.id}"
        key = raw_key(PLATFORM_USER_ID, kb_id, doc_id, document.filename)
        storage.put_bytes(key, text.encode("utf-8"), "text/markdown")

        item = docs_repo.document_item(
            doc_id=doc_id,
            kb_id=kb_id,
            user_id=PLATFORM_USER_ID,
            file_name=document.filename,
            s3_key=key,
            content_type="text/markdown",
            size_bytes=len(text.encode("utf-8")),
            source="upload",
            status="processing",
            content_hash=_content_hash(text),
        )
        docs_repo.put_document(item)
        uploaded += 1
        if uploaded % 10 == 0:
            print(f"  uploaded {uploaded}/{len(documents)}")

    print(f"uploaded {uploaded} documents to raw/{PLATFORM_USER_ID}/{kb_id}/")
    kb_repo.set_doc_count(kb_id, len(documents))
    print("the ingestion pipeline will extract, embed and index them next")
    print(f"check status: python3 {_rel(__file__)} status")
    return 0


def cmd_status() -> int:
    _require_backend()
    from data.repositories import documents as docs_repo  # noqa: PLC0415

    items = docs_repo.list_documents(PLATFORM_KB_ID)
    counts: dict[str, int] = {}
    for item in items:
        status = str(item.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    total = len(items)
    print(f"{total} documents in {PLATFORM_KB_NAME}")
    for status, count in sorted(counts.items()):
        print(f"  {status:<12} {count}")
    return 0 if counts.get("ready", 0) == total and total else 1


def cmd_wait(timeout: int = 900, interval: int = 10) -> int:
    """Poll until every platform document is ready (or the timeout expires)."""
    _require_backend()
    from data.repositories import documents as docs_repo  # noqa: PLC0415

    deadline = time.time() + timeout
    while True:
        items = docs_repo.list_documents(PLATFORM_KB_ID)
        statuses = [str(item.get("status") or "unknown") for item in items]
        pending = [s for s in statuses if s not in ("ready", "failed")]
        failed = statuses.count("failed")
        print(
            f"  {statuses.count('ready')}/{len(statuses)} ready"
            + (f", {failed} failed" if failed else "")
            + (f", {len(pending)} in flight" if pending else "")
        )
        if items and not pending:
            return 0 if failed == 0 else 1
        if time.time() > deadline:
            print("timed out waiting for ingestion")
            return 1
        time.sleep(interval)


def _rel(path: str) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Assistant corpus build tool")
    parser.add_argument(
        "command",
        choices=("check", "build", "verify", "bootstrap", "upload", "status", "wait"),
    )
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)

    # A corpus build must never need AWS credentials or a network.
    os.environ.setdefault("AWS_DEFAULT_REGION", "ap-south-1")

    if args.command == "check":
        return cmd_check()
    if args.command == "build":
        return cmd_build()
    if args.command == "verify":
        return cmd_verify()
    if args.command == "bootstrap":
        return cmd_bootstrap()
    if args.command == "upload":
        return cmd_upload()
    if args.command == "status":
        return cmd_status()
    return cmd_wait(timeout=args.timeout)


if __name__ == "__main__":
    raise SystemExit(main())

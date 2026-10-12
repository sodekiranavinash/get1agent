"""Ingest Avi's corpus into the **local** Floci stack, from the host.

`make avi-bootstrap` / `make avi-upload` are for the deployed platform: they rely
on the S3 → EventBridge → Step Functions pipeline to pick the corpus up. Locally
that machinery exists but is fiddly to drive from a shell, and there is no reason
to: the three ingestion stages are plain Python functions, so this script calls
them in order, in-process. Same extract → chunk → embed → index code as
production, just without the queue in front of it.

Requires the local stack (`make floci`): DynamoDB Local on :8000, Floci on
:4566 and Ollama for embeddings (`EMBED_MODE=local`).

    python3 tools/avi-knowledge/local_ingest.py

Then point the widget at a local agent service and ask it something.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import local_env  # noqa: E402  (same directory)

# Endpoints, credentials and local mode come from one place so the ingest and the
# agent service cannot disagree about where the stack is.
local_env.apply()

BACKEND = REPO_ROOT / "backend"
for extra in (BACKEND / "packages", BACKEND / "avi"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import build as corpus  # noqa: E402  (the generator/validator CLI)
import scope  # noqa: E402

from core.storage import Storage  # noqa: E402
from data.repositories import documents as docs_repo  # noqa: E402
from data.repositories import knowledge_bases as kb_repo  # noqa: E402
from ingestion import actions  # noqa: E402
from retrieval.layout import raw_key  # noqa: E402


def _check_stack() -> None:
    """Fail early with a useful message rather than a boto stack trace."""
    from data import client

    try:
        status = client.table().meta.client.describe_table(
            TableName=client.table_name()
        )["Table"]["TableStatus"]
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(
            f"Local DynamoDB is not reachable at "
            f"{os.environ['DYNAMODB_ENDPOINT_URL']} ({type(exc).__name__}).\n"
            "Start the stack with `make floci` and try again."
        ) from exc
    print(f"  dynamodb   {client.table_name()} ({status})")

    storage = Storage()
    try:
        storage.put_bytes("avi/local-check", b"ok", "text/plain")
        storage.delete("avi/local-check")
    except Exception as exc:  # noqa: BLE001 - report the real reason, not just its type
        raise SystemExit(
            f"S3 is not reachable at {os.environ['S3_ENDPOINT_URL']} "
            f"({type(exc).__name__}: {exc}). Is the Floci container up?"
        ) from exc
    print(f"  s3         {os.environ['S3_BUCKET']} (storage mode: {storage.mode})")


def _ensure_kb() -> dict:
    existing = kb_repo.get_kb(scope.PLATFORM_USER_ID, scope.PLATFORM_KB_ID)
    if existing:
        print(f"  knowledge base already present: {existing.get('name')}")
        return existing
    item = kb_repo.create_kb(
        scope.PLATFORM_USER_ID,
        kb_id=scope.PLATFORM_KB_ID,
        name=scope.PLATFORM_KB_NAME,
        description=scope.KB_DESCRIPTION,
        status="ready",
        embed_model=scope.PLATFORM_EMBED_MODEL,
        image_embed_model=scope.PLATFORM_IMAGE_EMBED_MODEL,
        embedding_dim=scope.PLATFORM_EMBEDDING_DIM,
        chunk_size=scope.PLATFORM_CHUNK_SIZE,
        chunk_overlap=scope.PLATFORM_CHUNK_OVERLAP,
    )
    print(f"  created knowledge base {item['name']} ({item['kbId']})")
    return item


def _upload(documents: list, kb_id: str) -> list[dict]:
    """Write each document to raw/ and register it, exactly as the real upload does."""
    storage = Storage()

    # Reconcile first: a document dropped from the corpus must stop being
    # answerable, and only a prune removes it from the local index. Without this a
    # re-ingest would leave the removed page citable forever.
    keep = {f"{corpus.DOC_ID_PREFIX}{document.id}" for document in documents}
    pruned = corpus.prune_removed_documents(kb_id, keep, storage=storage)
    if pruned:
        print(f"  pruned {len(pruned)} stale document(s): {', '.join(pruned)}")

    registered: list[dict] = []
    for document in documents:
        text = corpus.render_document(document)
        doc_id = f"avi-{document.id}"
        key = raw_key(scope.PLATFORM_USER_ID, kb_id, doc_id, document.filename)
        storage.put_bytes(key, text.encode("utf-8"), "text/markdown")

        item = docs_repo.document_item(
            doc_id=doc_id,
            kb_id=kb_id,
            user_id=scope.PLATFORM_USER_ID,
            file_name=document.filename,
            s3_key=key,
            content_type="text/markdown",
            size_bytes=len(text.encode("utf-8")),
            source="upload",
            # `uploaded`, not `pending`: the extract stage refuses a pending
            # document because in production it is still being PUT.
            status="uploaded",
            content_hash=None,
        )
        docs_repo.put_document(item)
        registered.append(item)
    kb_repo.set_doc_count(kb_id, len(registered))
    print(f"  uploaded {len(registered)} documents under raw/{scope.PLATFORM_USER_ID}/{kb_id}/")
    return registered


def _ingest(items: list[dict], *, timeout_seconds: int = 1800) -> int:
    """Run extract → embed → index for every document, in-process."""
    kb_id = str(items[0]["kbId"]) if items else scope.PLATFORM_KB_ID
    failures: list[tuple[str, str]] = []
    started = time.perf_counter()

    for index, item in enumerate(items, 1):
        doc_id = str(item["docId"])
        event = {
            "documentId": doc_id,
            "knowledgeBaseId": kb_id,
            "userId": scope.PLATFORM_USER_ID,
        }
        try:
            # Each stage returns the keys the next one needs. In production the
            # Step Functions definition threads them through; locally we do it by
            # hand, which is the only difference from the real pipeline.
            extracted = actions.extract_action(dict(event))
            embedded = actions.embed_action({**event, **extracted})
            actions.index_action({**event, **extracted, **embedded})
        except Exception as exc:  # noqa: BLE001 - report, do not abort the batch
            failures.append((doc_id, f"{type(exc).__name__}: {exc}"))
        if index % 10 == 0 or index == len(items):
            print(f"    {index}/{len(items)} ingested")
        if time.perf_counter() - started > timeout_seconds:
            print(f"  stopping after {timeout_seconds}s (raise the timeout to continue)")
            break

    if failures:
        print(f"\n  {len(failures)} document(s) failed:")
        for doc_id, message in failures[:10]:
            print(f"    {doc_id}: {message[:160]}")
    return len(failures)


def main() -> int:
    print("Avi local ingest")
    print("  checking the local stack…")
    _check_stack()

    documents, problems = corpus._load()
    if problems:
        print(f"\n{len(problems)} corpus problem(s) — refusing to ingest:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"  corpus     {len(documents)} documents")

    kb = _ensure_kb()
    items = _upload(documents, str(kb["kbId"]))

    print("  ingesting (extract → embed → index)…")
    failures = _ingest(items)

    statuses: dict[str, int] = {}
    for item in docs_repo.list_documents(str(kb["kbId"])):
        status = str(item.get("status") or "unknown")
        statuses[status] = statuses.get(status, 0) + 1
    print(f"\n  status: {statuses}")

    ready = statuses.get("ready", 0)
    if failures or ready != len(items):
        print(f"\n{ready}/{len(items)} ready — see the failures above.")
        return 1

    print(f"\nAll {ready} documents are ready.")
    print("\nNext: run the agent service locally and point the widget at it:")
    print("  AVI_SESSION_SECRET=local-dev-secret AVI_MODE=local \\")
    print("  PYTHONPATH=backend/packages backend/avi/.venv/bin/python backend/avi/main.py")
    print("  then in frontend/.env.local:")
    print("    printf 'VITE_AVI_URL=http://localhost:8091\\\\nVITE_AVI_MICROVM=false\\\\n' > frontend/.env.local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

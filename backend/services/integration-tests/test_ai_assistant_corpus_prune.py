"""The AI Assistant corpus is generated, so an ingest must reconcile — not just add.

Removing a document from `knowledge/ai-assistant/` does nothing to an index that already
holds it: the page stays answerable and keeps being cited. That is how an
admin-console page outlived its own removal, and why "re-run the ingest" was not
enough to fix an answer that named it. Both ingest paths now prune first
(`build.prune_removed_documents`), and this pins the two properties that matter:
stale corpus documents go, and nothing outside the corpus is ever touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from support import REPO_ROOT, FakeStorage, load_module

TOOLS = REPO_ROOT / "tools" / "ai-assistant-knowledge"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

build = load_module("tools/ai-assistant-knowledge/build.py", "avi_corpus_build")

from data.repositories import documents as docs_repo  # noqa: E402

KB_ID = "kb_platform_docs_0001"
SUB = "platform"


def _register(doc_id: str, file_name: str) -> None:
    docs_repo.put_document(
        docs_repo.document_item(
            doc_id=doc_id,
            kb_id=KB_ID,
            user_id=SUB,
            file_name=file_name,
            s3_key=f"raw/{SUB}/{KB_ID}/{doc_id}/{file_name}",
            content_type="text/markdown",
            size_bytes=10,
            source="upload",
            status="ready",
            content_hash=None,
        )
    )


def _ids() -> set[str]:
    return {str(item.get("docId")) for item in docs_repo.list_documents(KB_ID)}


@pytest.fixture(autouse=True)
def _bucket():
    import boto3

    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="get1agent-test-bucket")
    yield


def test_prune_removes_only_stale_corpus_documents():
    storage = FakeStorage()
    # A live corpus document, one dropped from the corpus, and — critically —
    # something else living in the same reserved knowledge base.
    _register("ai-assistant-keep-me", "keep-me.md")
    _register("ai-assistant-removed-page", "removed-page.md")
    _register("other-document", "other.md")

    removed = build.prune_removed_documents(KB_ID, {"ai-assistant-keep-me"}, storage=storage)

    assert removed == ["ai-assistant-removed-page"]
    assert _ids() == {"ai-assistant-keep-me", "other-document"}


def test_prune_is_a_no_op_when_the_corpus_is_unchanged():
    storage = FakeStorage()
    _register("ai-assistant-a", "a.md")
    _register("ai-assistant-b", "b.md")

    assert build.prune_removed_documents(KB_ID, {"ai-assistant-a", "ai-assistant-b"}, storage=storage) == []
    assert _ids() == {"ai-assistant-a", "ai-assistant-b"}


def test_prune_deletes_the_stale_documents_s3_artifacts():
    storage = FakeStorage()
    _register("ai-assistant-gone", "gone.md")
    raw = f"raw/{SUB}/{KB_ID}/ai-assistant-gone/gone.md"
    derived = f"derived/{SUB}/{KB_ID}/ai-assistant-gone/text.md"
    storage.put_bytes(raw, b"# gone")
    storage.put_bytes(derived, b"text")

    build.prune_removed_documents(KB_ID, set(), storage=storage)

    assert raw not in storage.data
    assert derived not in storage.data


def test_the_keep_set_is_built_from_the_corpus_document_ids():
    """The ids the prune protects are exactly the ones an ingest writes."""
    documents = build.build_documents()
    keep = {f"{build.DOC_ID_PREFIX}{document.id}" for document in documents}
    # Nothing admin-console may be in the corpus that an ingest would keep alive.
    assert not any("admin" in doc_id for doc_id in keep)
    assert keep and all(doc_id.startswith("ai-assistant-") for doc_id in keep)

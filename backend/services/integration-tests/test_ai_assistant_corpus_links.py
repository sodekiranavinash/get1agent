"""Every link AI Assistant offers must open something real.

Two ways a citation can lie, both of which shipped:

* a documentation section that documents a **page** linked to `/docs#<id>` — a trip
  to the docs to read about the page you asked for, instead of the page itself;
* a FAQ/troubleshooting spin-off linked to its own synthetic anchor
  (`/docs#faq-do-i-need-a-bedrock-account-0`), which exists nowhere in the DOM, so
  clicking it did nothing at all.

The anchors the Documentation page renders are read from `docs.ts` through the
generator, and the validator now rejects a fragment that is not one of them — these
tests pin that from the outside, against the committed corpus.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from support import REPO_ROOT

TOOLS = REPO_ROOT / "tools" / "ai-assistant-knowledge"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import build  # noqa: E402
import sources  # noqa: E402
from generator import Document  # noqa: E402
from validator import validate  # noqa: E402

#: Routes that take an id, so they can never be a document's own route.
DYNAMIC = ":"


@pytest.fixture(scope="module")
def documents():
    return build.build_documents()


@pytest.fixture(scope="module")
def known_routes() -> set[str]:
    return {route.path for route in sources.load_routes()}


def _is_openable(path: str, known_routes: set[str]) -> bool:
    if path in known_routes:
        return True
    for known in known_routes:
        if DYNAMIC in known:
            prefix = known.split(":", 1)[0].rstrip("/")
            if prefix and (path == prefix or path.startswith(prefix + "/")):
                return True
    return False


def test_every_document_route_is_openable(documents, known_routes):
    anchors = sources.doc_anchors()
    for document in documents:
        path, _, fragment = document.route.partition("#")
        if fragment:
            assert path == "/docs", f"{document.id}: unexpected fragment on {path}"
            assert fragment in anchors, (
                f"{document.id} links to {document.route}, "
                "which the Documentation page does not render"
            )
        else:
            assert _is_openable(path, known_routes), (
                f"{document.id} links to {path}, which is not a real route"
            )


def test_a_documented_page_links_to_the_page_not_to_the_docs(documents):
    """The point of the fix: `agent-builder` cites `/agent-builder`."""
    route_of = {document.id: document.route for document in documents}
    assert route_of["agent-builder"] == "/agent-builder"
    assert route_of["knowledge-bases"] == "/knowledge-bases"
    assert route_of["workflow-builder"] == "/workflow-builder"
    # Sections whose page name differs from their docs id.
    assert route_of["schedules"] == "/scheduled-jobs"
    assert route_of["mcp-tools"] == "/tools"
    assert route_of["agents-library"] == "/agent-store"
    assert route_of["workflows-store"] == "/workflow-store"


def test_only_concept_content_falls_back_to_a_docs_anchor(documents):
    """A `/docs#…` link is now the exception, not the default."""
    anchored = [document for document in documents if "#" in document.route]
    assert anchored, "expected the FAQ and concepts sections to stay on the docs page"
    assert {document.route for document in anchored} <= {
        "/docs#faq",
        "/docs#troubleshooting",
        "/docs#getting-started",
        "/docs#concepts",
    }
    # Well under half the corpus: most of it points at a real page.
    assert len(anchored) < len(documents) / 2


def test_a_faq_spinoff_links_to_its_section(documents):
    spinoffs = [
        document
        for document in documents
        if document.id.startswith(("faq-", "troubleshooting-"))
    ]
    assert spinoffs, "the FAQ/troubleshooting questions should be their own documents"
    for document in spinoffs:
        assert document.route in ("/docs#faq", "/docs#troubleshooting"), document.route


def test_the_validator_rejects_a_dangling_docs_anchor(known_routes):
    """The guard that makes the old bug unshippable."""
    probe = Document(
        id="probe-doc",
        title="Probe",
        route="/docs#faq-do-i-need-a-bedrock-or-openai-account-0",
        group="Help",
        audience="user",
        source="docs",
        tags=["probe"],
        body="x" * 400,
    )
    problems = [p for p in validate([probe], sources.load_routes()) if "anchor" in p.message]
    assert problems, "a citation pointing at a non-existent anchor must fail the build"


def test_the_committed_corpus_is_valid(documents, known_routes):
    """What CI runs, asserted here too: the shipped corpus has no broken link."""
    assert validate(documents, sources.load_routes()) == []

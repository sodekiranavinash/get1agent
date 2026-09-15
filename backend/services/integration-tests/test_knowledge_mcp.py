"""knowledge-mcp: MCP transport + hybrid search over DynamoDB + S3."""

from __future__ import annotations

import json

from support import load_module, patch_pipeline, patch_search

handler = load_module("backend/services/knowledge-mcp/handler.py", "knowledge_mcp_handler")

from data.repositories import documents, knowledge_bases as kb, tags  # noqa: E402
from data.repositories import users  # noqa: E402
from retrieval.embedding.config import load_config  # noqa: E402
from ingestion.pipeline import index_document  # noqa: E402
from retrieval.layout import chunks_key, embeddings_key  # noqa: E402

SUB = "auth0|mcp"
KB_ID = "kb-mcp"
DOC_ID = "doc-mcp"

USER_ID: str | None = None


def _setup(fake, monkeypatch) -> None:
    global USER_ID
    patch_pipeline(monkeypatch, fake)
    patch_search(monkeypatch, fake)
    monkeypatch.setattr(handler, "embed_texts", lambda texts, cfg: [[0.9, 0.1, 0.0]])

    profile = users.upsert_user(
        {"sub": SUB, "https://get1agent.com/email": "mcp@example.com"}
    )
    USER_ID = profile["userId"]
    user_id = USER_ID
    kb.create_kb(
        user_id,
        kb_id=KB_ID,
        name="kmcp-kb",
        description="d",
        status="ready",
        embed_model="m",
        image_embed_model="im",
        embedding_dim=3,
        chunk_size=512,
        chunk_overlap=64,
    )
    doc = documents.document_item(
        doc_id=DOC_ID,
        kb_id=KB_ID,
        user_id=user_id,
        file_name="resume.pdf",
        s3_key="raw/x",
        content_type="application/pdf",
        size_bytes=10,
        source="upload",
        status="ready",
    )
    documents.put_document(doc)
    tags.replace_tags(user_id, DOC_ID, KB_ID, doc["fileKey"], [("Resume", "cv")])

    chunks_path = chunks_key(user_id, KB_ID, DOC_ID)
    embeddings_path = embeddings_key(user_id, KB_ID, DOC_ID)
    fake.put_json(
        chunks_path,
        {
            "parents": [
                {"ordinal": 0, "page": 1, "pageEnd": 1, "text": "The personal project is a resume parser."}
            ],
            "chunks": [
                {
                    "text": "The personal project is a resume parser built with Python.",
                    "page": 1,
                    "pageEnd": 1,
                    "parentOrdinal": 0,
                }
            ],
        },
    )
    fake.put_json(
        embeddings_path,
        {
            "dimension": 3,
            "textModel": "m",
            "imageModel": "im",
            "chunkVectors": [[1.0, 0.0, 0.0]],
            "imageVectors": [],
        },
    )
    index_document(
        fake,
        load_config(),
        user_id=user_id,
        knowledge_base_id=KB_ID,
        document_id=DOC_ID,
        chunks_key=chunks_path,
        embeddings_key=embeddings_path,
        images=[],
        file_name="resume.pdf",
        kb_name="kmcp-kb",
    )


def _invoke(method: str, params: dict | None = None, request_id: int = 1) -> dict:
    event = {"jsonrpc": "2.0", "id": request_id, "method": method, "userId": USER_ID}
    if params is not None:
        event["params"] = params
    return handler.lambda_handler(event, None)


def test_tools_list(fake_storage, monkeypatch):
    _setup(fake_storage, monkeypatch)
    response = _invoke("tools/list")
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert "search-user-knowledge-bases" in names
    assert "get-user-knowledge-bases" in names


def test_search_tool(fake_storage, monkeypatch):
    _setup(fake_storage, monkeypatch)
    response = _invoke(
        "tools/call",
        {
            "name": "search-user-knowledge-bases",
            "arguments": {"query": "personal project resume", "knowledgeBaseNames": ["kmcp-kb"]},
        },
        request_id=2,
    )
    body = json.loads(response["result"]["content"][0]["text"])
    assert body["chunks"], body
    assert body["chunks"][0]["documentId"] == DOC_ID
    assert body["chunks"][0]["kbName"] == "kmcp-kb"
    assert body["sources"] and body["meta"]["returned"] == 1
    assert body["error"] is None


def test_discovery_tool(fake_storage, monkeypatch):
    _setup(fake_storage, monkeypatch)
    response = _invoke(
        "tools/call",
        {"name": "get-user-knowledge-bases", "arguments": {}},
        request_id=3,
    )
    discovery = json.loads(response["result"]["content"][0]["text"])
    assert discovery["knowledgeBases"][0]["name"] == "kmcp-kb"
    assert {t["name"] for t in discovery["knowledgeBases"][0]["tags"]} == {"Resume"}

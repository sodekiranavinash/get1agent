# Retrieval Sources & Citations

Design reference for the retrieval (query) path: how a search result cites the
document and page it came from, and how the UI opens the original file without
ever exposing an S3 URL.

Status: **design — not implemented.** Page capture (the prerequisite) is
implemented; see "What ships now".
Last updated: 2026-09-13.

---

## 1. Goal

When a user asks a question and retrieval returns matching chunks, each source
must show:

- which **document** it came from (filename),
- which **page(s)** of that document (e.g. "report.pdf · p. 7"),
- a **snippet** of the matched text,
- a **link to open the source** — the original PDF at that page.

The link must resolve through **our API only**. The browser must never receive
an `s3.amazonaws.com` / presigned URL, in a response body, a redirect, or the
network tab.

---

## 2. What ships now (page capture)

Retrieval is not built yet, but the data it needs is now captured at ingestion.

### Text chunks

- `extractors._extract_pdf` returns per-page text (`Extraction.page_texts`) in
  addition to the joined text.
- `chunking.chunk_pages(pages, chunk_size, overlap)` chunks the page text and
  tags every chunk with a 1-based source page range:
  - `page` — page containing the chunk's first character,
  - `page_end` — page containing its last character (equals `page` when the
    chunk does not cross a page boundary).
- Non-paginated formats (DOCX/XLSX/CSV/TXT/MD) keep `page = page_end = NULL`.
- `chunks.json` is now `{"chunks": [{"text", "page", "pageEnd"}, ...]}`. The
  embed and index stages accept both this shape and the old bare-string shape
  so an in-flight execution from before the deploy still completes.

### Image chunks

Already captured end-to-end — no change needed:
`ExtractedImage.page` → `document_images.page` (1-based, PDF only; `NULL` for
DOCX/embedded images with no page).

### Schema

Migration `0005_chunk_pages` adds `chunks.page` and `chunks.page_end`
(`integer`, nullable). `document_images.page` already existed (migration
`0003_ingestion`).

### Re-ingestion

Page columns are `NULL` for documents indexed before this change. Existing
documents only get page citations after they are **re-ingested** (re-upload or
a re-index job). Retrieval must treat `page IS NULL` as "no page citation"
rather than failing.

---

## 3. Source payload (proposed)

`POST /v1/knowledge-bases/{kbId}/query` (or `/v1/query`) returns, per hit:

```json
{
  "chunkId": 12345,
  "documentId": "uuid",
  "knowledgeBaseId": "uuid",
  "fileName": "report.pdf",
  "contentType": "application/pdf",
  "page": 7,
  "pageEnd": 7,
  "snippet": "…matched text…",
  "score": 0.83,
  "sourceUrl": "/v1/knowledge-bases/{kbId}/documents/{docId}/file#page=7"
}
```

- `sourceUrl` is **relative** and points at our API, never at S3. The frontend
  prefixes it with `VITE_API_URL`.
- The `#page=N` fragment is applied client-side; the PDF viewer (browser native
  or `react-pdf`) jumps to that page. For images, the URL points at the image
  object (`.../file?asset=image-3`), no fragment.
- `page`/`pageEnd` are `null` for non-paginated sources.

### Grouping

Multiple chunks often map to the same document+page. The API should group hits
by `(documentId, page)` and keep the best score, returning the chunk list under
each group so the UI shows one citation per page rather than duplicates.

---

## 4. Retrieval flow (proposed)

```sql
-- 1. vector search over text chunks (HNSW cosine index already exists)
SELECT c.id, c.document_id, c.page, c.page_end, c.content,
       1 - (c.embedding <=> :query_vector) AS score
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE c.knowledge_base_id = :kb
  AND d.status = 'ready'          -- never cite a partial document
ORDER BY c.embedding <=> :query_vector
LIMIT :k;

-- 2. optionally, the same over document_images for image hits
```

- The query vector is produced with the **same model/dimension** the KB was
  indexed with (`knowledge_bases.embed_model`, `embedding_dim`). Reject queries
  against a KB whose model differs from the query model.
- Only `documents.status = 'ready'` rows are eligible.
- The `chunks` → `documents` join supplies `file_name`, `content_type`,
  `s3_key` (server-side only).
- This is a **read path**; never match by vector similarity on the write path
  (see `ingestion-logic.md` §3).

---

## 5. Download endpoint (no S3 URL, ever)

New route:

```
GET /v1/knowledge-bases/{kbId}/documents/{docId}/file
```

Behavior:

1. Resolve the JWT subject and assert the document belongs to the caller
   (`documents.user_id`) and to `{kbId}`. Return `404` (not `403`) on mismatch
   so document ids are not enumerable.
2. Fetch the object from S3 **server-side** and stream it back through the API.
3. Respond with:
   - `Content-Type` = `documents.content_type`
   - `Content-Disposition: inline; filename="report.pdf"` (inline so the PDF
     renders in the viewer; use `attachment` for a "Download" button)
   - `Accept-Ranges: bytes` and honor `Range` requests so the PDF viewer can
     seek without re-downloading the whole file.
4. The response body is the file bytes. **No redirect, no presigned URL, no
   S3 hostname.**

### Why not presign-and-redirect

A `302` to a presigned URL puts the S3 URL in the browser and in any proxy
logs, and the user explicitly rejected exposing S3 URLs. All bytes flow through
our endpoint.

### Delivery mechanism

| Option | Fit |
|---|---|
| API Gateway HTTP API + Lambda (binary) | Simple; hard **10 MB** response cap |
| Lambda **response streaming** via Function URL | Streams large files; needs its own auth/authorizer |
| CloudFront + signed cookies → S3 via OAC | Scales, keeps S3 private; more infra |

Recommended: start with a `documents-download` Lambda behind API Gateway
(covering typical PDFs) and move to Lambda response streaming if files >10 MB
are expected. Keep the object in the **private** bucket; only the Lambda's
execution role may `s3:GetObject`. If the Lambda runs in the VPC it reaches S3
through the free gateway endpoint.

Alternative for the object bytes: the Lambda may presign internally and
`urllib`-fetch it server-side — but a direct `GetObject` with the execution
role is simpler and keeps credentials out of the URL entirely.

---

## 6. Frontend rendering

- Sources panel under the answer: one card per `(document, page)` group.
  - Title: `fileName`
  - Subtitle: `Page {page}` when present
  - Snippet with the matched span emphasized
  - Primary action opens `sourceUrl` in a new tab / side drawer.
- The PDF viewer appends `#page=N`; the browser handles the jump. If a custom
  viewer is used, pass `page` as a prop instead.
- Never render `documents.s3_key`, and do not add `downloadUrl` to any
  response. The existing `downloadUrl` field in the KB detail payload
  (`user-api/user_api/handler.py:_presign_get`) is unused by the UI and
  should be **removed** as part of this work — it is exactly the leak we are
  avoiding.

---

## 7. Open questions

- Query endpoint shape: `POST /v1/knowledge-bases/{id}/query` vs a global
  `/v1/query` with a `knowledgeBaseIds` filter.
- Hybrid search (vector + Postgres full-text) and reranking?
- How many chunks per page group to return, and how to trim the snippet around
  the match?
- Image sources: show the extracted image inline, or link to the PDF page?
- Files >10 MB: adopt Lambda response streaming now or defer?
- Re-index/backfill job to populate `page` on already-ingested documents.

---

## 8. References

- Ingestion rationale: `design/ingestion-logic.md`.
- Pipeline stages: each `backend/services/ingestion-*` Lambda (`handler.py` + `src/`).
- Page-aware chunker: `backend/packages/ingestion/chunking.py`.
- Page extraction: `backend/packages/ingestion/extractors.py`.
- Embedding config/clients: `backend/packages/retrieval/embedding/`.
- Schema: `backend/migrations/versions/0003_ingestion.py`,
  `backend/migrations/versions/0005_chunk_pages.py`.

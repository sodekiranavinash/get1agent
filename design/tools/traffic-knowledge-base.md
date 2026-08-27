# LLD — `traffic-knowledge-base`

Low-level design for the second MCP tool: retrieve **Motor Vehicles Act / state rules / dispute procedure** context for the **traffic challan advisor** (`trafficrules` runtime) via AgentCore MCP Gateway.

Documents live in a **normal S3 bucket**. Child-chunk embeddings live in **Amazon S3 Vectors**. A **tiny lexical index** (BM25) lives next to them in the same bucket. Parents (legal **sections**, not PDF pages) live as JSON objects. The chat Lambda **does not** chunk or parse PDFs. Hybrid is **in-process BM25 + vectors**, not OpenSearch. Speed is a requirement: lexical and vector search run **in parallel**; section-number queries **skip Bedrock embed**.

Code and `mcp.json` live in `tools/traffic-knowledge-base/`. Terraform lives in `infra/terraform/`. This folder is a sibling of `tools/challan-extractor/`.

**Architecture exception (intentional):** overall-architecture §7 defaults to Bedrock Knowledge Bases. This tool needs **section-shaped parents** (small-to-big retrieval) that KB hierarchical chunking does not guarantee (KB parents are token windows, not “Section 177”). Do **not** also stand up a Bedrock KB for the same corpus in v1.

---

## 1. Why this shape

| Need | Decision |
| --- | --- |
| Cheap idle | S3 + S3 Vectors + BM25 JSON in S3 (no OpenSearch) |
| Precise search | Embed **child** chunks only (~150–400 tokens) |
| Keyword / section numbers | In-Lambda BM25 over a cached inverted index |
| Hybrid | Reciprocal rank fusion (RRF) of the two lists |
| Usable context | Return **section parents**, not the child, not a PDF page, not the whole file |
| Fast | Parallel BM25 ∥ `QueryVectors`; skip embed when the query is only section ids; keep lexical file small and in memory |

S3 Vector search does **not** read PDFs. The PDF is source-of-truth for ingest; the query path never `GetObject`s the raw Act unless a citation URL is enough.

---

## 2. Two jobs (do not mix)

```
Ingest (batch, rare)                         Retrieve (chat hot path — keep short)
──────────────                               ────────────────────────────────────
PDF/HTML → text → sections                   MCP query
  → child chunks                               → rewrite / detect section-only
  → Bedrock embeddings                         → FAST: BM25 only (no embed) if section-only
  → PutVectors (children)                      → ELSE: embed, then BM25 ∥ QueryVectors
  → PutObject parents/*.json                   → RRF → unique section_id
  → PutObject index/lexical.json               → parallel GetObject parents
                                               → bounded MCP JSON
```

| Job | Runtime | When |
| --- | --- | --- |
| Ingest | Go CLI `cmd/ingest` and/or Lambda `traffic-knowledge-base-ingest` | Manual / CI / S3 `ObjectCreated` on `raw/` |
| Retrieve | Lambda `traffic-knowledge-base` (MCP) | Every agent tool call |

The retrieve Lambda **must not** download PDFs, call Textract, or re-embed the corpus.

---

## 3. Why Go

Same as `challan-extractor`: agent hot path, bounded JSON, AWS SDK, no fat runtime.

| Criterion | Go (`provided.al2023`, arm64) |
| --- | --- |
| Cold start | ~10–50 ms |
| Concurrent parent `GetObject` | goroutines |
| Deploy | static `bootstrap` zip |

**Retrieve Lambda:** memory **512 MB** (CPU scales with memory; faster JSON + BM25), timeout **10 s**, no VPC.  
**Ingest Lambda (if used):** memory **1024 MB**, timeout **5 min**. Prefer CLI ingest in v1 if PDFs are few.

No Bleve, SQLite, or CGO — they inflate the zip and cold start. Lexical search is a **hand-sized inverted index** in memory.

**Decision: Go 1.22+, `provided.al2023`, `arm64`.**

---

## 4. Object model (small-to-big)

Legal meaning lives in **sections / rules / FAQ answers**, not PDF page breaks.

```
document_id          e.g. in-mva-1988
  └── section_id     e.g. in-mva-1988#s-177          ← parent (returned to the model)
        └── chunk_id e.g. in-mva-1988#s-177#c-02     ← embedded, searched
```

| Id | Format | Example |
| --- | --- | --- |
| `document_id` | `[a-z0-9-]{3,64}` | `in-mva-1988`, `ts-cmvr`, `in-dispute-parivahan` |
| `section_id` | `{document_id}#s-{slug}` | `in-mva-1988#s-177`, `in-mva-1988#s-177a` |
| `chunk_id` | `{section_id}#c-{nn}` | zero-padded index inside the section |

**Parent = one section** (or one FAQ item). Not a PDF page. Not the whole file.

For unstructured dispute HTML with no section numbers, parent = one heading block; children = sentences or ~200-token slices of that block.

---

## 5. S3 layout (docs bucket ≠ sessions bucket)

Bucket: `{env}-traffic-kb-docs` (private, SSE-S3 or KMS, block public access). **Never** the `S3SessionManager` conversations bucket.

```
s3://{KB_DOCS_BUCKET}/
  raw/{document_id}/{filename}              # source PDF or HTML (ingest only)
  raw/{document_id}/source.json             # provenance: url, retrievedAt, licence note
  parents/{document_id}/{section_slug}.json # generation payload
  manifest/{document_id}.json               # section list, ingest version, embedding model
  index/lexical.json                        # inverted index + chunk stats (BM25); keep < 8 MiB
  index/version                             # etag/version string; retrieve skips reload if same
```

Parent object (`parents/in-mva-1988/177.json` — key may use slug `177` while `section_id` in JSON is full):

```json
{
  "section_id": "in-mva-1988#s-177",
  "document_id": "in-mva-1988",
  "title": "General provision for punishment of offences",
  "heading": "177",
  "text": "…full section text including provisos…",
  "jurisdiction": "IN",
  "doc_type": "central_act",
  "year": 1988,
  "source_uri": "s3://…/raw/in-mva-1988/mva-1988.pdf",
  "citation": "Motor Vehicles Act, 1988, s.177",
  "chunk_ids": ["in-mva-1988#s-177#c-00", "in-mva-1988#s-177#c-01"]
}
```

`text` must be the full parent. Cap parent `text` at **8000 UTF-8 bytes**; if a section is longer, split into `s-177#p1`, `s-177#p2` as separate parents (still not “a PDF page”).

---

## 6. S3 Vectors (children only)

- Vector **bucket** + **index** dedicated to `corpus=trafficrules`.
- Dimension = embedding model (Titan Text Embeddings V2: **1024**).
- Distance: **cosine**.
- **Embed children only.** Do not `PutVectors` for parents or whole documents.

Filterable metadata (keep well under **2 KB**):

| Key | Type | Example |
| --- | --- | --- |
| `corpus` | string | `trafficrules` |
| `document_id` | string | `in-mva-1988` |
| `section_id` | string | `in-mva-1988#s-177` |
| `jurisdiction` | string | `IN`, `TS`, `KA`, `MH`, `DL` |
| `doc_type` | string | `central_act`, `central_rules`, `state_rules`, `dispute` |
| `year` | number | `1988` |

Non-filterable (optional, small): `chunk_text` **only if** ≤ remaining metadata budget. Prefer **not** storing full child text on the vector; retrieve path uses `section_id` → parent JSON. If child text is stored, declare that key **non-filterable** at index create.

Vector key = `chunk_id`.

On re-ingest of a document: `List`/`Delete` all vectors with `document_id` equals that id, then put the new children (or delete-by-prefix convention: keys start with `{document_id}#`).

---

## 7. Embeddings

| Knob | v1 |
| --- | --- |
| Model | Bedrock **Titan Text Embeddings V2** (`amazon.titan-embed-text-v2:0`) |
| Region | same as Lambdas (`us-east-1`) |
| Normalize | yes (Titan v2 default) |
| Query vs document | **same model**, no instruct prefix unless we later switch models |

Ingest embeds each child. Retrieve embeds only on the **semantic path** (§9). Section-only queries skip embed.

---

## 8. Ingest (batch)

### 8.1 Child / parent split

1. Extract text from `raw/` (PDF: `ledongthuc/pdf` or pre-extracted `.txt` next to the PDF if layout is hostile). Prefer **official born-digital PDFs**; scanned gazettes may need Textract in a later phase (out of v1).
2. Split on legal headings: `Section N`, `Sec. N`, `Rule N`, numbered FAQ titles. Fail closed: if no headings found, fall back to ~1200-token windows as parents (log `split=window`).
3. Parent = one heading block.
4. Children: pack ~200–350 tokens with **40-token overlap** inside the parent. Do not split mid-sentence when possible.
5. Write parent JSON; `PutVectors` for children; write `manifest/`.
6. Rebuild **`index/lexical.json`** for the whole corpus (or incrementally merge). Must finish in the same ingest as vectors so search never sees split-brain.

### 8.2 v1 corpus (download yourself, store in `raw/`)

| `document_id` | What | Typical source |
| --- | --- | --- |
| `in-mva-1988` | Motor Vehicles Act, 1988 + amendments | India Code / Gazette PDF |
| `in-cmvr-1989` | Central Motor Vehicles Rules | MoRTH / India Code |
| `ts-state-rules` | Telangana (first state) | State transport / gazette |
| `in-dispute-echallan` | How to dispute / compound e-challan | Parivahan / official FAQ PDF or HTML saved to S3 |

Add more states as extra `document_id`s with `jurisdiction` set. Do **not** scrape government sites on the retrieve path.

Provenance `source.json` records the URL and date. We store a copy; we do not claim we are the publisher.

### 8.3 Lexical index (`index/lexical.json`)

Built at ingest from **child text** (same units as vectors). Cap **8 MiB** uncompressed; gzip on S3 is fine if retrieve gunzips once into memory.

Shape (illustrative):

```json
{
  "version": "2026-08-27T00:00:00Z",
  "avgdl": 220.4,
  "k1": 1.2,
  "b": 0.75,
  "N": 1840,
  "chunks": {
    "in-mva-1988#s-177#c-00": {
      "dl": 198,
      "section_id": "in-mva-1988#s-177",
      "jurisdiction": "IN",
      "doc_type": "central_act"
    }
  },
  "postings": {
    "177": { "in-mva-1988#s-177#c-00": 2 },
    "compound": { "in-mva-1988#s-200#c-01": 1 }
  }
}
```

Tokenize: lowercase, unicode letters/digits, keep tokens like `177a`. Do **not** stem aggressively (legal “compounding” vs “compound” can differ; light suffix strip is optional). Store **df** implicitly via posting list length.

**Not** Bleve / SQLite / OpenSearch. Must stay small so a cold Lambda can `GetObject` + JSON-decode in tens of milliseconds.

---

## 9. Retrieve Lambda — runtime shape (speed-first)

```
MCP Gateway  ──invoke──►  Lambda  traffic-knowledge-base
                                │
                                ├─ unwrap + validate
                                ├─ ensureLexical(): memory hit OR GetObject index/ (once per container)
                                ├─ rewrite; classify path = section_only | hybrid
                                │
                                ├─ section_only (fast): BM25 / heading lookup only — no Bedrock
                                │
                                └─ hybrid:
                                      goroutine A: Bedrock embed → QueryVectors
                                      goroutine B: BM25 on in-memory index
                                      wait both (fail-soft: one side empty is OK)
                                      RRF merge
                                │
                                ├─ unique section_id, cap max_parents
                                ├─ parallel GetObject parents (4 workers)
                                └─ JSON
```

**Latency budget (warm, us-east-1, target p50; extra RTT if you call from India):**

| Step | Budget |
| --- | --- |
| Lexical already in memory | ~0 |
| Section-only BM25 + 1–4 parent GETs | **&lt; 150 ms** |
| Hybrid: embed + max(vectors, BM25) + parents | **&lt; 500 ms** p50; BM25 must stay **&lt; 15 ms** |
| Cold: first `GetObject` lexical.json | extra **&lt; 200 ms** if file &lt; 8 MiB |

Wall clock for hybrid is `embed + max(QueryVectors, BM25) + RRF + parent GET`, **not** the sum of BM25 and vectors.

### 9.1 Section-only fast path (required)

Skip Bedrock when the query is only section/rule identifiers after trim:

- `177`, `s.177`, `sec 177A`, `section 177 and 179`
- Min query length **2** (so `177` is valid)

BM25 (and an exact `heading` / `section_id` suffix match) only. If BM25 returns nothing, **then** fall back to hybrid (embed + vectors) — one slow retry, not the default.

### 9.2 Hybrid merge

- `k_rrf = 60`
- `score(id) = Σ 1/(60 + rank_list)` over lists that contain the chunk (`rank` is 1-based)
- Each list contributes at most `top_k_chunks` hits
- Apply the same `jurisdiction` / `doc_type` filter **in BM25** as in `QueryVectors` (post-filter on chunk metadata in `lexical.json`)
- Parent `score` in the MCP response = merged RRF of its children (not raw cosine)

If S3 Vectors errors and BM25 has hits → still `ok: true` with lexical-only sections. If BM25 index missing/corrupt and vectors work → vectors-only. If both fail → `search_failed`.

### 9.3 Keep it fast (do / don’t)

| Do | Don’t |
| --- | --- |
| Cache lexical index in a process global; reload only if `index/version` changed (HEAD/ETag) | Download `lexical.json` every invoke |
| `QueryVectors` and BM25 in parallel | BM25 after vectors |
| 512 MB memory | 128 MB (starves CPU) |
| `max_parents` default **4** | Returning 8 full sections |
| Gzip lexical on S3, decode once | Bleve index in the zip |
| Optional: provisioned concurrency = 1 if cold starts show up in LangSmith | OpenSearch “for speed” |

---

## 10. Input contract

Same JSON from test console, MCP `arguments`, or wrapped envelope.

```json
{
  "query": "How can I dispute a Telangana e-challan under section 177?",
  "jurisdiction": "TS",
  "doc_type": null,
  "top_k_chunks": 12,
  "max_parents": 4
}
```

Also accepted: `{ "arguments": { "query": "…" } }`.

| Field | Rules |
| --- | --- |
| `query` | required, string, trim, **2–2000** chars (`177` is valid) |
| `jurisdiction` | optional. `IN` \| ISO-like state codes we ingest (`TS`, `KA`, `MH`, `DL`, …). Unknown → `invalid_input` |
| `doc_type` | optional. one of `central_act`, `central_rules`, `state_rules`, `dispute` |
| `top_k_chunks` | optional int **1–30**, default **12** |
| `max_parents` | optional int **1–8**, default **4** |

When `jurisdiction` is a state (not `IN`), filter is:

`corpus = trafficrules` AND (`jurisdiction` equals that state **OR** `jurisdiction` equals `IN`)

Central Act always applies; state rules are extra. When `jurisdiction` omitted, filter `corpus` only (agent should pass state when the challan has one).

### 10.1 Query rewrite (deterministic, no extra LLM)

Before embed:

1. Keep the user `query` as `query_raw`.
2. Extract tokens matching `(?i)\b(?:section|sec\.?|s\.?)\s*(\d+[A-Za-z]?)\b` and bare `\b(\d{2,3}[A-Za-z]?)\b` near “MVA” / “MV Act”.
3. `query_embed` = `query_raw` plus, if any, `" section " + joined numbers` (avoid exploding with every number in the challan).
4. If the remainder after stripping those identifiers is empty (or only “and” / commas), set `path=section_only`.

Rewrite feeds BM25 tokens and, on the hybrid path, the embedding. Return `query_raw` in the response. Add `"path": "section_only" | "hybrid"` on the success JSON for debugging (agent can ignore it).

---

## 11. Output contract

Success: Lambda 200, `ok: true`.

```json
{
  "ok": true,
  "query": "How can I dispute a Telangana e-challan under section 177?",
  "path": "hybrid",
  "sections": [
    {
      "section_id": "in-mva-1988#s-177",
      "document_id": "in-mva-1988",
      "citation": "Motor Vehicles Act, 1988, s.177",
      "title": "General provision for punishment of offences",
      "jurisdiction": "IN",
      "doc_type": "central_act",
      "score": 0.82,
      "matched_chunk_ids": ["in-mva-1988#s-177#c-00"],
      "text": "…"
    }
  ]
}
```

| Rule | Value |
| --- | --- |
| Order | descending `score` (RRF of that parent’s child hits; section-only = BM25/RRF from one list) |
| Dedupe | one object per `section_id` |
| Cap | `max_parents` |
| Empty | `ok: true`, `sections: []` (not an error) |
| Size | total JSON **≤ 96 KiB**; if over, drop lowest-score parents then truncate `text` of the last one with `"…"` |

Do not return raw embeddings, PDFs, or other parents’ full `chunk_ids` lists beyond `matched_chunk_ids`.

### 11.1 Errors

Function succeeds with `ok: false` for validation. Lambda error only on panic.

| `error.code` | When |
| --- | --- |
| `invalid_input` | missing/short query, bad enum, bad ranges |
| `embed_failed` | Hybrid path needed embed, Bedrock failed, and BM25 had **no** hits |
| `search_failed` | Vectors **and** BM25 both failed or both empty after a vectors/index error |
| `parent_fetch_failed` | **all** parent GetObject failed (if some succeed, omit failed ids and still `ok: true`) |

```json
{ "ok": false, "error": { "code": "invalid_input", "message": "query is required" }, "sections": [] }
```

Do not log full parent `text`. Log `query` truncated to 80 chars.

---

## 12. AWS calls + retry (retrieve)

| Call | Timeout | Retry |
| --- | --- | --- |
| Lexical `GetObject` | 3 s | 1 retry; then BM25 off for this container until next success |
| Bedrock embed | 6 s | 2 extra on 429/5xx, 80 ms × 2^n jitter; **skip entirely** on `section_only` |
| `QueryVectors` | 6 s | same; on failure continue with BM25 |
| Parent `GetObject` | 3 s each, **4** workers | 1 retry on 5xx |

Retrieve Lambda timeout **10 s**. BM25 has no network timeout (in-memory).

---

## 13. Package layout

```
tools/traffic-knowledge-base/
  cmd/bootstrap/main.go     # retrieve Lambda
  cmd/ingest/main.go        # CLI: -document-id -bucket …
  cmd/local/main.go         # go run retrieve against event.json
  internal/handler/         # unwrap, status JSON
  internal/embed/           # Bedrock Titan v2
  internal/search/          # S3 Vectors QueryVectors
  internal/lexical/         # load + BM25
  internal/rrf/             # merge ranks
  internal/parent/          # GetObject + decode
  internal/rewrite/         # section-number rewrite + section_only
  internal/ingest/          # split + put + lexical.json (used by cmd/ingest)
  testdata/                 # sample parent JSON, fake query
  event.json
  event-mcp.json
  mcp.json
  Makefile
  go.mod
```

Package retrieve like challan-extractor: `GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -tags lambda.norpc -o bootstrap ./cmd/bootstrap`.

Register in `tools/registry.json`.

---

## 14. IAM

Retrieve role:

- `bedrock:InvokeModel` on the Titan embed model ARN only
- `s3vectors:QueryVectors` (and `GetIndex` if required) on the traffic index ARN
- `s3:GetObject` on `parents/*`, `index/*`, and `manifest/*` only (not `raw/` on the chat role)

Ingest role (CLI user or ingest Lambda):

- `s3:GetObject` / `PutObject` / `ListBucket` on `raw/`, `parents/`, `manifest/`, `index/`
- `bedrock:InvokeModel` embed
- `s3vectors:PutVectors`, `DeleteVectors`, `QueryVectors` / list as needed

No DynamoDB. No OpenSearch in v1.

---

## 15. Terraform

- Reuse `modules/lambda_tool` for retrieve (and ingest Lambda if added).
- New module or env resources: docs bucket, S3 Vector bucket + index (dimension 1024, cosine, non-filterable keys reserved if we store `chunk_text`).
- Env: `KB_DOCS_BUCKET`, `S3_VECTOR_BUCKET`, `S3_VECTOR_INDEX`, `EMBED_MODEL_ID`, `AWS_REGION`, `LEXICAL_KEY` (default `index/lexical.json`).
- CloudWatch log group **7 days**.
- Function name pattern: `get1agent-{env}-traffic-knowledge-base`.
- Terraform ignores zip hash; tools workflow updates code (same as challan-extractor).

---

## 16. MCP

Tool name: **`traffic-knowledge-base`**.

Description (for the model): search ingested Indian traffic law and dispute guides. Pass `jurisdiction` from the challan when known. Use for “what the Act says” and “how to dispute”, not for live challan fetch (`challan-extractor`).

Input schema: `query` required; `jurisdiction`, `doc_type`, `top_k_chunks`, `max_parents` optional as in §10.

Attach only to `trafficrules`.

---

## 17. Tests (required)

| Test | Asserts |
| --- | --- |
| Rewrite | “section 177” and `177` → `section_only`; long prose stays `hybrid` |
| BM25 | token `177` ranks `s-177` children above unrelated chunks |
| RRF | chunk rank 1 on both lists outranks rank 1 on one list |
| Parallel contract | handler does not call embed before starting BM25 (unit: fake clocks / call order) |
| Filter | state `TS` → filter OR `IN`; unknown code → `invalid_input` |
| Dedupe | two chunks same `section_id` → one parent |
| Cap | 6 unique sections, `max_parents=4` → 4 |
| Fail-soft | vectors error + BM25 hits → `ok: true` |
| Parent miss | one GetObject 404 → remaining sections still returned |
| Handler unwrap | top-level and `arguments.query` |
| Empty hits | `ok: true`, `sections: []` |
| Ingest split | fixture Act fragment → parent `s-177` + lexical posting for `177` |

No live Bedrock / S3 Vectors in CI (interfaces faked). Optional `make invoke` for a deployed index.

---

## 18. Observability

Log: `durationMs`, `path` (`section_only`\|`hybrid`), `embedMs`, `vectorMs`, `bm25Ms`, `parentMs`, `lexicalCache` (hit/miss), `chunkHits`, `parentCount`, `jurisdiction`, `ok`, truncated query. CloudWatch 7 days. No full section text in logs. Alert if `embedMs` runs on `section_only`.

---

## 19. Out of scope (v1)

- OpenSearch / Elastic / Pinecone (hybrid is in-process BM25)
- Bedrock Knowledge Base for this corpus
- Bleve / SQLite FTS in the retrieve zip
- OCR / Textract for scanned gazettes
- Returning whole PDF pages or whole documents
- Cross-agent corpora (`companyInfo`)
- MCP Gateway wiring (same later step as challan-extractor)
- Mutating law; this is retrieval only

---

## 20. How it works with `challan-extractor`

1. Agent calls **`challan-extractor`** → structured offences (`Sec. 177`, state, vehicle).
2. Agent calls **`traffic-knowledge-base`** with that section + `jurisdiction`.
3. Model advises using **section text + citation**, not unsourced memory.

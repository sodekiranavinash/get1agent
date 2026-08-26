# LLD — `challan-extractor`

Low-level design for the first MCP tool Lambda: fetch a Parivahan eChallan **print-page** URL, parse the HTML, and return a compact JSON document for the **traffic challan advisor** agent (`trafficrules` runtime) via AgentCore MCP Gateway later.

This document is the implementation contract. Code and `mcp.json` live in `tools/challan-extractor/`. Terraform lives in `infra/terraform/`. The next tool is another sibling under `tools/`, not nested under `lambda/`.

---

## 1. Why Go

Architecture §6 language table:

| Use | Language |
| --- | --- |
| Light HTTP / JSON transforms | Node.js |
| CPU-heavy parsing, concurrency | **Go** |

This tool is a **GET + HTML walk + JSON out**, with **retries**, and it must be **fast** on the agent hot path.

| Criterion | Go (`provided.al2023`, arm64) | Node 20 | Python 3.12 |
| --- | --- | --- | --- |
| Cold start | ~10–50 ms | ~200–400 ms | ~300–800 ms + deps |
| HTML parse | `net/html` / goquery, low alloc | cheerio, GC pauses | BeautifulSoup, slower |
| Retry / timeout | first-class `context` + `http.Client` | good | good |
| Deploy size | single static binary | `node_modules` | layers / zip |
| MCP later | same handler JSON in/out | same | same |

**Decision: Go 1.22+, `provided.al2023`, architecture `arm64` (Graviton).** No VPC (default internet egress). Memory **256 MB**. Timeout **25 s** so a slow Parivahan GET still fits (per-attempt HTTP timeout 10 s).

Python would be convenient for BeautifulSoup but loses cold-start and parse speed. Node is acceptable for “light HTTP” but this parse is the hot path for LLM context — Go is the fit.

---

## 2. Runtime shape

```
MCP Gateway (later)  ──invoke──►  Lambda  challan-extractor
                                      │
                                      ├─ validate URL (https + host allow-list)
                                      ├─ GET with timeout, 429/5xx retry
                                      ├─ parse HTML → ExtractedChallan
                                      └─ JSON response (bounded)
```

No S3, no DynamoDB, no secrets. Outbound HTTPS only to allow-listed hosts.

**Not in this Lambda:** downloading evidence images as bytes (those URLs are passed to the model / a later vision tool). **Do** return every useful image URL.

---

## 3. Input contract

`urls` array of print-page links (no count cap). Same JSON whether invoked from a test console, a later MCP target, or a wrapped `arguments` object.

```json
{ "urls": ["https://echallan.parivahan.gov.in/report/print-page?challan_no=..."] }
```

Also accepted (Gateway-style):

```json
{ "arguments": { "urls": ["https://echallan.parivahan.gov.in/report/print-page?challan_no=..."] } }
```

Legacy single `url` is still accepted and treated as a one-element list.

### 3.1 URL rules (fail closed)

| Check | Rule |
| --- | --- |
| Scheme | `https` only |
| Host | exact match to allow-list (default `echallan.parivahan.gov.in`) |
| Path | must start with `/report/print-page` |
| Size | URL string ≤ 2048 chars |

Reject `http`, IPs, other hosts, and open redirects. Do **not** follow redirects off the allow-list (client: `CheckRedirect`).

---

## 4. Output contract

Success: HTTP 200 (Lambda function success) with JSON body. Top-level `ok` is `true` when the request was accepted; each URL has its own item (same order as input). Item fields are always present; missing HTML values are `""`, empty arrays, or `null` as noted.

```json
{
  "ok": true,
  "items": [
    {
      "ok": true,
      "sourceUrl": "https://echallan.parivahan.gov.in/report/print-page?challan_no=…",
      "issuingAuthority": "Traffic Police Andhra Pradesh",
      "officeName": "Kakinada",
      "challanDate": "26-04-2026 19:53:06",
      "challanDateIso": "2026-04-26T19:53:06+05:30",
      "vehicleClass": "M-Cycle/Scooter(2WN)",
      "vehicleNo": "AP40HP6758",
      "challanNo": "AP186219260426195306",
      "lgdCode": "746",
      "dlNo": "No DL",
      "placeOfIncident": "Door No 5, 1-41, Main Rd, …",
      "documentImpounded": "No Document Impounded",
      "ownerName": "S**E K***N A*****H",
      "ownerAddress": "5*******2 …",
      "driverName": "S**E K***N A*****H",
      "fatherName": "SO S**E A********U",
      "engineNo": "CK4GS31*****",
      "chassisNo": ".........",
      "violatorContactNo": "*******952",
      "receivedAmountInr": 185,
      "receiptDate": "07-05-2026",
      "remarks": "Not Available",
      "offences": [
        {
          "srNo": 1,
          "offence": "Not producing DL and RC/ with out document. (LMV) Sec. 177",
          "mvAct": "( Sec - 177 )",
          "compoundingFeeInr": 150,
          "offenceType": "Normal Penalty"
        }
      ],
      "officer": {
        "name": "A Satyanarayana_SI Traffic-II",
        "email": "kkd_ps2traffickkd_si2@echallan.appolice.gov.in",
        "rank": "SUB INSPECTOR"
      },
      "images": {
        "evidence": [
          "https://echallan.parivahan.gov.in/www/challans_downloaded_images/….jpeg",
          "https://echallan.parivahan.gov.in/www/challans_downloaded_images/….jpeg"
        ],
        "map": "https://maps.googleapis.com/maps/api/staticmap?…",
        "qr": "https://echallan.parivahan.gov.in/report/qrcode?…",
        "all": ["…every unique http(s) img src…"]
      }
    }
  ]
}
```

`challanDateIso` assumes **Asia/Kolkata** when the print page has no timezone (Parivahan timestamps are IST). If parse fails, `challanDateIso` is `""`.

### 4.1 Images (required for later LLM / vision)

Print HTML mixes logos, placeholders, QR, map, and offence photos.

| Bucket | Rule |
| --- | --- |
| `all` | Unique absolute `http(s)` `img[src]`, order of first appearance |
| `evidence` | Up to **4** photos that look like challan captures (`challans_downloaded_images`, or non-placeholder jpeg/jpg/png). Skip `no_image.png`, `gov.png`, `logo1.png`, `nic_logo.png` |
| `map` | First Google Static Maps / `staticmap` URL, else `""` |
| `qr` | First URL containing `qrcode`, else `""` |

Relative srcs are resolved against the request URL.

### 4.2 Errors

Function **succeeds** with request-level `ok: false` when `urls` is missing. Per-URL failures live on that item (`ok: false` + `error`); other items still return. Function **fails** (Lambda error) only for unexpected panics.

| `error.code` | When |
| --- | --- |
| `invalid_url` | Failed allow-list / scheme / path |
| `fetch_failed` | Network / non-retryable HTTP after retries |
| `parse_failed` | Body not HTML or empty extract of `challanNo` **and** `vehicleNo` |
| `rate_limited` | Still 429 after retries |

Request-level:

```json
{ "ok": false, "error": { "code": "invalid_url", "message": "urls is required" }, "items": [] }
```

Per URL (other items still returned):

```json
{
  "ok": true,
  "items": [
    { "ok": false, "sourceUrl": "https://…", "error": { "code": "invalid_url", "message": "host not allowed" } }
  ]
}
```

Do not include raw HTML in errors. Do not log full query strings (challan tokens).

---

## 5. Fetch + retry (must stay fast)

| Knob | Default | Env |
| --- | --- | --- |
| Per-attempt timeout | 10 s | `HTTP_TIMEOUT_MS` |
| Max attempts | 3 | `HTTP_MAX_ATTEMPTS` |
| Retry on | 429, 502, 503, 504 | — |
| Backoff | 80 ms × 2^(n-1) + 0–40 ms jitter | — |
| `Retry-After` | Honor if ≤ 2 s; otherwise cap at 2 s | — |
| Redirects | Max 3, same allow-list host | — |
| Response cap | 2 MiB | `HTTP_MAX_BODY_BYTES` |

Parivahan print pages often take several seconds. A 1.5 s `http.Client.Timeout` fails while reading the body. Timeouts are applied **per attempt** on the request context. Retry only 429/5xx (not timeouts). Lambda timeout **25 s**. Multiple URLs are fetched by a pool of **4** goroutines (one in-flight GET per worker).

Headers: browser-like `User-Agent`, `Accept: text/html`, `Accept-Language: en-IN`. HTTP/2 disabled (some NIC hosts stall h2).

---

## 6. Parser

Parivahan markup is **invalid HTML** (e.g. `<div>` inside `<table>`). Use `goquery` / `net/html` (tokenization is lenient).

1. Collect all `img[src]` → classify (§4.1).
2. Walk `div[class*=col-xs]` nodes; if text matches a known English label (`Challan Date`, `Vehicle Class`, `Vehicle no`, `Challan no`, `LGD Code`, `DL no`, `Place of incident`, `Owner's Name`, `Owner's Address`, `Driver's name`, `Father's name`, `Engine no`, `Chassis no`, `Violator Contact`), take the next sibling’s `<b>` (or text).
3. `Office Name` / `Traffic Police` from header `<b>` / nearby text.
4. `Document Impounded` from the block after that heading.
5. Offence table: `table.table-bordered` whose header contains `Offences Charged`; each `tbody tr` → 5 cells.
6. Officer: email regex near `Name and signature of Officer`; rank tokens (`SUB INSPECTOR`, `INSPECTOR`, `SI`, `CI`, `HC`).
7. `Received Amount Rs N` and `Remarks:` via regex on flattened text.

Keep extractors **label-based**, not CSS-index-based, so other states’ print pages still work when labels are bilingual.

---

## 7. Package layout

```
tools/
  challan-extractor/           # this tool (next tools are siblings)
    cmd/bootstrap/main.go      # Lambda entry (provided.al2023)
    internal/handler/          # event unwrap, status JSON
    internal/fetch/            # HTTP client + retry
    internal/parse/            # HTML → ExtractedChallan
    testdata/print-page.html   # fixture (no live Google API keys)
    event.json                 # local Lambda payload
    event-mcp.json             # Gateway-style payload
    cmd/local/main.go          # go run ./cmd/local -event event.json
    mcp.json                   # MCP tool name + input schema
    Makefile
    go.mod
infra/terraform/bootstrap/             # S3 bucket for remote Terraform state
infra/terraform/modules/lambda_tool/   # how we deploy *any* tool Lambda (iam.tf, lambda.tf, …)
infra/terraform/envs/dev/              # versions.tf, providers.tf, lambda.tf, outputs.tf
```

Handler uses `lambda.Start` with a typed request. Unit tests: `go test ./...`. Live local invoke (hits Parivahan): `make invoke` (`event.json`). Package: `GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -tags lambda.norpc -o bootstrap ./cmd/bootstrap` then zip `bootstrap`.

---

## 8. Terraform

Reusable module `infra/terraform/modules/lambda_tool`:

- `aws_lambda_function` runtime `provided.al2023`, `architectures = ["arm64"]`, `handler = "bootstrap"`
- `aws_iam_role` + basic execution
- `aws_cloudwatch_log_group` **retention 7 days** (architecture §10)
- Env vars for fetch knobs
- Optional `source_arn` for MCP Gateway invoke permission (empty until Gateway exists)

`infra/terraform/envs/dev` instantiates `name = get1agent-dev-challan-extractor`. Package path: `tools/challan-extractor/dist/function.zip`.

CI split: **Infra** creates the function, IAM, and logs. **Tools — deploy Lambda** (`.github/workflows/tools.yml`) is manual: pass tool name `challan-extractor`, the function name, or `all`. It zips and `UpdateFunctionCode` only when `CodeSha256` differs (same check Terraform would use for `source_code_hash`). Terraform ignores zip hash so infra apply does not overwrite a tools deploy. Register more tools in `tools/registry.json`.

State: S3 backend (`get1agent-terraform-state-ap-south-1`, native `use_lockfile`, no DynamoDB). Create the bucket once via `infra/terraform/bootstrap` (`infra/aws/bootstrap-tf-state.sh`). Pin Terraform 1.15.9 (`.terraform-version`, `required_version >= 1.15.0`) and AWS provider in `versions.tf`.

---

## 9. MCP (later — not wired in this change)

Tool name: **`challan-extractor`**.

- Input schema: `{ "urls": { "type": "array", "items": { "type": "string", "format": "uri" }, "minItems": 1 } }` required.
- Output: `{ "ok": true, "items": [ …per-URL extract… ] }` (Gateway will wrap as tool result).
- Attach only to the traffic challan advisor (`trafficrules`) when Gateway Terraform lands.

---

## 10. Tests (required)

| Test | Asserts |
| --- | --- |
| Parse fixture | Authority, office, date, vehicle, challan no, LGD, DL, place, impounded, 2 offences, officer email/rank, 2 evidence URLs, map + qr present, placeholders not in `evidence` |
| Invalid URL | `invalid_url` for http / wrong host / wrong path |
| Retry | httptest 429 then 200 → one success; 429×3 → `rate_limited` |
| Retry-After | short header is slept (capped) |
| Body cap | oversized body → `fetch_failed` |
| Handler unwrap | top-level `urls` / legacy `url` and nested `arguments.urls` |
| Batch | two URLs → two items in input order; one fetch error does not drop the other |

No live calls to Parivahan in CI.

---

## 11. Observability

Log: `challanNo` if parsed, `durationMs`, `httpAttempts`, `ok`. Never log full `challan_no` query token. CloudWatch 7 days.

---

## 12. Out of scope

- MCP Gateway target registration
- Auth0 / API Gateway in front of this Lambda (Gateway IAM later)
- Fetching image bytes
- Storing HTML
- Paying / mutating challans

# AI Assistant — architecture

AI Assistant is the in-product assistant: a launcher fixed to the **bottom-right of every
page** that opens a dialog, never a page. This document is the technical
reference for how AI Assistant is built and operated. It is deliberately kept **separate
from the platform's other design docs** — AI Assistant is its own subsystem with its own
service, its own runtime, its own data prefixes and its own admin surface, and it
does not appear in the agent-runtime, knowledge or data diagrams.

- Product plan and phasing: [`ai-assistant.md`](./ai-assistant.md)
- Interactive diagrams: `/architecture?tab=ai-assistant` (its own tab, separate from
  Architecture / Agent runtime / Knowledge)
- Admin surface: `/admin/ai-assistant`

---

## 1. Principles

1. **Separate by construction.** AI Assistant's code, image, lockfile, knowledge scope,
   DynamoDB prefixes, traces, feedback and admin page are all its own. Nothing
   AI Assistant writes can appear in the agent chat sidebar, the agent trace list or the
   agent feedback table.
2. **Reuse by import, never by copy.** AI Assistant imports `retrieval.*`, `data.*` and
   `core.*` for retrieval, persistence, caching and rate limiting; on the
   frontend it imports the `ui/` primitives, `ChatAnswer` and `runState` so a
   streamed answer renders with exactly the same components as a chat answer.
3. **Grounded in the repository.** No crawling and no live-UI scraping. The
   corpus is generated from repo sources into committed markdown, validated, then
   ingested through the standard pipeline. A CI drift check keeps it honest.
4. **Measured, not assumed.** Every model choice, limit and prompt is backed by a
   committed evaluation set and per-turn telemetry.
5. **Same contract, two entry points.** Guest and signed-in requests use
   different ingress paths but emit the **same SSE frames**, so the widget and the
   reducers never branch on identity.

---

## 2. System context

```
              ┌──────────────────────── Browser (any page) ─────────────────────────┐
              │  <AiAssistantLauncher/>  fixed bottom-right · opens <AiAssistantDialog/> (not a page) │
              └───────────────┬───────────────────────────────────┬───────────────────┘
                              │ guest                             │ signed in
                              │ POST /v1/ai-assistant/ask                  │ POST /v1/ai-assistant/session
                              ▼                                   ▼
                  ┌───────────────────────┐            ┌───────────────────────────┐
                  │ API Gateway (HTTP)    │            │ API Gateway (HTTP)        │
                  │ NONE auth · IP throttle│            │ Auth0 JWT · route throttle│
                  └───────────┬───────────┘            └─────────────┬─────────────┘
                              ▼                                      ▼
                  ┌───────────────────────┐            ┌───────────────────────────┐
                  │ ai-assistant Lambda      │            │ ai-assistant control plane │
                  │ Function URL          │            │ RunMicrovm + auth token   │
                  │ RESPONSE_STREAM       │            └─────────────┬─────────────┘
                  │ stateless · no tools  │                          ▼
                  └───────────┬───────────┘            ┌───────────────────────────┐
                              │                        │ ai-assistant-agent (Lambda MicroVM)│
                              │                        │ FastAPI · :8080 · SSE     │
                              │                        │ LangGraph Deep Agent      │
                              │                        └─────────────┬─────────────┘
                              └──────────────┬───────────────────────┘
                                             ▼
                        backend/ai-assistant/ai-assistant/  — the shared package
        classifier · retrieval · deep_links · frames · prompts · conversations
        metrics · settings · resolve
                                             │
        ┌────────────────┬───────────────────┼──────────────────┬─────────────────┐
        ▼                ▼                   ▼                  ▼                 ▼
  S3 Vectors       S3 term index        Amazon Bedrock     DynamoDB          S3 objects
  idx-platform     BM25 + catalog       model · judge      AICHAT#          transcripts
  (embeddings)     (lexical leg)        classifier         AIFEEDBACK#      traces
                                                           AITRACE#         corpus
                                                           AIEVAL# · RATE#
```

---

## 3. Components

| Component | Path | Runtime | Responsibility |
|---|---|---|---|
| Widget | `frontend/src/components/ai-assistant/` | browser | Launcher, dialog, transcript, example chips, feedback, route chips |
| Widget client | `frontend/src/lib/ai-assistant.ts` | browser | The only place that branches guest vs signed-in; SSE consumption |
| Shared package | `backend/ai-assistant/ai-assistant/` | imported by both backends | Classifier, retrieval, deep links, prompts, frames, persistence, metrics, settings |
| Agent service | `backend/ai-assistant/main.py` | Lambda MicroVM (ARM64, :8080) | FastAPI: `POST /invocations` (SSE), `GET /ping`, `POST /feedback` |
| Control plane | `backend/services/ai-assistant/control-plane/` | Lambda (Node, API Gateway) | Launches the MicroVM and mints its ingress token |
| MicroVM proxy | `backend/services/ai-assistant/microvm/` | Lambda MicroVM | Verifies the token, forwards SSE (mirrors `agent-run/microvm`) |
| Guest service | `backend/services/ai-assistant/guest/` | Lambda + Function URL (`RESPONSE_STREAM`) | Stateless guest answers |
| Admin API | `backend/services/admin/admin-console/src/ai-assistant.py` | Lambda (admin-console) | `/v1/admin/ai-assistant/*` |
| Corpus tools | `tools/ai-assistant-knowledge/` | CI / developer | Generate, validate, upload, drift-check |
| Infra | `infra/terraform/modules/ai_assistant_runtime/` | Terraform | ECR, MicroVM image, control plane, guest Lambda + URL, routes |

---

## 4. Request flow

### 4.1 Guest

1. The dialog POSTs the **full conversation** plus the entry route to
   `/v1/ai-assistant/ask`.
2. API Gateway applies the route throttle and forwards without authorizing (the
   guest route is deliberately `NONE`).
3. The Lambda hashes the caller IP (`sha256(salt + ip)`) and checks a fixed-window
   counter in DynamoDB (`RATE#ai-assistant` / `W#<window>`), returning `429` with
   `Retry-After` when the cap is hit.
4. The classifier runs. An off-topic or unsafe question returns the nudge plus
   tappable examples — **no retrieval and no answer model call**.
5. On-topic questions run a trimmed Deep Agents loop: **no tools**, retrieval from
   the platform scope only, answer from the retrieved passages.
6. SSE frames stream straight back through the Function URL. **Nothing is
   persisted** — no transcript, no trace, no feedback. Only aggregate metrics are
   emitted.

### 4.2 Signed-in

1. The dialog POSTs `/v1/ai-assistant/session`. The Auth0 JWT authorizer validates at the
   gateway; the control-plane Lambda resolves the verified `sub` to the internal
   `userId` and passes it to the MicroVM when booting it, so identity never comes
   from the browser body.
2. The control plane returns `{ endpoint, token, expiresAt }`; the browser caches
   it and reuses it while it has margin left (the same pattern as agent runs), so
   the measured **2.28 s** cold start is paid once per session, not per message.
3. The browser POSTs the full transcript to the MicroVM's `/invocations`, which
   verifies its own ingress token, resolves the user, and proxies to
   `POST /invocations` on the FastAPI app.
4. The full run executes: classifier → retrieval → tools → answer, streamed.
5. After the answer: the turn is appended to the S3 transcript, the conversation
   metadata item is touched, and one trace object plus a small index item are
   written. All three are best-effort — a persistence failure never costs the
   user an answer.

### 4.3 Turn sequence (both paths)

```
browser ─ POST (full transcript) ─▶ ingress
ingress ─ settings read (30s cache) ─▶ AI Assistant settings item
ingress ─ kill switch / rate limit
ingress ─ run.started ─▶ browser
ingress ─ classifier (rules → model) ─▶ Bedrock
   ├ off_topic ─ ai-assistant.intent + examples ─▶ browser   (turn ends, ~300 ms, no model answer)
   └ platform
        ingress ─ tool.start(search_platform_docs) ─▶ browser
        ingress ─ hybrid search: S3 Vectors ∥ BM25 → RRF → (rerank) → parents
        ingress ─ tool.result + sources[n] ─▶ browser
        ingress ─ text… (streamed tokens) ─▶ browser
ingress ─ run.completed + usage ─▶ browser
ingress ─ trace + transcript + EMF metrics   (signed-in only: persisted)
```

---

## 5. Intent classification

AI Assistant answers **only** platform questions, and the classifier is what enforces it
without paying for a full agent turn on every off-topic message.

| Stage | Cost | What it does |
|---|---|---|
| Rules | ~0 ms, no model | Greetings, obvious arithmetic, code-request verbs, empty/garbage, and platform vocabulary that short-circuits to `platform` |
| Model | ~300 ms | Strict JSON: `kind` (`platform` \| `off_topic` \| `unsafe`), `intent`, `confidence`, `route_hint`, `examples[]`. `temperature=0`, small token cap, few-shot per class |
| Examples | ~0 ms | Off-topic replies ship 3–4 tappable example questions, chosen by the entry route, so a refusal is one tap from recovery |
| Escalation | — | `platform` + `how_to` + a complexity signal swaps in the reasoning model for that turn |

Properties that matter:

- **Fails open.** A classifier timeout or unparseable reply is treated as
  `platform`, so a classifier hiccup can never block a real user.
- **Own model.** `AI_ASSISTANT_CLASSIFIER_MODEL` (default `zai.glm-4.7-flash`), chosen for
  the lowest-variance latency of the invocable models — and it is **not** the
  answer model.
- **Measured.** Precision/recall/F1, fail-open rate and the rules-stage share are
  all tracked, and the committed eval set includes refusal, boundary and
  innocuous-question cases.

---

## 6. Knowledge & ingestion

### 6.1 The reserved platform scope

AI Assistant's knowledge base is **an ordinary knowledge base** owned by a reserved scope:

```
userId  = platform            (no profile, no login, never listed to a user)
KB name = platform-docs       (stable kbId, created once by make ai-assistant-bootstrap)
vectors = idx-platform        (S3 Vectors index named for the scope)
S3      = raw/platform/…, derived/platform/…, index/platform/…
```

Every retrieval call passes that scope instead of a user id, so the existing
hybrid search, reranking, parent hydration, exact cache, semantic cache and
single-flight behaviour apply unchanged. A user's own knowledge bases are
reachable only through `search_my_knowledge`, which is scoped to their own id.

### 6.2 Corpus sources (repository only)

| Source | Produces |
|---|---|
| `frontend/src/content/docs.ts` | One document per documentation section, `route: /docs#<sectionId>` |
| Sidebar + admin navigation registries, `App.tsx` route table | The feature catalogue: the `open_feature` allow-list and the per-page seeds |
| Enforced limit constants (`quotas.py`, `user-api` limits, custom-tool and storage caps, AI Assistant's own defaults) | `platform-limits.md`, generated **from code** so AI Assistant states real numbers and points at the Usage page for per-user overrides |
| `README.md`, `AGENTS.md`, `docs/design/*.md` | Concepts, architecture and operations documents, tagged by audience |
| The AI Assistant design docs | AI Assistant's own answers about itself |

### 6.3 Pipeline

```
tools/ai-assistant-knowledge  ──generate──▶  knowledge/ai-assistant/*.md  ──validate──▶  commit
                                                                        │
                                                              make ai-assistant-knowledge
                                                                        ▼
                                        raw/platform/<kbId>/<docId>/<file>.md  (S3)
                                                                        │
                                        ObjectCreated → EventBridge → SQS → dispatcher
                                                                        ▼
                                     Step Functions: extract ─▶ embed ─▶ index
                                                                        ▼
                                     idx-platform + BM25 terms + parents + manifest
```

- **Chunking** is heading-aware with a prepended breadcrumb
  (`Product docs > Agent builder > Choosing a model`), which is the single
  biggest retrieval win for a question-shaped corpus, and each chunk carries its
  `route` and `title` so a retrieved passage is immediately citable and linkable.
- **Idempotent**: the index stage is delete-then-write per document via the
  manifest, so re-running the build re-indexes cleanly.
- **Drift-checked**: CI regenerates and fails if the committed corpus would
  change, so AI Assistant cannot silently answer from stale documents.

---

## 7. Answer contract

AI Assistant emits the **existing agent-run SSE frames**, so `lib/runState.ts`,
`RunTimeline`, `ChatAnswer` and `SourceCarousel` render an AI Assistant answer without
AI Assistant-specific UI code:

| Frame | Meaning |
|---|---|
| `run.started` | Run id, model, session |
| `ai-assistant.intent` | Classifier verdict (`kind`, `intent`, `examples[]`) — **the only new frame** |
| `plan.started` / `plan` | The harness's plan and todos |
| `text` | Streamed answer tokens (strings or typed content blocks are flattened) |
| `tool.start` / `tool.input` / `tool.result` | Tool activity, translated from LangGraph events |
| `tool.result.sources` | Numbered passages with `route`, `docUrl`, `title` |
| `run.completed` / `run.error` | Terminal frames, with usage |

Streaming is the default on both paths. A non-streaming Lambda fallback exists as
a degraded mode if MicroVM capacity is unavailable.

---

## 8. Data model

All AI Assistant keys are AI Assistant-specific. Nothing here collides with the agent surfaces.

| Entity | pk | sk | GSI |
|---|---|---|---|
| AI Assistant conversation (metadata) | `USER#<userId>` | `AICHAT#<id>` | GSI2 `byUser` |
| AI Assistant conversation transcript | S3 `conversations/<userId>/<id>.json` | — | — |
| AI Assistant feedback | `USER#<userId>` | `AIFEEDBACK#<runId>` | — |
| AI Assistant trace index | `USER#<userId>` | `AITRACE#<traceId>` | GSI2 `byUser`; TTL 90 d |
| AI Assistant trace tree | S3 `traces/<userId>/<traceId>.json` | — | — |
| AI Assistant evaluation run | `USER#<userId>` | `AIEVAL#<runId>` | GSI2 `byUser` |
| Guest rate window | `RATE#ai-assistant` | `W#<window>` | TTL |
| AI Assistant settings (admin) | `PLATFORM#SETTINGS` | `#AI_ASSISTANT` | — |
| Platform knowledge KB | `USER#platform` | `KB#platform-docs` | `byId` |

AI Assistant's feedback item is deliberately richer than the agent one: it carries the
question, an answer preview, the sources used, the classifier's verdict, the
model, the clicked route, latency, tokens and cost — everything the admin
feedback table needs in one item, with no second lookup.

---

## 9. Limits & abuse protection

| Layer | Guest | Signed-in |
|---|---|---|
| API Gateway route throttle | burst 4 / rate 2 | burst 10 / rate 5 |
| Per-caller window (`core.ratelimit`) | per IP hash: 6/hour, 20/day | per user: 120/hour, 1000/day |
| Turn and loop caps | n/a (stateless) | 6 agent steps per turn, 40 turns per conversation |
| Input caps | 2 000 chars per question; 8 turns / 24 000 chars of history | same |
| Persistence | none | transcript, feedback, traces |
| Kill switch | `aviEnabled` hides the launcher and 503s both routes | same |

Beyond the widget's own limits, every model call passes through the platform's
global Bedrock token bucket (`core.ratelimit_bedrock`), so AI Assistant can never starve
the product's own agents. All limits and the model ids are editable at runtime
from `/admin/ai-assistant`.

---

## 10. Observability & evaluation

- **Every turn** emits CloudWatch EMF metrics under `get1agent/ai-assistant`: latency
  (first token and total), classifier and retrieval time, tokens in/out, cost per
  answer, off-topic refusals and classifier fail-opens — split by guest and
  signed-in.
- **Every signed-in turn** writes one observation tree (classifier verdict,
  retrieval candidates and scores, tool calls, prompts and tokens, timings, cost,
  final answer) with a small filterable index item.
- **Feedback** (thumbs, comment, categories) is stored per answer and surfaced in
  the admin table, together with the question and sources that produced it.
- **Evaluations** run the committed AI Assistant question set — answerable, deep-link,
  refusal, boundary, unknown-topic and multi-turn cases — through the platform's
  existing evaluation worker, judged by a model that is never the model under
  test. Metrics: correctness, groundedness, citation precision, retrieval
  `hit@1`/`hit@3`, link validity, classifier precision/recall, hallucination rate
  on unknown topics, and cost per answer.

---

## 11. Admin surface

`/admin/ai-assistant` (backend `admin-console` → `/v1/admin/ai-assistant/*`) exposes:

| Card | Controls |
|---|---|
| Status | Master kill switch, guest toggle, current live config |
| Models | Answer, classifier, escalation and judge model pickers with the measured latency of each; reset to defaults |
| Limits | Guest and signed-in window caps, agent-step cap, input cap — applied at runtime |
| Feedback | The feedback table (question, answer, sources, verdict, model, latency, cost) with filters and export |
| Evaluations | Run the AI Assistant set, run history, per-metric trends, per-case judge reasoning |
| Traces | Latest runs, latency and cost distributions, full trace drill-down |
| Knowledge | Corpus documents, last ingest time, per-document status, re-index trigger |

All routes require the admin role; every mutation records `updatedBy`/
`updatedAt`, and the kill switch is audited.

---

## 12. Deployment

- **Image**: `backend/ai-assistant/` builds an ARM64 container from a frozen lockfile
  (LangChain Deep Agents + LangGraph + `langchain-aws`). It is a container, not a
  Lambda zip, so the dependency size is not a constraint.
- **Infra**: `infra/terraform/modules/ai_assistant_runtime/` creates the ECR repository
  (with the same retention policy as the agent runtime), the MicroVM image, the
  control-plane Lambda, the guest Lambda and its `RESPONSE_STREAM` Function URL,
  and both API Gateway routes.
- **Registry**: `ai-assistant` and `ai-assistant` are registered in
  `backend/registry.json` under the `ai-assistant` group, so the existing deploy script and
  Backend workflow pick them up with no new tooling.
- **Local**: `AI_ASSISTANT_MODE=local` runs the agent on `:8091`; the guest path runs as a
  plain local Lambda handler; `VECTOR_STORE=local` and `EMBED_MODE=ollama` keep
  the whole loop offline.
- **CI**: a new `ai-assistant` group checkbox for Lambda code, a corpus drift check on
  docs/navigation changes, and the AI Assistant evaluation set as a deploy gate.

---

## 13. Why these choices

| Choice | Reason |
|---|---|
| Separate service, not a package inside the agent runtime | Isolates a second framework (LangChain/LangGraph) from Strands, so neither can break the other; the integration surface is only the SSE frames, the DynamoDB keys and the retrieval package |
| Lambda MicroVM for signed-in, plain Lambda for guests | API Gateway HTTP APIs **cannot stream** and cap an integration at 30 s; a guest needs no tools or state, so a streaming Function URL is simpler and cheaper, while a signed-in session benefits from a reused, isolated MicroVM |
| Reserved `platform` scope instead of a new vector store | Reuses hybrid search, rerank, small-to-big hydration, the exact cache, the semantic cache and single-flight — no new retrieval code to maintain |
| Generated, committed corpus instead of a crawler | Deterministic, reviewable in a PR, drift-checked in CI, and no authenticated crawl harness to operate |
| Read-only agent, no shell, no subagents | A support widget must answer in seconds; the harness's planning and context middleware are used, its delegation and filesystem-write middleware are deliberately declined |
| AI Assistant-specific prefixes | Keeps AI Assistant out of the agent chat sidebar, the agent trace list and the agent feedback table, so neither surface gets noisier |

---

## 14. Related documents

| Document | Contents |
|---|---|
| [`ai-assistant.md`](./ai-assistant.md) | Product plan: decisions, phasing, risks, open items |
| [`infra.md`](./infra.md) | Platform infrastructure rules and deploy scripts |
| [`data-access.md`](./data-access.md) | Single-table data-access rules AI Assistant also follows |
| [`frontend.md`](./frontend.md) | UI conventions the widget and admin page follow |
| `/architecture?tab=ai-assistant` | The interactive AI Assistant diagrams (question lifecycle, corpus ingestion, quality loop) |

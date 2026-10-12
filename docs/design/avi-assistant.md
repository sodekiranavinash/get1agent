# Avi — the in-product AI assistant

**Status:** plan for sign-off (no code yet)
**Goal:** a floating **Avi** button at the **bottom-right of every page** (landing
and public pages included) that opens a **dialog, not a page**. Avi streams
answers, explains what the platform can do, deep-links the feature the user is
asking about, and politely redirects non-platform questions. Built on LangChain
**Deep Agents** (deliberately not Strands), grounded in repo knowledge ingested
through the platform's existing pipeline, fully controllable from a new
**admin → Avi** page.

---

## 1. Confirmed decisions

| # | Decision |
|---|---|
| 1 | **Not a chat page** — a bottom-right launcher that opens a dialog box. (One optional maximised view, `/assistant`, only if we want it shareable.) |
| 2 | **Guests can ask questions**, statelessly, on a **separate route** with a hard per-IP cap. **Nothing is stored** for guests. |
| 3 | **Signed-in users get higher limits** (described as "unlimited" in the product, with a generous safety cap) and their transcripts **are** persisted. |
| 4 | **Every request sends the full conversation** from the browser — the server is stateless per request; there is no turn-stitching dependency. |
| 5 | **No crawl, no live-UI scraping.** Knowledge comes **only from the repo**. |
| 6 | **Off-topic questions get a warm nudge + 3–4 tappable example questions.** |
| 7 | **Feedback from signed-in users**, with **new DynamoDB fields/items** (no reuse compromise). |
| 8 | **Full admin page "Avi"** — kill switch, model pickers, limits, guest toggle, feedback, eval dashboard, traces. |
| 9 | **Separate folder structure** for everything Avi, reusing existing components through imports. |
| 10 | **No Strands classifier.** Intent classification is its own component with its own model. |
| 11 | Evaluations, metrics and traces for Avi specifically, "as much as possible". |

### Verified facts this plan rests on

| Check | Result |
|---|---|
| `deepagents` | ✅ `0.7.23`, Python ≥3.11, `langchain-aws` via the `aws` extra; `create_deep_agent` → LangGraph `CompiledStateGraph` with `.astream()` |
| Bedrock streaming | ✅ works — **must pass `disable_streaming=False`**, since `ChatBedrockConverse` silently disables streaming for unverified providers (`glm`, `qwen`) |
| Token frames | ✅ `AIMessageChunk`; content can be a **list of typed blocks**, not a string — the adapter must flatten both |
| MicroVM cold start | ✅ **2.28 s** launch → healthy `/ping` on your deployed image (`RunMicrovm` itself returns in 0.62 s) |
| Default agent FS | ✅ `StateBackend` — files in graph state; no shell unless added |
| API Gateway | ❌ HTTP API (`AWS_PROXY`, `payload_format_version 2.0`) **cannot stream** and caps an integration at 30 s |
| Nova Micro / Lite / Pro | ❌ **not invocable** in your account+`ap-south-1` (only `global.amazon.nova-2-lite-v1:0` works) — they cannot be the classifier |
| Conversation storage | ✅ existing pattern: transcript = one S3 object, metadata = one small DynamoDB item; both best-effort |
| Evals + feedback + EMF metrics | ✅ `data/repositories/evals.py`, `data/repositories/feedback.py`, and `_emit_feedback_metric` (CloudWatch EMF) already exist |

### Model choice — measured, not guessed

Classifier (12-prompt battery, median ms) and answer streaming (4 real platform
questions, TTFT median ms):

| Model | Classifier | Answer TTFT | Correct answers |
|---|---|---|---|
| `nvidia.nemotron-nano-3-30b` | — | **220** | ✅ |
| `zai.glm-4.7-flash` | **304** | **322** | ✅ |
| `qwen.qwen3-next-80b-a3b` | 406 | 378 | ✅ |
| `deepseek.v3.2` | 531 | 463 | ✅ |
| `global.amazon.nova-2-lite-v1:0` | 787 | — | 1M ctx / multimodal |

| Role | Default | Env | Why |
|---|---|---|---|
| **Intent classifier** | `zai.glm-4.7-flash` | `AVI_CLASSIFIER_MODEL` | Lowest-variance latency (230–423 ms), already your `AGENT_PLANNER_MODEL` + `CUSTOM_TOOLS_GENERATOR_MODEL`, reliable JSON. `ministral-3-8b` is no faster (305 ms). |
| **Answer agent** | `nvidia.nemotron-nano-3-30b` | `AVI_MODEL` | Fastest first token by ~100 ms and answered all four questions correctly — the single biggest perceived-speed lever. |
| **Escalation** (only "how do I build X" reasoning questions) | `deepseek.v3.2` | `AVI_REASONING_MODEL` | Cheapest of the strong reasoners; used only when the classifier says `how_to` + reasoning. |
| **Evaluations judge** | `amazon.nova-2-lite-v1:0` | `AVI_JUDGE_MODEL` | Already your `EVAL_JUDGE_MODEL`; 1M context for long rubrics. Never the same model as the one being judged. |

All four are user-selectable on the admin page; `AVI_MODEL` et al. remain the
defaults.

---

## 2. Shape

```
        GUEST (no token)                              SIGNED IN (Auth0 JWT)
              │                                                │
              │  POST /v1/avi/ask                              │  POST /v1/avi/session
              │  (API GW, NONE auth, throttle 2/s)             │  (API GW, JWT, throttle 10/5)
              ▼                                                ▼
   avi-guest Lambda ───────────────────────┐        avi-session control-plane Lambda
   (Function URL, RESPONSE_STREAM)         │        (launches MicroVM, mints token)
   stateless, no tools, no storage         │                    │
              │                            │                    ▼
              │                     shared package        avi-agent (MicroVM :8080)
              │                  backend/avi/avi/*        FastAPI + LangGraph Deep Agent
              │                  classifier · retrieval    tools · subagents-free · persistence
              │                  frames · deep_links                │
              ▼                            ▼                      ▼
        ┌────────────────────────────────────────────────────────────────────┐
        │ platform KB (idx-platform) · Bedrock · S3 conversations · DynamoDB  │
        └────────────────────────────────────────────────────────────────────┘
                                  ▲
                    admin → Avi  (/admin/avi)  ·  evals  ·  EMF metrics  ·  traces
```

**Two ingress paths, on purpose:**

- **Guest** — a plain Lambda with a **Function URL in `RESPONSE_STREAM` mode**, so
  it streams without a MicroVM (no warm-up, no per-user state, no session to
  manage). It answers from the platform KB with **no tools** and **stores
  nothing**. This is what makes guests "smooth and seamless": one POST, tokens
  immediately.
- **Signed-in** — the existing `agent-run` pattern: `/v1/avi/session` mints a
  MicroVM endpoint, the browser streams from it directly. Sessions are reused
  (`autoResumeEnabled`, idle 900 s / suspended 300 s), so Avi's 2.3 s cold start
  is paid once per session, not per message.

The browser uses one reducer for both (`lib/runState.ts`), so the widget code
does not branch on identity — only the URL does.

---

## 3. Folder structure (everything Avi, self-contained)

```
backend/
  avi/                                  ← the agent service (its own image + lockfile)
    main.py                             FastAPI: POST /invocations (SSE), GET /ping, POST /feedback
    avi/                                ← THE SHARED PACKAGE — imported by the guest Lambda too
      classifier.py                     intent classification (its own model, no Strands)
      retrieval.py                      platform-scoped hybrid search (reuses retrieval.*)
      deep_links.py                     feature catalog → validated routes
      frames.py                         LangGraph stream → the SSE contract
      prompts.py                        system prompts + off-topic nudge copy
      agent.py                          create_deep_agent(...) wiring
      model.py                          ChatBedrockConverse(disable_streaming=False)
      resolve.py                        verified JWT sub → userId → profile
      conversations.py                  transcript persistence (S3 + DynamoDB)
      metrics.py                        CloudWatch EMF (latency, tokens, cost, refusals)
      settings.py                       reads admin-controlled config, cached ~60 s
    pyproject.toml  Dockerfile  Makefile  tests/
  services/avi/
    guest/                              ← guest Lambda (imports backend/avi/avi)
      handler.py  Makefile  pyproject.toml  tests/
    control-plane/                      ← avi-session Lambda (Node, mirrors agent-run/index.mjs)
      index.mjs  package.json  Makefile
    microvm/                            ← SSE proxy (copy of agent-run/microvm, retargeted)
      app.mjs  Dockerfile  package.json
  services/admin/admin-console/
    src/avi.py                          ← admin routes: /v1/admin/avi/* (new module, imported by handler.py)
  packages/data/repositories/
    avi.py                              ← AviChat metadata, AviFeedback, AviEvalReport

frontend/src/
  components/avi/                       ← the widget (self-contained)
    AviLauncher.tsx  AviDialog.tsx  AviMessage.tsx  AviComposer.tsx
    AviExampleChips.tsx  AviFeedback.tsx  useAviRun.ts
  lib/avi.ts                            ← one API surface for both paths
  content/aviStarters.ts                ← route-aware example questions
  admin/pages/AdminAviPage.tsx          ← the admin page
  admin/lib/adminAvi.ts                 ← admin API client

tools/avi-knowledge/                    ← generators + validator (make avi-knowledge)
knowledge/avi/                          ← generated, committed markdown (the corpus)
infra/terraform/modules/avi_runtime/    ← ECR + MicroVM image + control plane + guest Lambda/URL
```

Reuse is by **import**, never by copy: `retrieval.*` (hybrid search, s3_vectors,
term_index, layout), `data.repositories.*`, `core.ratelimit`, `core.cache`,
`core.ratelimit_bedrock`, `core.storage`; on the frontend `components/ui/*`,
`components/chat/ChatAnswer.tsx`, `lib/runState.ts`, `lib/support.ts`,
`PageShell`/`PageHeader` for the admin page.

---

## 4. Intent classification (own component, own model)

Runs **before** any answer generation, in both paths, so an off-topic question
costs one cheap call instead of a full agent turn.

```python
# avi/classifier.py
class AviIntent: kind: Literal["platform","off_topic","unsafe"]
                 intent: Literal["explain_feature","find_feature","how_to",
                                 "troubleshoot","limits_billing","smalltalk"]
                 confidence: float; route_hint: str | None; examples: list[str]
```

- **Stage 0 — rules, zero cost** (~1 ms): greetings, obvious arithmetic
  (`^\s*\d+\s*[-+*/]\s*\d+`), code-request verbs (*"write me a python script"*),
  empty/garbage, and platform keywords that short-circuit to `platform`
  (`knowledge base`, `mcp`, `agent builder`, `trace`, `vault`, …). Roughly a
  third of real traffic never reaches a model.
- **Stage 1 — model** (`AVI_CLASSIFIER_MODEL`, `zai.glm-4.7-flash`, ~300 ms):
  strict JSON, `temperature=0`, `maxTokens≈80`, 2 few-shot examples per class.
  Best-effort: on timeout/parse failure it **fails open to `platform`** — never
  block a real user behind a classifier hiccup.
- **Stage 2 — examples**: when `off_topic`, the nudge ships 3–4 example
  questions, chosen by `route_hint` from `aviStarters.ts`. They render as
  **tappable chips**; one tap re-asks that question. That is decision #6.
- **Stage 3 — escalation**: `platform` + `how_to` with a complexity signal
  switches the answer model to `AVI_REASONING_MODEL` for that turn.

Copy (in `prompts.py`, so it is editable without a code change):

> I'm Avi — I'm here for the get1agent platform, so I'm best at questions about
> agents, knowledge bases, workflows, tools and your account. I'm not able to
> help with that one. Try one of these:
> `How do I add a knowledge base?` · `Where do I build an agent?` ·
> `What's the difference between Storage and a knowledge base?` ·
> `How do I see my token usage?`

Never scolding, never "I cannot answer that" — always an invitation plus a way
forward.

---

## 5. What Avi can do (tools — signed-in path only)

| Tool | Purpose |
|---|---|
| `search_platform_docs` | Ground every product statement. Hybrid search over the platform KB; returns passages **with `route` + `docUrl`**, so answers cite and link. |
| `search_my_knowledge` | Only when the user asks about **their own** documents; disabled when they have no ready KB. |
| `open_feature` | *"Where do I do that?"* → a validated in-app path (checked against the real route table). |
| `escalate_to_support` | Blocked or wants a human → prefills the existing `/support` flow (or files the ticket via `user-api`). |

Deliberately absent: shell, network fetch, code execution, subagents, any write
to user data.

```python
agent = create_deep_agent(
    model=model,                       # nemotron-nano by default; deepseek on escalation
    system_prompt=AVI_SYSTEM_PROMPT,
    tools=[search_platform_docs, search_my_knowledge, open_feature, escalate_to_support],
    middleware=[TurnCap(max_turns=AVI_MAX_AGENT_STEPS),   # 6 — a widget, not a worker
                ContextEditing(...)],                     # keeps full history inside budget
    permissions=[FilesystemPermission(operations=["read"])],
    subagents=[],                                         # no delegation, no extra loops
    backend=StateBackend(),                               # in-state; no disk, no shell
    checkpointer=thread_checkpointer,
)
```

Declining subagents is a deliberate, documented reduction of the harness — and
it is the honest framework story: *we use Deep Agents' planning and
context-management middleware and decline its delegation middleware.*

---

## 6. Streaming contract (shared by both paths)

`frames.py` maps LangGraph output to the **existing `AgentRunEvent` shape** in
`frontend/src/lib/agentRun.ts`, so `lib/runState.ts`, `RunTimeline`,
`ChatAnswer` and `SourceCarousel` render Avi unchanged:

| LangGraph | Frame |
|---|---|
| run start | `run.started` |
| harness plan/todos | `plan.started` → `plan` |
| `AIMessageChunk` text (string **or** typed blocks) | `text` |
| tool start / arg deltas / result | `tool.start` / `tool.input` / `tool.result` |
| results carrying passages + routes | `tool.result.sources` (`kind:"knowledge"`, `route`, `docUrl`) |
| off-topic verdict | `avi.intent` (`kind`, `examples[]`) — new frame, ignored by existing reducers |
| end / failure | `run.completed` / `run.error` |

`avi.intent` is the only new frame; everything else is already understood by the
chat UI.

---

## 7. Knowledge ingestion — repo only

**Source of truth is git; the pipeline is the one we already run.** Avi's
knowledge base is one more knowledge base, owned by a reserved `platform` scope.

### 7.1 Corpus (`knowledge/avi/*.md`, generated then reviewed)

```yaml
---
id: agent-builder-model
title: Choosing a model in the Agent builder
route: /agent-builder          # the deep link
group: Build
tags: [agents, builder, model]
audience: user                 # user | admin | public
source: docs                   # docs | readme | agents-md | design
updated: 2026-10-11
---
## What it is
…
```

| Repo source | Ingestion |
|---|---|
| `frontend/src/content/docs.ts` | Generator walks the typed blocks (`paragraph`/`steps`/`bullets`/`callout`/`code`) → markdown, **one file per section**, `route: /docs#<sectionId>` (anchors already exist). ~33 sections. |
| `frontend/src/navigation/sidebarLinks.ts` + the route table in `App.tsx` | Generator emits the **feature catalog** (label, path, group, children) = the `open_feature` allow-list and the per-page seed. |
| `README.md`, `AGENTS.md`, `docs/design/*.md` | Split by heading into concepts / architecture / operations documents, `audience: public|user|admin`, so Avi can explain *how* the platform works and admin-only topics stay admin-scoped. |
| `frontend/src/admin/navigation/adminSidebarLinks.ts` + `infra/terraform/envs/prod/api_gateway.tf` | Admin-surface and API/limits documents (`audience: admin`) — the admin page's Avi gets them, the widget does not. |

**No crawler.** Refresh = re-run the generator.

### 7.2 Build

`make avi-knowledge` (`tools/avi-knowledge/`):

1. **generate** markdown into `knowledge/avi/`;
2. **validate** — unique `id`, `route` exists in the real route table, no broken
   relative links, no secrets/tokens, size caps, frontmatter schema;
3. **upload** to `raw/platform/<kbId>/<docId>/<file>.md`;
4. the **existing** pipeline does the rest: S3 `ObjectCreated` → EventBridge → SQS
   → `ingestion-dispatcher` → Step Functions → `ingestion-extract` →
   `ingestion-embed` (Titan) → `ingestion-index` → `documents.status=ready`.

`make avi-bootstrap` creates the reserved scope (`userId = platform`,
`KB = platform-docs`) and stable `docId`s once; re-uploads are idempotent (the
index stage is already delete-then-write per document via the manifest).

**One chunker change:** split on heading boundaries and prepend a breadcrumb to
every chunk (`Product docs > Agent builder > Choosing a model`), and keep `route`
+ `title` in chunk metadata. This is the single biggest retrieval win for a
question-shaped corpus, and it is what makes a source clickable.

**Drift guard in CI:** regenerate and fail if the committed corpus would change —
Avi can never silently answer from stale docs.

### 7.3 Retrieval at answer time

`retrieval.py` calls the same path `knowledge-mcp` uses (`search_candidates` →
RRF → Bedrock rerank opt-in → parent hydration) with the `platform` scope, so
**exact cache + semantic cache + single-flight come for free** (`core.cache`,
`core.semantic_cache`) — a repeated question costs zero Bedrock calls, the single
largest cost lever for a widget.

---

## 8. Guest path, limits and abuse protection

| Layer | Guest | Signed-in |
|---|---|---|
| API Gateway route throttle | `/v1/avi/ask`: burst **4** / rate **2** | `/v1/avi/session`: burst **10** / rate **5** |
| Per-caller window (`core.ratelimit`, atomic DynamoDB) | per **IP hash**: `AVI_GUEST_PER_HOUR=6`, `AVI_GUEST_PER_DAY=20` | per **userId**: `AVI_PER_HOUR=120`, `AVI_PER_DAY=1000` ("effectively unlimited", but bounded) |
| Per-conversation turns | n/a (stateless, capped history) | `AVI_MAX_AGENT_STEPS=6` per turn, `AVI_MAX_TURNS=40` per conversation |
| Input caps | question ≤ 2 000 chars, history ≤ 8 turns / 24 000 chars | same |
| Flow control | classifier-first (off-topic never generates) + 1 in-flight request per IP | bounded MicroVM sessions, auto-resume, 25-min hard cap |
| Storage | **nothing persisted** | transcript + feedback persisted |
| Kill switch | `aviEnabled` flag → launcher hides, both routes `503` | same |

Plus: every model call is admitted through `core.ratelimit_bedrock` (global
per-model token bucket), so Avi can never starve the product's own agents; and
**no Strands code runs inside Avi at all** — the classifier, the agent and the
judge are LangChain/Bedrock.

`429` responses carry `Retry-After`; the widget renders a calm inline note with
the exact wait, never an error toast.

---

## 9. Persistence (signed-in only)

| What | Where | Notes |
|---|---|---|
| Transcript | S3, one object per conversation (`conversations/<userId>/avi-<id>.json`) | Reuses `retrieval.layout.conversation_key` + the existing read-modify-write `append_turn` pattern |
| Conversation metadata | DynamoDB `USER#<userId>` / **`AVICHAT#<id>`** | New prefix; **separate from `CHAT#`**, so Avi never appears in the agent chat sidebar. Projected on `byUser` for the admin page. |
| **Feedback** | DynamoDB `USER#<userId>` / **`AVIFEEDBACK#<runId>`** | New item with new fields: `value` (up/down), `comment`, `categories[]`, `conversationId`, `messageId`, `question`, `answerPreview`, `sourcesUsed[]`, `routeClicked`, `model`, `classifierKind`, `latencyMs`, `tokensIn/out`, `costUsd`, `createdAt`, `updatedAt` |
| Traces | S3 `traces/avi/<runId>.json` + small DynamoDB index item | Admin-only; filterable in the Traces surface without mixing with agent traces |
| Evals | Existing eval repos, `kind="avi"` | Per-case Avi metrics (§10) |

New repository module `data/repositories/avi.py` holds all three entities, with
the key builders alongside the others in `data/keys.py`.

---

## 10. Evaluations, metrics and traces

### 10.1 Evaluation dataset (`tools/avi-knowledge/eval/avi-eval.jsonl`)

~60 committed cases, generated from the same corpus so they stay in sync:

| Case type | Example | Judge checks |
|---|---|---|
| Answerable | "How many knowledge bases can I create?" | correct + grounded + cites the right doc |
| Deep link | "Where do I change an agent's model?" | returns `/agent-builder`, and the route **exists** |
| Refusal | "1+1", "write me a React component", "what's the weather" | refused, kind=`off_topic`, examples offered |
| Boundary | "What is 1 MB in bytes?" (on-topic-ish) | not refused |
| Unknown | "Do you support on-prem deployment?" | says it is not documented, points to `/support` — **no hallucination** |
| Multi-turn | follow-up with a pronoun referring to the prior turn | resolves the reference from the sent history |

### 10.2 Metrics (all emitted, all on the admin dashboard)

- **Answer quality:** correctness (judge), groundedness/no-hallucination, citation
  precision, `hit@1` / `hit@3` of the expected page.
- **Link quality:** % answers with ≥1 valid deep link; `routeClicked` rate from
  the widget.
- **Classifier:** off-topic precision / recall / F1, fail-open rate, rules-stage
  share (cost saved).
- **Latency:** TTFT p50/p95, total p50/p95, classifier ms, retrieval ms — split by
  guest vs signed-in.
- **Cost:** tokens in/out, USD per answer, per user per day; Bedrock-throttle
  rejections.
- **Product:** dialogs opened, questions asked, answer→sign-in conversions
  (guests), thumbs up/down ratio, top unanswered questions.

Implementation: **CloudWatch EMF** via the existing `_emit_feedback_metric`
pattern (no extra API calls), one namespace `get1agent/avi`, plus an
`AviEvalReport` item per eval run. Evaluation runs are launched from the admin
page and executed by the **existing evaluations worker** — Avi is registered as
an eval target with `kind="avi"`, so no new evaluation engine is built.

### 10.3 Traces

Each Avi run writes one observation tree (same shape as agent traces) to
`traces/avi/<runId>.json`: classifier verdict + ms, retrieval candidates and
scores, tool calls, prompt/token counts, model, first-token and total latency,
cost, and the final answer. Admin → Avi links straight into the existing trace
viewer, filtered to Avi.

---

## 11. Admin page — **Avi** (`/admin/avi`)

Route in `frontend/src/App.tsx` under `/admin`, sidebar entry in
`adminSidebarLinks.ts`, API in `backend/services/admin/admin-console/src/avi.py`
mounted at `/v1/admin/avi/*`.

| Card | Controls |
|---|---|
| **Status** | Master `aviEnabled` kill switch (the existing `PLATFORM#SETTINGS/#FLAGS` mechanism), guest access on/off, current live config |
| **Models** | Answer model, classifier model, escalation model, judge model — pickers from the curated Bedrock list, with the measured latency of each next to it; "reset to defaults" |
| **Limits** | Guest per-IP/hour + per-day, signed-in per-user/hour + per-day, max agent steps, max input chars — written to the settings item and read by the services (`settings.py`, 60 s cache), so changes apply **without a redeploy** |
| **Feedback** | Table of `AVIFEEDBACK#` items: thumbs, comments, categories, the question, the answer, sources, model, latency, cost; filters + CSV export |
| **Evaluations** | Run the Avi eval dataset, history of runs, per-metric sparklines, case-by-case pass/fail with the judge's reasoning (reuses the eval components) |
| **Traces** | Latest Avi runs, latency/cost distributions, click through to a full trace |
| **Knowledge** | Corpus documents, last ingest time, per-document status; a link to trigger a re-index (the `make avi-knowledge` path) |

Guardrails: every route requires the admin role (the existing admin-console
check), every mutation is written to the settings item with `updatedBy`/
`updatedAt`, and the kill switch is audited.

---

## 12. Frontend widget

| File | Purpose |
|---|---|
| `components/avi/AviLauncher.tsx` | The bottom-right button; opens the dialog. Lazy-loaded. |
| `components/avi/AviDialog.tsx` | Right-side dialog (desktop) / bottom sheet (mobile), themed, focus-trapped, `Esc` to close, remembers open state. **Not a page.** |
| `components/avi/AviMessage.tsx` | Reuses `ChatAnswer` + round `[n]` badges; adds a **route chip** ("Open Agent builder →") that navigates the SPA; a collapsed run timeline while working. |
| `components/avi/AviExampleChips.tsx` | The tappable examples from the off-topic nudge and the route-aware starters. |
| `components/avi/AviFeedback.tsx` | Thumbs + comment + categories for signed-in users. |
| `lib/avi.ts` | `POST /v1/avi/ask` (guest) / `POST /v1/avi/session` + MicroVM (signed-in) / feedback — the only place that branches on identity. |

**Mount list — 4 shells, so no page can be missed:**

| Mount | Covers |
|---|---|
| `layouts/MainLayout.tsx` | every signed-in app route |
| `layouts/PublicLayout.tsx` | footer/public pages opened from the landing surface |
| `pages/LoginPage.tsx` | the landing page (`/`) |
| `pages/ArchitecturePage.tsx` | `/architecture` |

`AdaptiveLayout` swaps between the two layouts, so it needs no mount of its own.
`/trace/:token` is deliberately excluded (share-link viewer, no app chrome).

Smoothness details: optimistic user bubble, typing indicator during the
classifier (~300 ms), tokens streamed as they arrive, sources and chips appearing
inline, and a composer that never blocks. If a guest hits the cap, the dialog
shows the wait plus a **sign-in to keep asking** button — the natural upsell.

---

## 13. Infrastructure

- `infra/terraform/modules/avi_runtime/` — ECR repo (same lifecycle policy as
  `agent_runtime`), the MicroVM image, the control-plane Lambda, the **guest
  Lambda + its `RESPONSE_STREAM` Function URL**, and both API Gateway routes.
- `backend/registry.json` — register `avi-guest` and `avi-session` under a new
  `avi` group, so `deploy-backend.sh` and the Backend workflow pick them up with
  no new tooling.
- `infra/aws/deploy-avi.sh` — build/push the ARM64 image, apply
  `module.avi_runtime` (mirrors `deploy-agent-runtime.sh`).
- Makefile: `avi-build`, `avi-knowledge`, `avi-bootstrap`, `avi-deploy`,
  `avi-eval`, `avi-test`.
- GitHub: new `avi` group checkbox for Lambda code; `avi-knowledge` drift check on
  PRs touching `frontend/src/content/docs.ts`, `README.md`, `AGENTS.md`,
  `docs/design/**` or `frontend/src/navigation/**`.
- Local (Floci): `AVI_MODE=local` runs the agent on `:8091`
  (`VITE_AVI_URL=http://localhost:8091`), `VECTOR_STORE=local` +
  `EMBED_MODE=ollama` keep the whole loop offline; the guest path runs as a plain
  local Lambda handler.

---

## 14. Phased plan

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **0 — Corpus** (1 d) | `tools/avi-knowledge/` generators + validator; ~60 documents in `knowledge/avi/`; `avi-bootstrap` creates `platform-docs` | Every `docs.ts` section and every sidebar route exists as a validated document |
| **1 — Retrieval** (1 d) | Platform-scoped `retrieval.py` + heading/breadcrumb chunking | ≥ 90 % of a 20-question set returns the correct page as source #1 |
| **2 — Classifier** (0.5 d) | `classifier.py` + the 60-case eval set | Off-topic F1 ≥ 0.95, fail-open on timeout, rules stage catches ≥ 30 % of real traffic |
| **3 — Agent service** (1.5 d) | `backend/avi/` container: model, tools, frames, persistence, `/ping`, feedback | Local end-to-end: question → tokens → `[n]` sources → route chip → feedback stored |
| **4 — Guest path** (1 d) | `avi-guest` Lambda + Function URL + per-IP limits + nudge with chips | Guest gets a streamed answer in < 1 s TTFT with nothing persisted; cap returns a calm `429` |
| **5 — Deployment** (1 d) | `avi_runtime` Terraform, control plane, MicroVM image, both routes | Production: warm TTFT < 700 ms, cold session < 3 s |
| **6 — Widget** (1.5 d) | Launcher on all 4 shells, dialog, chips, citations, feedback, route-aware starters | Avi present on every page; guest and signed-in flows both correct |
| **7 — Admin page** (1.5 d) | `/admin/avi` with all seven cards + `/v1/admin/avi/*` routes | Kill switch hides the widget live; model + limit changes take effect without redeploy |
| **8 — Evals & metrics** (1 d) | Eval runs via the existing worker, EMF metrics, dashboard, trace view | Avi's eval suite runs from the admin page; every §10.2 metric is visible |
| **9 — Hardening & polish** (1 d) | Guardrail, Bedrock admission, X-Ray, drift CI, docs (`AGENTS.md`, `docs/design/`) | 60-case acceptance set passes; docs updated |

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| Answer quality is the only thing users judge | Ground every claim, cite `[n]`, ship the committed 60-case eval set, run it before each deploy from the admin page |
| Classifier blocks a real platform question | Rules stage short-circuits known platform vocabulary; model stage **fails open**; the nudge always offers chips, so a wrong refusal is one tap from recovery |
| Guest endpoint abused | Separate route with the strictest limits, per-IP hashed counters, classifier-first (no generation for off-topic), 1 in-flight per IP, kill switch, and `core.ratelimit_bedrock` admission |
| Streaming silently regresses to non-streaming | `disable_streaming=False` **and** a startup self-test that asserts a first `AIMessageChunk`, exposed on `/ping` as `{"streaming": true}` |
| Two frameworks (Strands + LangChain) to maintain | Avi is isolated in its own image/lockfile/scope; the integration surface is only the SSE frames, the DynamoDB keys and the retrieval package |
| Corpus drift | CI regeneration check + `updated` frontmatter reviewed in PRs |
| Prompt injection through ingested text | Corpus is committed and reviewed; tool results treated as data, never instructions; no shell, no network, no writes, read-only permissions |
| Model deprecation | All four model ids are admin-editable config, so a swap needs no code change |

---

## 16. Open items (minor — I'll proceed with these unless you object)

1. `/assistant` maximised view: I'll **skip it** (you said dialog only); the
   admin page and trace links cover sharing needs.
2. Admin Avi conversations list: I'll add a read-only conversation viewer inside
   **admin → Avi** rather than the user chat sidebar (keeps `CHAT#` clean).
3. `AVI_PER_HOUR=120` / `AVI_PER_DAY=1000` for signed-in users — high enough to
   feel unlimited, low enough to bound a leaked token.
4. Guest cap `6/hour, 20/day` per IP hash — raise if the landing trial feels
   tight once we see real traffic.

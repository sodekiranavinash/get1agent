# AI Assistant — the in-product AI assistant

**Status:** plan for sign-off (no code yet)
**Goal:** a floating **AI Assistant** button at the **bottom-right of every page** (landing
and public pages included) that opens a **dialog, not a page**. AI Assistant streams
answers, explains what the platform can do, deep-links the feature the user is
asking about, and politely redirects non-platform questions. Built on LangChain
**Deep Agents** (deliberately not Strands), grounded in repo knowledge ingested
through the platform's existing pipeline, fully controllable from a new
**admin → AI Assistant** page.

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
| 8 | **Full admin page "AI Assistant"** — kill switch, model pickers, limits, guest toggle, feedback, eval dashboard, traces. |
| 9 | **Separate folder structure** for everything AI Assistant, reusing existing components through imports. |
| 10 | **No Strands classifier.** Intent classification is its own component with its own model. |
| 11 | Evaluations, metrics and traces for AI Assistant specifically, "as much as possible". |

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
| **Intent classifier** | `zai.glm-4.7-flash` | `AI_ASSISTANT_CLASSIFIER_MODEL` | Lowest-variance latency (230–423 ms), already your `AGENT_PLANNER_MODEL` + `CUSTOM_TOOLS_GENERATOR_MODEL`, reliable JSON. `ministral-3-8b` is no faster (305 ms). |
| **Answer agent** | `nvidia.nemotron-nano-3-30b` | `AI_ASSISTANT_MODEL` | Fastest first token by ~100 ms and answered all four questions correctly — the single biggest perceived-speed lever. |
| **Escalation** (only "how do I build X" reasoning questions) | `deepseek.v3.2` | `AI_ASSISTANT_REASONING_MODEL` | Cheapest of the strong reasoners; used only when the classifier says `how_to` + reasoning. |
| **Evaluations judge** | `amazon.nova-2-lite-v1:0` | `AI_ASSISTANT_JUDGE_MODEL` | Already your `EVAL_JUDGE_MODEL`; 1M context for long rubrics. Never the same model as the one being judged. |

All four are user-selectable on the admin page; `AI_ASSISTANT_MODEL` et al. remain the
defaults.

---

## 2. Shape

```
        GUEST (no token)                              SIGNED IN (Auth0 JWT)
              │                                                │
              │  POST /v1/ai-assistant/guest                   │  POST /v1/ai-assistant/ask
              │  (API GW, NONE auth, throttle 4/2)             │  (API GW, JWT, throttle 20/10)
              ▼                                                ▼
              └───────────────────────┬────────────────────────┘
                                      ▼
                    ai-assistant Lambda (one zip, API Gateway)
                    handler.py · buffered SSE · no session token
                    identity: verified claims (/ask) | IP hash (/guest)
                                      │
                              shared package
                       backend/ai-assistant/src/*
                    classifier · retrieval · frames · deep_links
                    conversations · traces · limits · identity
                                      ▼
        ┌────────────────────────────────────────────────────────────────────┐
        │ platform KB (idx-platform) · Bedrock · S3 conversations · DynamoDB  │
        └────────────────────────────────────────────────────────────────────┘
                                  ▲
                    admin → AI Assistant  (/admin/ai-assistant)  ·  evals  ·  EMF metrics  ·  traces
```

**One function, two routes, on purpose:**

- **Guest** — the `/guest` route has **no authorizer**, so the Lambda hashes the
  caller's IP into a rate-limit bucket instead. It answers from the platform KB
  with **no tools** and **stores nothing**. One POST, no session to manage.
- **Signed-in** — the `/ask` route runs the Auth0 JWT authorizer, and the Lambda
  reads the **verified claims** out of the event. There is no session to bootstrap
  and no token to mint, forward or verify, so nothing has to stay in sync between
  two components.

Both responses are **buffered**: API Gateway HTTP APIs cannot stream and cap an
integration at 30 s, so the run is assembled and returned as one SSE body. The
frames are identical to a live stream, so the widget does not branch.

The browser uses one reducer for both (`lib/runState.ts`), so the widget code
does not branch on identity — only the URL does.

---

## 3. Folder structure (everything AI Assistant, self-contained)

```
backend/
  ai-assistant/                                  ← the agent service (its own image + lockfile)
    main.py                             FastAPI: POST /invocations (SSE), GET /ping, POST /feedback
    ai-assistant/                                ← THE SHARED PACKAGE — imported by the guest Lambda too
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
  services/ai-assistant/
    guest/                              ← guest Lambda (imports backend/ai-assistant/ai-assistant)
      handler.py  Makefile  pyproject.toml  tests/
    control-plane/                      ← ai-assistant Lambda (Node, mirrors agent-run/index.mjs)
      index.mjs  package.json  Makefile
    microvm/                            ← SSE proxy (copy of agent-run/microvm, retargeted)
      app.mjs  Dockerfile  package.json
  services/admin/admin-console/
    src/ai-assistant.py                          ← admin routes: /v1/admin/ai-assistant/* (new module, imported by handler.py)
  packages/data/repositories/
    ai-assistant.py                              ← AviChat metadata, AiAssistantFeedback, AviEvalReport

frontend/src/
  components/ai-assistant/                       ← the widget (self-contained)
    AiAssistantLauncher.tsx  AiAssistantDialog.tsx  AiAssistantMessage.tsx  AviComposer.tsx
    AviExampleChips.tsx  AiAssistantFeedback.tsx  useAiAssistantRun.ts
  lib/aiAssistant.ts                             ← one API surface for both paths
  content/aiAssistantStarters.ts                ← route-aware example questions
  admin/pages/AdminAiAssistantPage.tsx          ← the admin page
  admin/lib/adminAiAssistant.ts                 ← admin API client

backend/ai-assistant/                            ← the Lambda: handler.py + src/*
  handler.py                                       both routes, buffered SSE, claims → userId
  src/                                             classifier · retrieval · frames · conversations
                                                   traces · limits · identity · metrics · settings
tools/ai-assistant-knowledge/                    ← generators + validator (make ai-assistant-knowledge)
knowledge/ai-assistant/                          ← generated, committed markdown (the corpus)
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
# ai-assistant/classifier.py
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
- **Stage 1 — model** (`AI_ASSISTANT_CLASSIFIER_MODEL`, `zai.glm-4.7-flash`, ~300 ms):
  strict JSON, `temperature=0`, `maxTokens≈80`, 2 few-shot examples per class.
  Best-effort: on timeout/parse failure it **fails open to `platform`** — never
  block a real user behind a classifier hiccup.
- **Stage 2 — examples**: when `off_topic`, the nudge ships 3–4 example
  questions, chosen by `route_hint` from `aiAssistantStarters.ts`. They render as
  **tappable chips**; one tap re-asks that question. That is decision #6.
- **Stage 3 — escalation**: `platform` + `how_to` with a complexity signal
  switches the answer model to `AI_ASSISTANT_REASONING_MODEL` for that turn.

Copy (in `prompts.py`, so it is editable without a code change):

> I'm AI Assistant — I'm here for the get1agent platform, so I'm best at questions about
> agents, knowledge bases, workflows, tools and your account. I'm not able to
> help with that one. Try one of these:
> `How do I add a knowledge base?` · `Where do I build an agent?` ·
> `What's the difference between Storage and a knowledge base?` ·
> `How do I see my token usage?`

Never scolding, never "I cannot answer that" — always an invitation plus a way
forward.

---

## 5. What AI Assistant can do (tools — signed-in path only)

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
    system_prompt=AI_ASSISTANT_SYSTEM_PROMPT,
    tools=[search_platform_docs, search_my_knowledge, open_feature, escalate_to_support],
    middleware=[TurnCap(max_turns=AI_ASSISTANT_MAX_AGENT_STEPS),   # 6 — a widget, not a worker
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
`ChatAnswer` and `SourceCarousel` render AI Assistant unchanged:

| LangGraph | Frame |
|---|---|
| run start | `run.started` |
| harness plan/todos | `plan.started` → `plan` |
| `AIMessageChunk` text (string **or** typed blocks) | `text` |
| tool start / arg deltas / result | `tool.start` / `tool.input` / `tool.result` |
| results carrying passages + routes | `tool.result.sources` (`kind:"knowledge"`, `route`, `docUrl`) |
| off-topic verdict | `ai-assistant.intent` (`kind`, `examples[]`) — new frame, ignored by existing reducers |
| end / failure | `run.completed` / `run.error` |

`ai-assistant.intent` is the only new frame; everything else is already understood by the
chat UI.

---

## 7. Knowledge ingestion — repo only

**Source of truth is git; the pipeline is the one we already run.** AI Assistant's
knowledge base is one more knowledge base, owned by a reserved `platform` scope.

### 7.1 Corpus (`knowledge/ai-assistant/*.md`, generated then reviewed)

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
| `README.md`, `AGENTS.md`, `docs/design/*.md` | Split by heading into concepts / architecture / operations documents, `audience: public|user|admin`, so AI Assistant can explain *how* the platform works and admin-only topics stay admin-scoped. |
| `frontend/src/admin/navigation/adminSidebarLinks.ts` + `infra/terraform/envs/prod/api_gateway.tf` | Admin-surface and API/limits documents (`audience: admin`) — the admin page's AI Assistant gets them, the widget does not. |

**No crawler.** Refresh = re-run the generator.

### 7.2 Build

`make ai-assistant-knowledge` (`tools/ai-assistant-knowledge/`):

1. **generate** markdown into `knowledge/ai-assistant/`;
2. **validate** — unique `id`, `route` exists in the real route table, no broken
   relative links, no secrets/tokens, size caps, frontmatter schema;
3. **upload** to `raw/platform/<kbId>/<docId>/<file>.md`;
4. the **existing** pipeline does the rest: S3 `ObjectCreated` → EventBridge → SQS
   → `ingestion-dispatcher` → Step Functions → `ingestion-extract` →
   `ingestion-embed` (Titan) → `ingestion-index` → `documents.status=ready`.

`make ai-assistant-bootstrap` creates the reserved scope (`userId = platform`,
`KB = platform-docs`) and stable `docId`s once; re-uploads are idempotent (the
index stage is already delete-then-write per document via the manifest).

**One chunker change:** split on heading boundaries and prepend a breadcrumb to
every chunk (`Product docs > Agent builder > Choosing a model`), and keep `route`
+ `title` in chunk metadata. This is the single biggest retrieval win for a
question-shaped corpus, and it is what makes a source clickable.

**Drift guard in CI:** regenerate and fail if the committed corpus would change —
AI Assistant can never silently answer from stale docs.

### 7.3 Retrieval at answer time

`retrieval.py` calls the same path `knowledge-mcp` uses (both legs → RRF → the
shared cross-encoder rerank → parent hydration) with the `platform` scope, so
**exact cache + semantic cache + single-flight come for free** (`core.cache`,
`core.semantic_cache`) — a repeated question costs zero Bedrock calls, the single
largest cost lever for a widget.

Reranking is **on by default** here (unlike `knowledge-mcp`, where it is
opt-in), because RRF scores agreement between the two legs rather than relevance
and the resulting order is what the answer and its `[n]` citations are built
from. It hydrates up to `AI_ASSISTANT_RERANK_CANDIDATES` (24) parents so the
reranker has real recall to work with, records `rerankScore` per passage and
`rerank.applied` on the diagnostic, and falls back to the RRF order if the
reranker is unreachable. `AI_ASSISTANT_RERANK=0` turns it off.

---

## 8. Guest path, limits and abuse protection

| Layer | Guest | Signed-in |
|---|---|---|
| API Gateway route throttle | `/v1/ai-assistant/guest`: burst **4** / rate **2** | `/v1/ai-assistant/ask`: burst **20** / rate **10** |
| Per-caller window (`core.ratelimit`, atomic DynamoDB) | per **IP hash**: `AI_ASSISTANT_GUEST_PER_HOUR=6`, `AI_ASSISTANT_GUEST_PER_DAY=20` | per **userId**: `AI_ASSISTANT_PER_HOUR=120`, `AI_ASSISTANT_PER_DAY=1000` ("effectively unlimited", but bounded) |
| Per-conversation turns | n/a (stateless, capped history) | `AI_ASSISTANT_MAX_AGENT_STEPS=6` per turn, `AI_ASSISTANT_MAX_TURNS=40` per conversation |
| Input caps | question ≤ 2 000 chars, history ≤ 8 turns / 24 000 chars | same |
| Flow control | classifier-first (off-topic never generates) + 1 in-flight request per IP | classifier-first + agent-step cap + a 24 s soft turn budget under the 30 s gateway ceiling |
| Storage | **nothing persisted** | transcript + feedback persisted |
| Kill switch | `aviEnabled` flag → launcher hides, both routes `503` | same |

Plus: every model call is admitted through `core.ratelimit_bedrock` (global
per-model token bucket), so AI Assistant can never starve the product's own agents; and
**no Strands code runs inside AI Assistant at all** — the classifier, the agent and the
judge are LangChain/Bedrock.

`429` responses carry `Retry-After`; the widget renders a calm inline note with
the exact wait, never an error toast.

---

## 9. Persistence (signed-in only)

| What | Where | Notes |
|---|---|---|
| Transcript | S3, one object per conversation (`conversations/<userId>/ai-assistant-<id>.json`) | Reuses `retrieval.layout.conversation_key` + the existing read-modify-write `append_turn` pattern |
| Conversation metadata | DynamoDB `USER#<userId>` / **`AICHAT#<id>`** | New prefix; **separate from `CHAT#`**, so AI Assistant never appears in the agent chat sidebar. Projected on `byUser` for the admin page. |
| **Feedback** | DynamoDB `USER#<userId>` / **`AIFEEDBACK#<runId>`** | New item with new fields: `value` (up/down), `comment`, `categories[]`, `conversationId`, `messageId`, `question`, `answerPreview`, `sourcesUsed[]`, `routeClicked`, `model`, `classifierKind`, `latencyMs`, `tokensIn/out`, `costUsd`, `createdAt`, `updatedAt` |
| Traces | S3 `traces/ai-assistant/<runId>.json` + small DynamoDB index item | Admin-only; filterable in the Traces surface without mixing with agent traces |
| Evals | Existing eval repos, `kind="ai-assistant"` | Per-case AI Assistant metrics (§10) |

New repository module `data/repositories/ai-assistant.py` holds all three entities, with
the key builders alongside the others in `data/keys.py`.

---

## 10. Evaluations, metrics and traces

### 10.1 Evaluation dataset (`tools/ai-assistant-knowledge/eval/ai-assistant-eval.jsonl`)

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
pattern (no extra API calls), one namespace `get1agent/ai-assistant`, plus an
`AviEvalReport` item per eval run. Evaluation runs are launched from the admin
page and executed by the **existing evaluations worker** — AI Assistant is registered as
an eval target with `kind="ai-assistant"`, so no new evaluation engine is built.

### 10.3 Traces

Each AI Assistant run writes one observation tree (same shape as agent traces) to
`traces/ai-assistant/<runId>.json`: classifier verdict + ms, retrieval candidates and
scores, tool calls, prompt/token counts, model, first-token and total latency,
cost, and the final answer. Admin → AI Assistant links straight into the existing trace
viewer, filtered to AI Assistant.

---

## 11. Admin page — **AI Assistant** (`/admin/ai-assistant`)

Route in `frontend/src/App.tsx` under `/admin`, sidebar entry in
`adminSidebarLinks.ts`, API in `backend/services/admin/admin-console/src/ai-assistant.py`
mounted at `/v1/admin/ai-assistant/*`.

| Card | Controls |
|---|---|
| **Status** | Master `aviEnabled` kill switch (the existing `PLATFORM#SETTINGS/#FLAGS` mechanism), guest access on/off, current live config |
| **Models** | Answer model, classifier model, escalation model, judge model — pickers from the curated Bedrock list, with the measured latency of each next to it; "reset to defaults" |
| **Limits** | Guest per-IP/hour + per-day, signed-in per-user/hour + per-day, max agent steps, max input chars — written to the settings item and read by the services (`settings.py`, 60 s cache), so changes apply **without a redeploy** |
| **Feedback** | Table of `AIFEEDBACK#` items: thumbs, comments, categories, the question, the answer, sources, model, latency, cost; filters + CSV export |
| **Evaluations** | Run the AI Assistant eval dataset, history of runs, per-metric sparklines, case-by-case pass/fail with the judge's reasoning (reuses the eval components) |
| **Traces** | Latest AI Assistant runs, latency/cost distributions, click through to a full trace |
| **Knowledge** | Corpus documents, last ingest time, per-document status; a link to trigger a re-index (the `make ai-assistant-knowledge` path) |

Guardrails: every route requires the admin role (the existing admin-console
check), every mutation is written to the settings item with `updatedBy`/
`updatedAt`, and the kill switch is audited.

---

## 12. Frontend widget

| File | Purpose |
|---|---|
| `components/ai-assistant/AiAssistantLauncher.tsx` | The bottom-right button; opens the dialog. Lazy-loaded. |
| `components/ai-assistant/AiAssistantDialog.tsx` | Right-side dialog (desktop) / bottom sheet (mobile), themed, focus-trapped, `Esc` to close, remembers open state. **Not a page.** |
| `components/ai-assistant/AiAssistantMessage.tsx` | Reuses `ChatAnswer` + round `[n]` badges; adds a **route chip** ("Open Agent builder →") that navigates the SPA; a collapsed run timeline while working. |
| `components/ai-assistant/AviExampleChips.tsx` | The tappable examples from the off-topic nudge and the route-aware starters. |
| `components/ai-assistant/AiAssistantFeedback.tsx` | Thumbs + comment + categories for signed-in users. |
| `lib/aiAssistant.ts` | `POST /v1/ai-assistant/ask` (signed-in, JWT) / `POST /v1/ai-assistant/guest` (no authorizer) / feedback — the only place that branches on identity, and the only SSE parser. |

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

- `infra/terraform/envs/prod/backend.tf` — one `module "ai_assistant"` (the Lambda
  zip, 1024 MB, 30 s timeout matched to the gateway ceiling), plus its two routes in
  `api_gateway.tf`: `/ask` (`JWT`, throttle 20/10) and `/guest` (`NONE`, 4/2). No
  ECR, no MicroVM image, no control plane and no Function URL.
- `backend/ai-assistant/Makefile` — `make -C backend/ai-assistant package` builds
  `dist/function.zip` (~21 MB zipped / 81 MB unzipped), bundling the agent
  framework and dropping what the Lambda runtime already provides.
- `backend/registry.json` — `ai-assistant` registered under the `ai-assistant`
  group, so the deploy script and Backend workflow pick it up with no new tooling.
- Makefile: `ai-assistant-knowledge`, `ai-assistant-bootstrap`, `ai-assistant-upload`,
  `ai-assistant-status`,
  `ai-assistant-eval`, `ai-assistant-test`.
- GitHub: a named **AI Assistant** job runs `make test-ai-assistant`; the
  `ai-assistant-knowledge` drift check runs on
  PRs touching `frontend/src/content/docs.ts`, `README.md`, `AGENTS.md`,
  `docs/design/**` or `frontend/src/navigation/**`.
- Local (Floci): the `ai-assistant` service in the stack — brought up by
  `make floci`/`floci-up`, rebuilt by `make floci-reload`, stopped by
  `make floci-down` — serves `:8091` from `backend/ai-assistant/main.py`, a small
  ASGI server that synthesises the API Gateway event and calls the **same**
  `handler.lambda_handler` production runs. It stands in for the gateway, so it
  also verifies the Auth0 token itself (`src/local_auth.py`, stdlib-only RS256 +
  JWKS) and answers `401` for anything it cannot verify — the check moves, it is
  never dropped. Guests need no setup. It runs in a container
  (`backend/ai-assistant/Dockerfile.dev`, built on Linux from the committed
  `uv.lock`) because the Lambda zip is built from the host's macOS wheels, which a
  Linux Lambda container cannot import; its port is published on loopback only.
  `fastapi`/`uvicorn` are a dev dependency group, excluded from the Lambda zip, and
  `frontend/.env.local` points `VITE_AI_ASSISTANT_URL` at this service.
  `VECTOR_STORE=local` + `EMBED_MODE=local` keep retrieval offline; reranking
  follows `RERANK_MODE` from `.env` — `none` locally, because the account's
  cross-region Bedrock Rerank throttles and costs 6–26s of retries per turn for
  the same RRF order it falls back to. `make floci-rerank` + `RERANK_MODE=local`
  runs the real cross-encoder instead.

---

## 14. Phased plan

| Phase | Deliverable | Exit criterion |
|---|---|---|
| **0 — Corpus** (1 d) | `tools/ai-assistant-knowledge/` generators + validator; ~60 documents in `knowledge/ai-assistant/`; `ai-assistant-bootstrap` creates `platform-docs` | Every `docs.ts` section and every sidebar route exists as a validated document |
| **1 — Retrieval** (1 d) | Platform-scoped `retrieval.py` + heading/breadcrumb chunking | ≥ 90 % of a 20-question set returns the correct page as source #1 |
| **2 — Classifier** (0.5 d) | `classifier.py` + the 60-case eval set | Off-topic F1 ≥ 0.95, fail-open on timeout, rules stage catches ≥ 30 % of real traffic |
| **3 — Agent service** (1.5 d) | `backend/ai-assistant/` container: model, tools, frames, persistence, `/ping`, feedback | Local end-to-end: question → tokens → `[n]` sources → route chip → feedback stored |
| **4 — Guest path** (1 d) | `ai-assistant` Lambda + Function URL + per-IP limits + nudge with chips | Guest gets a streamed answer in < 1 s TTFT with nothing persisted; cap returns a calm `429` |
| **5 — Deployment** (1 d) | `ai_assistant_runtime` Terraform, control plane, MicroVM image, both routes | Production: warm TTFT < 700 ms, cold session < 3 s |
| **6 — Widget** (1.5 d) | Launcher on all 4 shells, dialog, chips, citations, feedback, route-aware starters | AI Assistant present on every page; guest and signed-in flows both correct |
| **7 — Admin page** (1.5 d) | `/admin/ai-assistant` with all seven cards + `/v1/admin/ai-assistant/*` routes | Kill switch hides the widget live; model + limit changes take effect without redeploy |
| **8 — Evals & metrics** (1 d) | Eval runs via the existing worker, EMF metrics, dashboard, trace view | AI Assistant's eval suite runs from the admin page; every §10.2 metric is visible |
| **9 — Hardening & polish** (1 d) | Guardrail, Bedrock admission, X-Ray, drift CI, docs (`AGENTS.md`, `docs/design/`) | 60-case acceptance set passes; docs updated |

---

## 15. Risks

| Risk | Mitigation |
|---|---|
| Answer quality is the only thing users judge | Ground every claim, cite `[n]`, ship the committed 60-case eval set, run it before each deploy from the admin page |
| Classifier blocks a real platform question | Rules stage short-circuits known platform vocabulary; model stage **fails open**; the nudge always offers chips, so a wrong refusal is one tap from recovery |
| Guest endpoint abused | Separate route with the strictest limits, per-IP hashed counters, classifier-first (no generation for off-topic), 1 in-flight per IP, kill switch, and `core.ratelimit_bedrock` admission |
| Streaming silently regresses to non-streaming | `disable_streaming=False` **and** a startup self-test that asserts a first `AIMessageChunk`, exposed on `/ping` as `{"streaming": true}` |
| Two frameworks (Strands + LangChain) to maintain | AI Assistant is isolated in its own image/lockfile/scope; the integration surface is only the SSE frames, the DynamoDB keys and the retrieval package |
| Corpus drift | CI regeneration check + `updated` frontmatter reviewed in PRs |
| Prompt injection through ingested text | Corpus is committed and reviewed; tool results treated as data, never instructions; no shell, no network, no writes, read-only permissions |
| Model deprecation | All four model ids are admin-editable config, so a swap needs no code change |

---

## 16. Open items (minor — I'll proceed with these unless you object)

1. `/assistant` maximised view: I'll **skip it** (you said dialog only); the
   admin page and trace links cover sharing needs.
2. Admin AI Assistant conversations list: I'll add a read-only conversation viewer inside
   **admin → AI Assistant** rather than the user chat sidebar (keeps `CHAT#` clean).
3. `AI_ASSISTANT_PER_HOUR=120` / `AI_ASSISTANT_PER_DAY=1000` for signed-in users — high enough to
   feel unlimited, low enough to bound a leaked token.
4. Guest cap `10 / 3 minutes, 60/hour, 100/day` per IP hash. The **3-minute burst
   window is the one a visitor actually meets**: with an hour as the shortest window
   a handful of questions produced *"try again in about 16 min"*, which reads as a
   wall rather than a rate. Ten in three minutes is the promise; the hour and day
   windows still bound a loop and a patient script.

# Agentic Chat — Architecture Spec

Medium-depth spec for implementing a multi-agent chat product. This repo is a **monorepo**: `frontend/` (SPA), `agents/` (AgentCore runtimes), `tools/` (MCP + agent tool Lambdas), `backend/` (history and other HTTP APIs), `infra/` (Terraform, AWS CLI, and other AWS ops). Coding agents should treat this document as the source of truth for *what* we are building and *how* pieces connect. Do not invent extra product surface unless this spec is updated.

---

## 1. What we are building

A logged-in chat product where:

- Each specialist agent has its own URL and the same chatbot UI.
- A later **host agent** at `/agents` can delegate to those same specialists over **A2A**.
- The model loop is **Strands on Amazon Bedrock AgentCore Runtime**, calling **Bedrock** models.
- Tools are reached through **AgentCore MCP Gateway** (Lambda targets, language chosen per tool).
- The UI shows **live execution**: tool name, args, duration, tokens so far; for the host, also **which sub-agent** ran and *its* tool calls.
- Conversations are persisted and can be **resumed**.
- Every public HTTP call is rejected unless it carries a valid **Auth0** access token.
- AWS is created with **Terraform**. **GitHub Actions** applies infra and ships app releases (no click-ops).

**Out of scope for v1:** custom planner UI, multi-user shared threads, billing, voice.

---

## 2. Frontend (`frontend/`)

Stack today: Vite + React 19 + React Router 7, under `frontend/`. Chat **routes** live here; agent **runtime code** lives in `agents/` (see §12). One shared chat shell; per-route config (title, agent id, system copy) is the only difference at first.

| Route | Role | Backend `agentId` |
| --- | --- | --- |
| `/agents` | Host / orchestrator (phase 2) | `host` |
| `/agents/trafficrules` | Specialist | `trafficrules` |
| `/agents/publicmoney` | Specialist | `publicmoney` |
| `/agents/companyInfo` | Specialist | `companyInfo` |

Add more specialists the same way: new route + registry row. Do **not** hard-code AgentCore ARNs in the UI. The UI only knows `agentId` and talks to **our API Gateway**.

Shared chatbot responsibilities:

- Auth0 login (SPA) and attach `Authorization: Bearer <access_token>` to every API call.
- Stream the reply and render tool / agent events inline.
- List conversations, open one, continue it (`conversationId` + `sessionId` from the history API).
- Same visual chrome; later we can specialize prompts, starters, or side panels per agent.

Suggested frontend layout (when implementing):

```
frontend/src/agents/
  registry.ts          # agentId, path, title, phase
  pages/AgentChatPage.tsx
  components/ChatShell.tsx
  components/MessageList.tsx
  components/ToolEventCard.tsx
  api/chatClient.ts    # SSE / fetch stream
  api/historyClient.ts
  auth/Auth0Provider.tsx
```

Wire routes in `frontend/src/app/App.tsx`. Keep portfolio pages (`/`, `/privacy`) unchanged. Do **not** put Strands / AgentCore Python, MCP servers, backend APIs, or Lambda handlers under `frontend/`.

---

## 3. System map

```
Browser (`frontend/`)
  Auth0 SPA  ──access token──►  Amazon API Gateway (JWT authorizer)
                                    │
                    ┌───────────────┼────────────────┐
                    ▼               ▼                ▼
              POST /chat/stream   GET /conversations   POST /conversations/{id}/resume
                    │               │                  │
                    │               └──── backend/ (history, resume) ──── same S3 sessions bucket
                    ▼
              AgentCore Runtime (Python Strands + BedrockModel)
                    │
                    ├── Strands S3SessionManager  (messages + agent state; no AgentCore Memory, no DynamoDB)
                    ├── Bedrock Knowledge Base  (docs in a **different** S3 bucket — see §7)
                    ├── AgentCore MCP Gateway ──► Lambda tools (Python / Node / Go)
                    └── A2A (host only) ──► other AgentCore Runtimes (same specialists)
```

**Public internet never talks to AgentCore directly.** API Gateway is the only origin the SPA trusts. Gateway maps `agentId` → Runtime ARN (or alias) server-side.

**Yes: Auth0 can be enforced on API Gateway so invalid tokens never reach AgentCore.** Use an HTTP API (or REST API) **JWT authorizer** with Auth0’s OIDC discovery URL, issuer, and audience. Unauthenticated requests get `401` at the edge.

Defense in depth (recommended, not optional for production):

1. API Gateway JWT authorizer (Auth0) — SPA / human callers.
2. AgentCore Runtime inbound `CUSTOM_JWT` (same Auth0 issuer/audience) — in case something bypasses the gateway.
3. AgentCore Gateway inbound JWT or IAM — Runtime → MCP tools. Prefer **IAM / runtime identity** for tool calls so user JWTs are not forwarded blindly into every Lambda. Use OAuth-on-behalf-of only when a tool must call a user-owned third-party API.

Auth0 notes:

- SPA: Authorization Code + PKCE.
- API identifier (audience) must match what Gateway and AgentCore expect (e.g. `https://api.yourdomain.com` or a dedicated API identifier).
- For Auth0 + AgentCore Gateway JWT, prefer **`allowedAudience`**; Auth0 often puts the client id in `azp`, which can break `allowedClients` checks.
- Put `sub` (Auth0 user id) on every persisted row as `userId`. Never trust a `userId` from the request body.

---

## 4. Request path (chat)

1. User is on `/agents/trafficrules` (or host). Chat shell sends:

   `POST /v1/chat/stream`

   ```json
   {
     "agentId": "trafficrules",
     "conversationId": "conv_… | null",
     "sessionId": "sess_… | null",
     "message": "user text"
   }
   ```

2. API Gateway validates JWT, then invokes a **thin Python entry** on AgentCore Runtime (HTTP proxy / Lambda integration that calls `InvokeAgentRuntime` with the token and session header).

3. Runtime builds a Strands `Agent`:

   - `BedrockModel` (model id from env, not hardcoded in UI).
   - MCP client pointed at AgentCore Gateway (tools for this agent).
   - Strands **`S3SessionManager`** (`session_id` + prefix scoped to user + conversation; see §8). **Do not** use `AgentCoreMemorySessionManager` / AgentCore Memory.
   - Optional Knowledge Base retrieve tool.

4. Runtime **streams** Strands events (`stream_async`) and maps them to the **UI event contract** (§9). API Gateway must use a streaming-capable integration (HTTP API + response streaming, or WebSocket if HTTP streaming is too painful). Prefer **SSE** (`text/event-stream`) to the browser.

5. Persistence is `S3SessionManager`’s job: after each message/turn it writes session + messages + agent state to S3. The Runtime also upserts a small **catalog object** (`title`, `updatedAt`, `agentId`) so the history API can list threads via `ListObjectsV2` without parsing every message blob.

If `conversationId` is null, create ids first, return both on the first SSE event so the client can update the URL/query.

---

## 5. Agents: specialists now, host later

### 5.1 Specialist (phase 1)

One AgentCore Runtime **per** specialist (separate containers / aliases). Code lives in `agents/{agentId}/`. Reasons:

- Isolated IAM and tool allow-lists.
- Independent deploys.
- A2A needs a stable runtime URL / ARN per skill.
- Do not share a Strands `session_id` across host and specialists. Each Runtime restores its own agent from S3.

Each specialist:

- Python on AgentCore Runtime.
- Own system prompt and MCP tool subset.
- Own Agent Card at `/.well-known/agent-card.json` (required for A2A later).
- `capabilities.streaming: true`.

### 5.2 Host (phase 2)

Host Runtime (`agents/host/`) does **not** reimplement specialist tools. It discovers specialists (config table: `agentId` → Runtime ARN + Agent Card URL) and delegates with **A2A** (`message/stream` JSON-RPC). AgentCore Runtime proxies JSON-RPC unchanged; session isolation uses `X-Amzn-Bedrock-AgentCore-Runtime-Session-Id`.

Host session vs specialist session:

- Host conversation uses `sessionId = host:{conversationId}`.
- Each A2A hop uses a **child** `session_id` and prefix `…/children/{agentId}/{sessionId}/`, so host and specialist S3 trees never collide.
- UI still has one thread. Events are nested: host → `agent_called` → that agent’s `tool_*` events.

Direct UI hit to `/agents/trafficrules` invokes the specialist Runtime **without** the host. Same specialist code path as A2A server.

---

## 6. Tools: MCP Gateway + Lambda (`tools/`)

**Default:** AgentCore Gateway as a managed MCP server; targets are Lambdas. Implementation lives in `tools/{tool-name}/` — **one directory per tool**, siblings of each other (no extra `lambda/` or `mcp/` wrapper). Each tool folder holds its handler (Python / Node / Go), tests, package script, and `mcp.json` schema. Do **not** colocate tool Lambdas with agent Docker images, and do **not** put history / HTTP APIs here — those live in `backend/`.

When to skip Gateway and put a tool in the Runtime container: tiny, no extra credentials, latency-sensitive helpers. Prefer Gateway for anything with AWS creds, third-party APIs, or independent scaling.

Lambda language by task:

| Use | Language |
| --- | --- |
| Bedrock / boto3 / data glue | Python |
| Light HTTP / JSON transforms | Node.js |
| CPU-heavy parsing, concurrency | Go |

Gateway target = one MCP tool (or a small tool family). IAM on the Gateway role is least-privilege per target.

Tool contract (every Lambda):

- Input: JSON matching the MCP tool schema (strict).
- Output: JSON, bounded size. Truncate large payloads; store blobs in S3 and return a key if needed.
- Timeouts: Gateway ~5 minutes; keep tools well under that. Long jobs: start async work + poll tool, or run the MCP server on Runtime (15 min sync) — only if a tool truly needs it.

---

## 7. Knowledge / RAG

**Default for v1: Amazon Bedrock Knowledge Bases.** Documents live in S3; KB handles chunking, embeddings, and retrieve APIs. Expose retrieve as an MCP tool or Strands retrieve tool, scoped per agent (traffic rules vs company docs).

**S3-as-vector-store** (DIY embeddings in S3 / OpenSearch-less) is only if we need a custom index the KB cannot do. Do not build both in v1.

Per-agent isolation: separate KB or separate metadata filters (`agentId` / `corpus`) so `trafficrules` cannot retrieve `companyInfo` chunks.

---

## 8. Session persistence (S3 + S3SessionManager — no AgentCore Memory, no DynamoDB)

**Decision:** persist conversations with Strands’ **built-in `S3SessionManager`**. Do **not** use AgentCore Memory. Do **not** implement a custom DynamoDB `SessionRepository`.

`FileSessionManager` is local/dev only (AgentCore disk is ephemeral). `S3SessionManager` is the official production backend: restore on construct, persist each message, sync agent state after invoke. Do not hand-roll `agent.messages` into Bedrock.

What it stores (enough to continue later):

- Conversation messages (user, assistant, tool-use, tool-result)
- Agent state (key/value)
- Conversation-manager state (window / summary offsets)

Re-create the agent with the same `session_id` + bucket/prefix and it continues.

### 8.1 Bucket, prefix, session id

**Dedicated sessions bucket** (not the Knowledge Base document bucket). Block public access, default encryption (SSE-S3 or KMS), bucket owner enforced.

```
s3://{SESSIONS_BUCKET}/
  conversations/{userId}/{conversationId}/catalog.json
  conversations/{userId}/{conversationId}/session/{sessionId}/   ← S3SessionManager prefix
  conversations/{userId}/{conversationId}/children/{agentId}/{sessionId}/  ← A2A child (phase 2)
```

```
session_id = {userId}:{agentId}:{conversationId}
```

`userId` is Auth0 `sub`. Host vs specialist never share a `session_id` (see §5.2). IAM: Runtime and `backend/` history `s3:GetObject` / `PutObject` / `ListBucket` **only** under `conversations/{thatUser}/…`. Never list the whole bucket for a user request.

Attach on every invoke:

```python
from strands.session.s3_session_manager import S3SessionManager

session_manager = S3SessionManager(
    session_id=session_id,
    bucket=os.environ["SESSIONS_BUCKET"],
    prefix=f"conversations/{user_id}/{conversation_id}/session/",
)
agent = Agent(
    model=model,
    tools=tools,
    session_manager=session_manager,
    conversation_manager=SlidingWindowConversationManager(...),  # or Summarizing
)
```

`ConversationManager` **prunes what the model sees**. Do not delete S3 message objects to “save space” in a way that breaks Strands restore. Full objects stay for the UI.

`catalog.json` (written by Runtime at start/end of turn) is the list index:

```json
{
  "conversationId": "…",
  "sessionId": "…",
  "agentId": "trafficrules",
  "title": "first user line, truncated",
  "updatedAt": "ISO-8601",
  "status": "active"
}
```

### 8.2 History / resume (`backend/`)

HTTP APIs the SPA calls (list/read/resume conversations, health) live in `backend/`, not in `tools/` and not in `agents/`. Same sessions bucket. Invoked by API Gateway:

- `GET /v1/conversations` — `ListObjectsV2` prefix `conversations/{sub}/` for `catalog.json` keys (or delimiter on `conversationId`). Return titles + ids. Do not download full session trees for the list view.
- `GET /v1/conversations/{id}` — verify the key is under that `sub`, then read Strands session objects and map messages to UI (role, text, tool name/args).
- `POST /v1/conversations/{id}/resume` — returns `{ conversationId, sessionId, agentId }` plus messages for the client to paint. Next `POST /v1/chat/stream` uses those ids; Runtime builds `S3SessionManager` with the same `session_id` and prefix; Strands restores automatically.

No replay of tools. No AgentCore Memory. No DynamoDB for chat.

**Not in v1:** cross-thread long-term memory (user preferences across different conversations).

Local/dev: `FileSessionManager` with a folder that mirrors the same `session_id` scheme.

---

## 9. Streaming event contract (UI)

Browser consumes SSE. Each event is one JSON object after `data: `. Names are stable; extra fields may be added but not renamed.

```ts
type ChatEvent =
  | { type: "session"; conversationId: string; sessionId: string; agentId: string }
  | { type: "token"; text: string; agentId: string }
  | {
      type: "agent_called";
      parentAgentId: "host";
      agentId: string;
      args?: Record<string, unknown>;
    }
  | {
      type: "tool_start";
      agentId: string;
      toolName: string;
      toolUseId: string;
      args: Record<string, unknown>;
    }
  | {
      type: "tool_end";
      agentId: string;
      toolName: string;
      toolUseId: string;
      durationMs: number;
      ok: boolean;
      tokensIn?: number;
      tokensOut?: number;
      tokensTotal?: number;
    }
  | {
      type: "usage";
      agentId: string;
      tokensIn: number;
      tokensOut: number;
      tokensTotal: number;
    }
  | { type: "error"; code: string; message: string }
  | { type: "done"; conversationId: string };
```

Mapping from Strands `stream_async`:

- `data` → `token`
- `current_tool_use` (new `toolUseId`) → `tool_start`
- tool result / cycle complete → `tool_end` (compute `durationMs` in Runtime)
- Bedrock usage on the model response → `usage` (and copy onto `tool_end` as “tokens consumed till that point”)
- Host A2A transfer → `agent_called`, then forward nested `tool_*` / `token` with the **specialist** `agentId`

UI: tool cards show name, args (sanitized), duration, running token total. Host view groups cards under the called agent.

Do not stream secrets, raw AWS creds, or full KB chunks if they contain PII beyond what the user already sees.

---

## 10. Observability

| Layer | Tool | Retention / use |
| --- | --- | --- |
| Logs + metrics | CloudWatch Logs (Runtime, Gateway, Lambdas, API GW) | **7 days** |
| Product traces / evals | **LangSmith** | LangSmith project retention |
| Optional AWS | AgentCore / Bedrock OTEL | Keep if cheap; LangSmith is the human testing UI |

LangSmith (Strands): at Runtime startup, `setup_langsmith_telemetry()` with OTLP to LangSmith (`OTEL_EXPORTER_OTLP_ENDPOINT`, `x-api-key`, `Langsmith-Project`). Traces include agent loops, model calls, tool I/O, token usage.

Log correlation: `conversationId`, `sessionId`, `userId` (hashed if needed), `agentId` on every log line. No prompt dumping of secrets.

---

## 11. Auth and API surface (complete)

Base URL: `https://api.<domain>/v1` (example). All routes: JWT required unless marked.

| Method | Path | Integration | Notes |
| --- | --- | --- | --- |
| POST | `/chat/stream` | AgentCore Runtime invoke (`agents/`) | SSE; `agentId` must match a registry entry the user may use |
| GET | `/conversations` | `backend/` history | Filter by JWT `sub` |
| GET | `/conversations/{id}` | `backend/` history | 404 if wrong user |
| POST | `/conversations/{id}/resume` | `backend/` history | Returns session binding |
| GET | `/health` | `backend/` (optional) | No JWT |

CORS: only the GitHub Pages / custom domain origin. Credentials: bearer header, not cookies, unless we later switch.

Authorization beyond “valid token”: optional allow-list of `agentId`s per user (Auth0 `app_metadata`). Until then, any logged-in user can hit all public demo agents.

---

## 12. Monorepo layout

One repo. **Terraform only** for AWS shape (no CDK). Path rule:

| Folder | Owns | Does not own |
| --- | --- | --- |
| `frontend/` | SPA (Vite/React), Auth0 UI, chat routes | AgentCore images, tools, backend APIs, Terraform |
| `agents/` | All agent runtime code (Strands, prompts, Dockerfiles, Agent Cards) | MCP tools, HTTP APIs, Terraform |
| `tools/` | One folder per MCP tool (`tools/{tool-name}/`, schema + Lambda source) | History/resume, health, other HTTP APIs |
| `backend/` | History, resume, health, and any other HTTP APIs behind API Gateway | Agent loops, MCP tool handlers, Terraform |
| `infra/` | Terraform, AWS CLI scripts, bootstrap/ops helpers | Application source |

```
.
  frontend/                  # this SPA
  agents/
    trafficrules/            # one AgentCore Runtime image
    publicmoney/
    companyInfo/
    host/                    # phase 2
    _shared/                 # optional: SSE mapper, S3SessionManager wiring
  tools/
    challan-extractor/       # MCP Lambda + mcp.json (traffic challan advisor)
    # next-tool/             # add more tools as siblings, not nested under lambda/
  backend/
    history/                 # GET /conversations, GET by id, POST resume
    health/                  # optional GET /health
  infra/
    terraform/
      bootstrap/             # one-time: tf state bucket, GitHub OIDC, deploy roles
      modules/
        api_gateway/
        agentcore_runtime/
        mcp_gateway/
        lambda_tool/
        sessions_bucket/
        knowledge_base/
        observability/       # log groups, 7-day retention
      envs/
        dev/
        prod/
      backends.tf            # S3 state; see §13
    aws/                     # AWS CLI / shell ops (bootstrap leftovers, one-off admin)
      README.md              # when to use vs Terraform
  .github/workflows/
    frontend.yml             # lint, build, deploy GitHub Pages (or custom domain)
    infra.yml
    release.yml
```

Each Runtime under `agents/{agentId}/`: Python, `bedrock-agentcore`, `strands-agents`, LangSmith/OTEL deps, Dockerfile as required by AgentCore. Image goes to **ECR**; Terraform (or the release job) points AgentCore Runtime at the **image digest**, not `latest`.

History/resume and other public HTTP APIs are **backend** (`backend/history/`, `backend/health/`), not tools. MCP tool Lambdas stay under `tools/{tool-name}/`. Gateway wiring (which agent may call which tool) is Terraform in `infra/terraform/`.

---

## 13. CI/CD — Terraform + GitHub Actions

### 13.1 Auth to AWS

**GitHub OIDC → IAM roles.** No long-lived `AWS_ACCESS_KEY_ID` in GitHub. One role per environment (`gha-dev`, `gha-prod`), least privilege, `sub` limited to this repo and protected branches.

Secrets allowed in GitHub: Auth0 domain/client (frontend), LangSmith key (runtime env via SSM/Secrets Manager, not committed). Terraform reads secrets from **SSM / Secrets Manager**, not from `.tfvars` in git.

### 13.2 Terraform state

Remote state in a **bootstrap** S3 bucket (not the conversations bucket, not the KB bucket). Enable versioning and encryption.

Locking: Terraform **S3 native state lock** (`use_lockfile`) so we do not add DynamoDB for Terraform. If the Terraform version we pin cannot do that, a tiny lock table is an infra-only exception — still not used for chat.

Workspaces or folders: **`envs/dev` and `envs/prod`** as separate root modules (clearer than one workspace for two accounts). Same modules, different `backend` keys and `tfvars`.

`terraform plan` on every PR that touches `infra/terraform/`. `terraform apply` only from Actions, never from a laptop for prod. Do not apply from `infra/aws/` CLI scripts in prod.

### 13.3 Two pipelines (do not mix)

**Infra (`infra.yml`)** — “change AWS shape”:

| Event | What |
| --- | --- |
| PR to `main` (paths: `infra/**`) | `fmt` check, `validate`, `plan` (dev) for Terraform under `infra/terraform/`. Post plan on the PR. |
| Merge to `main` | `apply` **dev** automatically. |
| `workflow_dispatch` or merge + GitHub **environment** `prod` (required reviewers) | `plan` then `apply` **prod**. |

Never `apply` prod on push without approval.

**Release (`release.yml`)** — “ship code with the same infra”:

| Event | What |
| --- | --- |
| PR | Lint/test by path: `agents/**` (Python), `tools/**` (Python/Node/Go per tool Lambda), `backend/**` (history/HTTP APIs), `frontend/**` (`tsc` + lint). |
| Push to `main` / version tag | Build → push ECR (runtimes) and Lambda artifacts. Deploy **dev**. |
| Git tag `v*` or manual promote | Deploy **prod** (same GitHub environment gate). |

Release job steps:

1. Build Runtime Docker images from `agents/{agentId}/`; push to ECR; record digest.
2. Zip/package Lambdas from `tools/*/` (MCP tools) and `backend/` (history, health, other HTTP APIs); upload to the artifacts bucket Terraform already created.
3. Update Runtime / Lambda to those artifacts (Terraform `-var` digest/version **or** a documented `infra/aws/` CLI helper if the module is written that way). Prefer Terraform so the next `plan` is not a surprise drift.
4. Smoke: `GET /v1/health` on the env URL.

Frontend job: `cd frontend && npm ci`, `lint`, `build`, deploy Pages (existing `gh-pages` flow or `actions/deploy-pages`). Build-time env: API Gateway URL + Auth0 audience per environment (`VITE_*`). Prod frontend must point at prod API.

### 13.4 Pinning and safety

- Terraform version and providers pinned (`.terraform-version` + lockfile committed).
- `terraform fmt -check` and `tflint` in CI.
- Destroy is **not** in the default workflows. No `terraform destroy` on `main`.
- Path filters so a `frontend/`-only commit does not plan AWS, an `infra/`-only commit does not rebuild images, an `agents/` change does not rebuild tools or backend, a `tools/` change does not rebuild runtimes or backend APIs, and a `backend/` change does not rebuild agent images or MCP tools.

---

## 14. Build phases

**Phase 0 — Auth + empty chat UI**  
Auth0 on the SPA, JWT authorizer on API Gateway, `/agents/:id` routes, ChatShell talking to a mock SSE.

**Phase 0b — Bootstrap CI**  
OIDC role, state bucket under `infra/terraform/`, `infra.yml` plan/apply **dev**, frontend workflow. AWS CLI helpers only in `infra/aws/`.

**Phase 1 — One specialist E2E**  
One Runtime (e.g. `trafficrules`) + Bedrock + `S3SessionManager` + one Gateway Lambda tool + `backend/` history API + CloudWatch 7d + LangSmith.

**Phase 1b — Remaining specialists**  
Clone Runtime, swap prompt/tools/KB. Same UI.

**Phase 2 — Host + A2A**  
Host Runtime, Agent Cards, nested stream events, child sessions.

**Phase 3 — Hardening**  
Per-agent IAM, PII redaction in events, evals in LangSmith, rate limits.

---

## 15. Non-negotiables / pitfalls

- UI never stores AgentCore ARNs or AWS keys.
- `userId` always from JWT `sub`.
- Distinct `sessionId` per agent role (host vs specialist). Do **not** provision AgentCore Memory.
- API Gateway JWT **does** sit in front of AgentCore; that is the intended design.
- Tools via Gateway unless duration/size forces Runtime-hosted MCP.
- Knowledge Bases first; DIY S3 vectors only if KB is insufficient.
- Stream **events** to the UI; do not wait for the full answer to show tools.
- CloudWatch 7 days is ops logs. Chat history and resume state live in S3 via `S3SessionManager`. Keep sessions bucket ≠ KB document bucket.
- Infra is Terraform; deploys are GitHub Actions with OIDC. No AWS keys in git. Prod apply is gated. Runtime images referenced by digest.

---

## 16. Checklist for a coding agent

When implementing, in order:

1. Add `frontend/src/agents` routes and shared ChatShell (no backend required if mock SSE exists).
2. Bootstrap Terraform under `infra/terraform/` (state bucket, GitHub OIDC) + `infra.yml` / `release.yml` / `frontend.yml`. Put one-off AWS CLI in `infra/aws/`.
3. Auth0 SPA + API Gateway JWT authorizer against Auth0 discovery URL + audience.
4. First specialist under `agents/trafficrules/`: Strands + `BedrockModel` + `stream_async` → SSE mapper (§9).
5. `S3SessionManager` with prefix `conversations/{userId}/{conversationId}/session/` plus `catalog.json`.
6. History/resume in `backend/history/`: list/read the same S3 prefix (never another user’s prefix).
7. MCP Gateway + first Lambda tool under `tools/challan-extractor/` (attach only to the traffic challan advisor agent).
8. Bedrock KB retrieve tool with corpus isolation.
9. LangSmith OTEL at Runtime process start; CloudWatch log groups with 7-day retention.
10. Host Runtime in `agents/host/` + A2A + nested events (after specialists work standalone).

If a step conflicts with this spec, update the spec first — do not silently fork the architecture.

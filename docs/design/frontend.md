# Frontend — UI conventions & product pages

UI code lives in `frontend/` (React + TypeScript + Tailwind, Vite). Do not put UI
code anywhere else.

For loading-state conventions (route skeletons, `usePageQuery`, `PageShell`) see
`AGENTS.md` → Conventions. The in-app documentation page (`/docs`) is
data-driven from `frontend/src/content/docs.ts`; keep prose there, not in the
page component.

## Conventions (do)

- React components must always be **scalable and reusable**.
- Use **ES6** syntax for JavaScript/TypeScript.
- If unsure, or you cannot assume safely, **ask the user** first.
- When creating any page or component, do not settle for a vanilla theme — go
  above and beyond with modern, clean colors and polished components. Prebuilt
  Tailwind primitives are allowed.

## Conventions (do not)

- **Do not rewrite an entire code block for a single/minor change** — read the
  context and edit precisely.
- **Do not make unnecessary or unwanted changes** — stick to exactly what was
  asked.

## Theming

- A modern **dark/white theme** that affects all pages, and every UI component
  must support the theme.

## Pages (current)

Sidebar sections (`frontend/src/navigation/sidebarLinks.ts`): Home, Build,
Resources, Marketplace, Labs, Manage, Help.

- **Dashboard** (`/dashboard`) — workspace KPIs (agents, workflows, 30-day
  tokens, AI credits), recent agents, quick actions and recent activity.
- **Chat** (`/chat`) — the end-user surface: pick an agent or workflow, configure
  the run, and stream the plan, tool calls, citations and answer inline.
- **Storage** (`/storage`) — standalone files to attach to agents (10 files,
  30 MB each, 100 MB total).
- **Agent builder** (`/agent-builder`) — a fixed React Flow canvas with permanent
  n8n-style cards (agent centre; input/output; schedule; knowledge, MCP & skills
  on the right). The whole card opens a dialog. A right-hand **Agent** panel with
  **Response/History/Errors** tabs is the run log; the **Live** tab owns the run
  composer. Save writes to DynamoDB; publishing sends it to the library.
- **Workflow builder** (`/workflow-builder`) — React Flow with a left agent
  palette, a centre canvas (Query host + Output + draggable agent cards) and a
  right panel with **Inspect** and **Run** tabs. Graph is deterministic; Swarm
  hands off dynamically.
- **Schedules** (`/scheduled-jobs`) — the read view of every cron schedule on
  your agents and workflows.
- **MCP Builder** (`/mcp-builder`) — a chat-to-code workspace (build chat +
  CodeMirror 6) for generating, diffing and sandbox-testing custom Python MCP
  tools.
- **Traces** (`/traces`) — every run, plus review queues; the only place to add
  a run to a dataset or a queue.
- **Playground** (`/playground`) — replay a trace's LLM call, edit the prompt,
  A/B models and judge the result.
- **Evaluations** (`/evaluations`) — RAG or agent offline evaluations against
  golden datasets.
- **Metrics** (`/metrics`) — run volume, latency, cost, tokens and score averages.
- **Knowledge** (`/knowledge-bases`) — create/list knowledge bases, upload or
  write documents, watch the ingestion activity, browse documents/tags.
- **Agent skills** (`/agent-skills`) — CRUD, marketplace and registry imports for
  strands-format skills.
- **MCP Tools** (`/tools`) — built-in tools and remote MCP server connections
  (OAuth or API key).
- **Agents** (`/agent-store`) — your agents plus the public library; install
  clones a published agent into your workspace.
- **Workflows** (`/workflow-store`) — your saved workflows (private).
- **Vault** (`/vault`) — KMS-encrypted provider keys, tokens and connection
  strings, referenced as `{{vault:name}}`.
- **Guardrails** (`/guardrails`) — the workspace Amazon Bedrock Guardrail and a
  test surface.
- **Platform** (`/platform`) — managed AgentCore/Identity/Registry/Browser/
  Optimization status and the active Bedrock levers.
- **Usage** (`/usage`) — AI credits, 30-day analytics, provider keys and
  resource limits.
- **Docs, Support** (`/docs`, `/support`) — in-app documentation, help and
  security reporting.
- **Admin** (`frontend/src/admin/`) — MCP tester, AI credits, support and
  security inboxes; kept separate from the user UI. Also the public **trace
  share** page (`/trace/:token`) and the public **Architecture** page
  (`/architecture`).

## Navigation labels

Dashboard · Chat · Storage · Agent builder · Workflow builder · Schedules ·
MCP Builder · Traces · Playground · Evaluations · Metrics · Knowledge ·
Agent skills · MCP Tools · Agents · Workflows · Vault · Guardrails · Platform ·
Usage · Docs · Support

Note: **Settings** has no sidebar entry — keep it in the user avatar dropdown
above Logout.

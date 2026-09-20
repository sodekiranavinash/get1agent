# Frontend — UI conventions & product roadmap

UI code lives in `frontend/` (React + TypeScript + Tailwind, Vite). Do not put UI
code anywhere else.

For loading-state conventions (route skeletons, `usePageQuery`, `PageShell`) see
`AGENTS.md` → Conventions.

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

- **Knowledge Bases** — create/list a knowledge base, upload documents, watch the
  ingestion activity timeline, browse documents/tags.
- **Agent Skills** — CRUD for strands-format skills.
- **Agent Builder** — a React Flow canvas (`@xyflow/react`) with no side panel:
  the agent sits in the middle with input on top, output on the bottom, schedule
  on the left, and knowledge / MCP tools / skills stacked down the right. Each
  is an Azure DevOps-style story card with inline
  controls (input/output have small message/instruction textareas) and an
  **Edit** footer that opens a detail dialog with the advanced options (full
  lists, per-MCP tool selection, custom cron). Cards are permanent — no palette,
  no delete, not draggable. A right-hand **Agent** panel with **Response /
  History / Errors** tabs logs config changes and test/save/publish activity.
  LocalStorage autosave, a config dry-run ("Test run"), and publish-to-library
  gated on a successful run.
- **Agents (Store)** — the user's agents plus publicly published agents; install
  clones a public agent into the workspace.
- **Admin** (`frontend/src/admin/`) — MCP tester and integrations; kept separate
  from the user UI.

## Planned pages (roadmap)

These describe the intended product direction; not all exist yet.

1. **Dashboard** — summary of created agents, workflows, token usage, AI credits
   spent, and scheduled workflows (running / already run).
2. **Agent Builder** — create custom agents via prompts: choose model, reasoning
   effort, and default tools to attach.
3. **Workflow Builder** — compose a workflow from existing agents, attach them in
   order or all to a host agent, and view live events + agent execution.
4. **Chat** — select created agents, provide the host agent's system prompt, and
   ask questions in a chat UI; show the same live events as each agent executes
   (A2A protocol).
5. **Scheduler** — pick saved workflows and schedule them to run on their own.
6. **Agent Store** — the user's agents plus publicly published agents; a user can
   add public agents to their list.
7. **Workflow Store** — the user's workflows plus shared workflows with
   explanations of how they work.
8. **Administration** — add your own model keys (OpenRouter for now), see token
   usage and billing info.
9. **Tools** — web search, AI web search, code interpreter, and connecting your
   own MCP tools.
10. **Settings** — user preferences (if supported).

## Navigation labels

Dashboard · Agent Builder · Workflow Builder · Agent Store · Workflow Store ·
Scheduled Jobs · Administration · Tools · Settings

Note: **Settings** has no sidebar entry — keep it in the user avatar dropdown
above Logout.

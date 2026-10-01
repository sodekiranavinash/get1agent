/**
 * In-app documentation content.
 *
 * The whole Documentation page is data-driven from this file: a list of groups,
 * each holding sections, each holding an ordered list of typed blocks. Keep new
 * prose here (not in the page component) so the page stays a thin renderer and
 * the table of contents is derived automatically.
 */

export type DocBlock =
  | { kind: 'paragraph'; text: string }
  | { kind: 'steps'; items: string[] }
  | { kind: 'bullets'; items: string[] }
  | { kind: 'callout'; tone: 'info' | 'tip' | 'warning'; title: string; text: string }
  | { kind: 'code'; language: string; code: string }

export type DocSection = {
  id: string
  title: string
  summary: string
  blocks: DocBlock[]
}

export type DocGroup = {
  id: string
  title: string
  sections: DocSection[]
}

export const DOCS: DocGroup[] = [
  // ---------------------------------------------------------------------------
  // Getting started
  // ---------------------------------------------------------------------------
  {
    id: 'start',
    title: 'Getting started',
    sections: [
      {
        id: 'getting-started',
        title: 'Getting started',
        summary:
          'OneAgent is a workspace for building, running and evaluating AI agents on your own data.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'OneAgent lets you assemble agents and multi-agent workflows from four building blocks: knowledge (retrieval over your documents), tools (web search, code, HTTP and remote MCP servers), skills (reusable instructions) and models. Everything is serverless and per-user, so your data, files and conversations are private to your account.',
          },
          {
            kind: 'steps',
            items: [
              'Create a knowledge base on the Knowledge page and upload documents, or write knowledge directly. Ingestion, chunking and indexing happen automatically.',
              'Upload any supporting files to Storage if you want to attach them to an agent later.',
              'Add provider API keys to the Vault if you want runs billed to your own key, or keep using the platform models.',
              'Build an agent in the Agent builder: pick a model, attach knowledge bases, MCP servers and skills.',
              'Run the agent from Chat, or chain several agents together in the Workflow builder.',
              'Inspect every run on Traces, tune prompts in the Playground, and measure quality in Evaluations.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'The fastest path',
            text: 'Create one knowledge base, build one agent with just a prompt and that knowledge base, then run it from Chat. Add tools, skills and schedules once the basics work.',
          },
        ],
      },
      {
        id: 'concepts',
        title: 'Core concepts',
        summary: 'The shared vocabulary used across every page in the app.',
        blocks: [
          {
            kind: 'bullets',
            items: [
              'Agent: one saved configuration — a system prompt, a model, an answer mode, optional knowledge bases, MCP servers, skills and attached files. Runs stream live in Chat.',
              'Workflow: several saved agents coordinated by a host agent, either as a deterministic graph or a dynamic swarm. Workflows reference agents by id; they never embed them.',
              'Knowledge base: a searchable collection of documents. Hybrid search (semantic + keyword) with small-to-big retrieval returns precise passages plus their surrounding page.',
              'MCP server: a Model Context Protocol tool server. Built-ins are web-search, code-interpreter and http-fetch; remote servers are connected over OAuth or an API key; custom servers are Python tools you build in the MCP Builder.',
              'Skill: a Strands-format markdown document (YAML frontmatter plus a body) that grants an agent reusable instructions and declares which MCP servers it may use.',
              'Conversation: one persisted transcript. Chat and builder runs each create a conversation that can be reopened later from the sidebar or History tab.',
              'Trace: the full Langfuse record of one run — the agent loop, model generations, tool calls, tokens and cost. Traces feed Datasets, Review queues and Metrics.',
              'Vault secret: an encrypted key, token or connection string. Secrets are only ever referenced, never displayed back to the browser.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'How the pieces fit',
            text: 'Knowledge, skills and tools are inputs to an agent. Agents are inputs to workflows. Both produce conversations and traces that you can evaluate, curate and monitor. The Vault feeds credentials into all of them.',
          },
        ],
      },
      {
        id: 'dashboard',
        title: 'Dashboard',
        summary:
          'Your workspace at a glance: agent and workflow counts, 30-day token usage, AI credits and recent activity.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The Dashboard is the landing page after you sign in. It summarises the workspace and offers the fastest routes into the product. Numbers come from real data: agents and workflows from their stores, tokens and runs from Langfuse metrics (30 days), credits from your quota.',
          },
          {
            kind: 'bullets',
            items: [
              'KPI cards: Agents, Workflows (with a graph/swarm breakdown), Tokens over 30 days (with run count) and AI credits remaining.',
              'Your recent agents: click a card to open the Agents library.',
              'Quick actions: New agent, New workflow, Open chat and New schedule.',
              'Runs · last 7 days: a small bar chart of daily run volume.',
              'Recent activity: the latest conversations, linking through to Chat.',
            ],
          },
          {
            kind: 'steps',
            items: [
              'Read the KPI row to see how much of your credit grant is left and how many runs you have made.',
              'Use Create agent in the header, or a Quick actions row, to jump straight into the builder you need.',
              'Click any of your recent agents to open the Agents library, or the Chat link on Recent activity to resume a conversation.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'Empty states point forward',
            text: 'On a brand-new workspace the hero card reads “Set up your workspace”. Follow its Create agent action, or open Quick actions, to begin.',
          },
        ],
      },
      {
        id: 'chat',
        title: 'Chat',
        summary:
          'Run agents and workflows conversationally, with live plans, tool calls, sources and answer modes.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Chat is the end-user surface. Pick a target (any saved agent or workflow), configure the run, and ask a question. The run streams a plan, its steps and tool calls, then the final answer. Agents resume per conversation, so follow-up questions keep context.',
          },
          {
            kind: 'paragraph',
            text: 'The composer is at the bottom of the chat column. It holds the target picker, the model picker, Answer mode and Reasoning effort, a Run settings dialog, and the Auto-approve toggle. An agent chat also shows a ring context meter once a conversation grows large.',
          },
          {
            kind: 'steps',
            items: [
              'Open the target picker and choose an agent (or a workflow, grouped under Workflows). A workflow target shows only the picker and applies Answer mode and Reasoning effort to the host agent.',
              'Optionally open Run settings. For an agent this selects knowledge bases, skills, MCP servers and storage files for this run (seeded from the saved config). For a workflow it selects which of your agents run this time.',
              'Choose a model. Platform models are listed, plus any provider keys you stored in the Vault; selecting a Vault key encodes it as vault:<id>:<model>.',
              'Pick Answer mode (Summarize, Normal or Detailed) and Reasoning effort for this run. These override the agent defaults without changing the saved agent.',
              'Toggle Auto-approve off if you want the agent to ask you a question mid-run, or on to let it assume the best option and state it.',
              'Type a question — or tap a starter question on the welcome screen — and send. Watch the run card move through Planning, sub-query groups and numbered todo steps; each tool call shows its name, arguments, response and citation sources.',
              'Read the final answer, rendered in the agent output format (markdown, pretty JSON or plain text). Below it, the Source carousel lists every source by number; inline [n] badges scroll the matching card into view.',
              'Rate the run with the thumbs under the answer, or open View trace for the Langfuse trace.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Human in the loop',
            text: 'With Auto-approve off, the agent can pause and ask a question in a card with option buttons and a custom answer. Submitting resumes the exact same run — the paused turn is replaced, so there is no duplicate.',
          },
          {
            kind: 'callout',
            tone: 'warning',
            title: 'Context limits',
            text: 'Once a conversation fills the model window (the meter turns full), the composer stops accepting messages. Start a new chat to continue with a clean context.',
          },
          {
            kind: 'bullets',
            items: [
              'The left sidebar lists your conversations (closable with the panel button). New chat resets to a draft until you send the first message.',
              'A conversation has a readable global id in the URL: /chat/conversation/<number>?agent=<name>.',
              'Only the final answer is shown; streamed narration before a tool call is dropped. All sources live in the carousel below the answer.',
            ],
          },
        ],
      },
      {
        id: 'storage',
        title: 'Storage',
        summary:
          'A standalone file area for files you want to attach to agents and skills later — separate from knowledge bases.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Storage holds arbitrary files that are not ingested or indexed. Use it for documents you want an agent to read at run time by attaching them to an agent input, or for files fetched by the HTTP Fetch tool. Bytes live in object storage; the app keeps only metadata.',
          },
          {
            kind: 'steps',
            items: [
              'Drag files onto the dropzone, or click it to browse. Any file type is allowed and each upload shows a progress bar.',
              'Watch the header card fill up: it shows total storage used, the file count and the per-file size cap.',
              'Find the file in “Your files” and use Remove to delete it.',
              'Attach a stored file to an agent by opening the agent input card in the Agent builder and selecting it under “Attach files”.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Limits: 10 files, 30 MB per file and 100 MB total per user.',
              'Storage is deliberately separate from knowledge bases: files here are never chunked, embedded or searchable.',
              'When the file limit is reached the dropzone disables and tells you to remove a file first.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'Storage vs knowledge',
            text: 'Use a knowledge base when you want hybrid search over many documents. Use Storage when you want to hand one specific file to an agent for a single run.',
          },
        ],
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Build
  // ---------------------------------------------------------------------------
  {
    id: 'build',
    title: 'Build',
    sections: [
      {
        id: 'agent-builder',
        title: 'Agent builder',
        summary:
          'Compose one agent from a prompt, model, knowledge, MCP tools, skills and an optional schedule.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The Agent builder is a fixed React Flow canvas. The agent sits in the middle with Input on top, Output on the bottom, Schedule on the left, and Knowledge, MCP servers & tools and Skills stacked down the right. Every card is permanent — equal size, not draggable — and clicking anywhere on it opens a dialog with all of its options.',
          },
          {
            kind: 'steps',
            items: [
              'Open the builder from Dashboard, the Agents library (New agent) or the /agent-builder route.',
              'Click the name at the top left to set the agent name and description. Names are lowercase-hyphen, 1–64 characters and unique per user.',
              'Click the Agent card to set the system prompt, model, reasoning effort and Answer mode (Summarize, Normal or Detailed).',
              'Click the Knowledge card to attach any ready knowledge bases.',
              'Click the MCP servers & tools card to select built-in, remote or custom servers, and choose which tools are enabled per server.',
              'Click the Skills card to attach skills. Selecting a skill automatically adds the MCP servers it declares.',
              'Click the Schedule card to add a cron schedule (frequency, time, day and timezone). It is mirrored into the scheduler registry on save.',
              'Click the Input card to add up to eight starter questions and attach storage files. The Output card configures the output format and instructions.',
              'Press Save. Edits also autosave to a local draft; the small dot on Save means unsaved changes.',
              'Open the right-hand Agent panel, use its Live tab run composer to ask a question, and watch the run timeline. Publish (bottom right) sends the agent to the library.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'The right panel has Response (Live), History and Errors tabs. History lists the persisted runs and links into Chat to reopen one.',
              'Publishing flips visibility to public so anyone in the workspace can find and install a copy; Unpublish reverses it.',
              'Delete permanently removes the agent. Copies others already installed are not affected.',
              'A run performed in the builder always creates a fresh conversation.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'Start minimal',
            text: 'A prompt plus one knowledge base is a complete agent. Add tools and skills only when the model needs them — too many tools can distract planning.',
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Limits',
            text: 'Up to 50 agents per user and 256 KB of configuration per agent.',
          },
        ],
      },
      {
        id: 'workflow-builder',
        title: 'Workflow builder',
        summary:
          'Coordinate several saved agents as a deterministic graph or a dynamic swarm.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'A workflow wires saved agents together. The Query card is the host agent: it owns the workflow system prompt and its own model, and it coordinates in both modes. Agents are added from the left palette by dragging onto the canvas (or clicking), and connected by dragging between their handles.',
          },
          {
            kind: 'bullets',
            items: [
              'Graph mode is deterministic: the host dispatches its brief to the entry agents, agents run along the wired agent-to-agent edges (independent ones in parallel), then a second host pass synthesises the outputs into the final answer.',
              'Swarm mode is dynamic: the host is the swarm entry point and hands off to teammates using an injected handoff tool.',
              'A schedule node can be attached to the Query card’s left side, like an agent schedule.',
            ],
          },
          {
            kind: 'steps',
            items: [
              'Open Workflows in the sidebar (or New workflow on the Dashboard) to start a workflow with just the Query and Output cards.',
              'Click the Query card to set the host system prompt and model. Switch between graph and swarm with the mode control in the header.',
              'Drag agents from the left palette onto the canvas, or click one to add it. Every added agent is connected to the host automatically.',
              'Connect agents to each other by dragging between handles to define the execution order (graph mode).',
              'Use the Inspect tab on the right to select any node. The host exposes its prompt and model; an agent exposes per-node overrides for model, prompt, reasoning, servers and skills.',
              'Click Add schedule in the inspector to attach a cron schedule to the Query card.',
              'Press Save, then open the Run tab and type a question in the run composer. The Run/Stop action lives there — the question is typed per run and never saved.',
              'Watch the WorkflowRunTimeline for per-node status, tool calls and timing. When the answer is ready, use View final answer to open the persisted conversation in Chat — that is where the answer renders.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'How transitions read',
            text: 'In swarm mode an inbound transition reads “Handoff from X”; in graph mode it reads “From X” because it is a batch transition, not a handoff. The graph synthesiser host is never shown as a step.',
          },
          {
            kind: 'callout',
            tone: 'warning',
            title: 'Limits',
            text: 'Up to 50 workflows per user, 10 agents, 100 nodes and 300 edges per workflow, and 256 KB of configuration.',
          },
        ],
      },
      {
        id: 'schedules',
        title: 'Schedules',
        summary:
          'One table of every cron schedule attached to your agents and workflows.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Schedules are created inside the Agent builder or Workflow builder — the Schedules page is the read view. It lists each schedule with the parsed frequency and its timezone, the next and last run, and an active/paused badge. Times are shown in each schedule’s own timezone.',
          },
          {
            kind: 'steps',
            items: [
              'Add a schedule card to an agent, or a schedule node to a workflow, and set the frequency, time, day and timezone.',
              'Save the agent or workflow. The schedule is mirrored into the scheduler registry and appears on the Schedules page.',
              'Open Schedules to review all schedules. Enabled ones are sorted first, soonest to fire, then alphabetically.',
              'Use the actions menu on a row to Edit schedule (opens the builder) or Open in chat.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'The scheduler checks for due schedules every minute and runs the target as the platform service.',
              'Each scheduled run creates a conversation of kind “run”, so it is a readable transcript in Chat.',
              'Cron is parsed timezone-aware, including daylight-saving transitions.',
              'Pausing is done by disabling the schedule in the builder; a schedule with an empty cron is not shown at all.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'Timezone comes from Settings',
            text: 'Your Settings timezone pre-fills schedule configuration, and each schedule stores its own timezone so a scheduled job always fires at the intended local time.',
          },
        ],
      },
      {
        id: 'mcp-builder',
        title: 'MCP Builder',
        summary:
          'Build, generate, diff and test your own Python MCP tools in a chat-to-code workspace.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The MCP Builder is where you create custom tools. It is a chat-to-code workspace, not a form: a build chat on the left and a CodeMirror code panel on the right. The server name, tool name and description are editable fields across the top. Save tool is the page’s single primary action and Test sits beside it.',
          },
          {
            kind: 'paragraph',
            text: 'A tool’s source defines a run(args) function that takes one dictionary and returns a JSON-serializable value. The input and output schemas are JSON Schema. Your code runs in a sandbox, never in the browser.',
          },
          {
            kind: 'code',
            language: 'python',
            code: 'def run(args):\n    # args matches the tool input schema\n    return {"result": args}',
          },
          {
            kind: 'steps',
            items: [
              'Open MCP Builder and give the server and tool a name and a one-sentence description the agent will read to decide when to call it.',
              'Describe what the tool should do in the build chat. The generator replies with a proposal.',
              'Review the change card (+N/-M) — it opens a VS Code-style unified diff between the accepted code and the proposal. Use the single global Accept or Reject pair, or Restore checkpoint to revert to the code before that change.',
              'Use Undo and Redo in the editor header over the accepted code, and switch between the Code and Schema tabs to edit the JSON schemas directly.',
              'Click Test, fill in the argument form built from the input schema, and run the tool to see its result. Test is always available.',
              'Press Save tool. The source is stored as a custom server and appears in the MCP Tools list and in the Agent builder’s tools card.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Limits: 20 servers per user, 20 tools per server, 64 KB of source per tool.',
              'Build-chat history persists in Playground sessions (100 sessions per user, 200 messages per session).',
              'A custom server attaches to an agent as a servers[] entry with source “custom” and the server slug as its id.',
              'Changing a tool’s code does not redeploy anything — it can be tested from the inspector, and the sandbox runs the current source.',
            ],
          },
          {
            kind: 'callout',
            tone: 'warning',
            title: 'No network in the sandbox',
            text: 'Custom tools cannot fetch the web or reach cloud SDKs. If a tool needs remote content, have the agent call HTTP Fetch first, then read the saved file and pass its content to your tool as an argument.',
          },
        ],
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Resources
  // ---------------------------------------------------------------------------
  {
    id: 'resources',
    title: 'Resources',
    sections: [
      {
        id: 'knowledge-bases',
        title: 'Knowledge bases',
        summary:
          'Upload documents or write knowledge, then search it with hybrid retrieval. Attach ready bases to agents.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The Knowledge page is where retrieval starts. You can create a knowledge base by uploading files or by writing knowledge directly. Uploads flow through an ingestion pipeline: extract and chunk, embed, then index. A ready knowledge base can be attached to any agent.',
          },
          {
            kind: 'paragraph',
            text: 'Search is hybrid and always on: a semantic leg over the embedding index and a BM25 keyword leg, fused with Reciprocal Rank Fusion. Results use small-to-big retrieval, so you get the precise matched passage plus its surrounding page context. Reranking is opt-in per query and never runs unless requested.',
          },
          {
            kind: 'steps',
            items: [
              'Click Knowledge base in the header (or Write knowledge directly) to open the create dialog, then pick the Write or Upload tab.',
              'Set the per-knowledge-base embedding model and chunk size/overlap. The page-level defaults only pre-fill this dialog.',
              'Upload files by dragging them onto the dropzone on the Knowledge page. Files are accepted within your remaining allowance.',
              'Watch ingestion in the Activity panel: events move from uploaded to processing to ready. The panel polls adaptively while something is active and stops when idle.',
              'When a row shows Ready, click Manage to see its documents and the options available for that base.',
              'Attach the ready base to an agent from the Agent builder’s Knowledge card, and optionally enable rerank on the knowledge node.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Statuses: Processing, Ready and Failed. A failed document emits a failed event with the reason.',
              'Each row shows its file count against the per-base cap and how recently it changed.',
              'Deleting a knowledge base permanently deletes it and all of its files (a confirmation names the count).',
              'The footer shows the active text and image embedding models, the chunk size and overlap, and that config is per knowledge base.',
              'Tags can be attached to documents and reused to narrow a search.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Limits',
            text: '30 knowledge bases per user, 50 files per knowledge base, and 100 MB of knowledge storage per user. The create button disables at the cap.',
          },
          {
            kind: 'callout',
            tone: 'warning',
            title: 'Stuck processing?',
            text: 'The pipeline retries, and a watchdog fails any document left processing past the threshold. Re-upload the document, or check the Activity panel for the failure event.',
          },
        ],
      },
      {
        id: 'agent-skills',
        title: 'Agent skills',
        summary:
          'Reusable instructions in Strands format, with marketplace and registry discovery and an importer.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'A skill is a markdown document with YAML frontmatter — name, description and allowed-tools — plus a body of instructions. The body is only loaded when the agent decides a skill applies (progressive disclosure), so a workspace can hold many skills without bloating every prompt. The allowed-tools field lists whole MCP servers, not individual tools.',
          },
          {
            kind: 'paragraph',
            text: 'The page has three tabs: All (your skills), Marketplace (the curated One Agent Marketplace) and Skills Registry (the public registry). A kind filter narrows results to Prompt-only or Tool-based skills.',
          },
          {
            kind: 'steps',
            items: [
              'To author your own, create a skill in the editor: set the name, description and allowed MCP servers (the built-ins code-interpreter, web-search and http-fetch are always offered), then write the body — or upload an existing .md file and let the parser fill the fields.',
              'To browse, open the Marketplace or Skills Registry tab, optionally filter by kind, and search.',
              'To import, click Import on a card. An import preview fetches and parses the skill; choose the name and which MCP servers to grant, then confirm.',
              'To import from a repository, use resolve-repo with an owner/repo reference to list the SKILL.md files it contains, then preview and import.',
              'Edit or delete your skills from the All tab. Editing opens the same editor with the frontmatter in separate fields.',
              'Attach skills in the Agent builder’s Skills card. Selecting a skill auto-adds the servers it declares.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Names are lowercase-hyphen, 1–64 characters and unique per user.',
              'Imported registry skills are third-party instructions; the editor shows a prompt-injection warning.',
              'The body is never sent to the model up front — only the skill name and description are injected until the agent activates it.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Limits',
            text: 'Up to 50 skills per user and 100 KB per skill.',
          },
        ],
      },
      {
        id: 'mcp-tools',
        title: 'MCP Tools',
        summary:
          'Built-in tools plus remote MCP server connections over OAuth or an API key.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The MCP Tools page lists the built-in tools that need no setup, then your connected remote servers. Built-ins are Web Search (real-time web results with citations), Code Interpreter (Python in a sandbox) and HTTP Fetch (call a public URL and save the response to Storage, plus list-storage-files and read-storage-file).',
          },
          {
            kind: 'paragraph',
            text: 'Remote (Streamable HTTP) MCP servers are connected from the catalog, which has three tabs: All, One Agent Marketplace and MCP Registry. Auth filters let you show only OAuth or no-sign-in servers.',
          },
          {
            kind: 'steps',
            items: [
              'To connect a server, find it in the catalog and start the connection. For an OAuth server a popup walks you through authorization; the callback completes the connection.',
              'For an API-key server, paste the key when prompted. You may reference a Vault secret instead of a literal token.',
              'Once connected, use the connection card to enable or disable it, manage and toggle its individual tools, refresh its cached schemas, reconnect if needed, or disconnect.',
              'If a connection shows Reconnect, its token was revoked — start the authorization again.',
              'Use the connected servers in an agent by selecting them on the MCP servers & tools card in the Agent builder.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Statuses: Setup, Connected, Reconnect and Error. Disabled connections are dimmed and skipped at run time.',
              'Tool schemas are cached; Refresh re-reads them from the server.',
              'Only remote HTTP servers are listed — stateful stdio servers are not supported.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'Prefer Vault references',
            text: 'Store an API key in the Vault and reference it as a placeholder so rotating the value is picked up live without editing the connection.',
          },
        ],
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Marketplace
  // ---------------------------------------------------------------------------
  {
    id: 'marketplace',
    title: 'Marketplace',
    sections: [
      {
        id: 'agents-library',
        title: 'Agents library',
        summary:
          'Browse your agents and published agents, then install a copy into your workspace.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The Agents page shows both your own agents and agents other people have published. An agent appears as a card with its status, model, knowledge/skill/server counts and install count. Public agents you do not own offer Add to workspace; your own offers Edit.',
          },
          {
            kind: 'steps',
            items: [
              'Use the All, My agents and Public tabs to filter the grid.',
              'Click New agent to create one, or Edit on your own agent to open it in the builder.',
              'On a public agent, click Add to workspace. A copy is created in your workspace and opens in the builder.',
              'To share your own, open it in the builder and publish it. Publishing is ungated and flips visibility to public.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Installing a published agent clones it with source “library” and a forkedFrom reference.',
              'Owner-scoped references (knowledge bases, skills and remote servers) are stripped on install because they are not shareable.',
              'Published copies already installed by others are not affected if you later unpublish or delete yours.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Where publishing lives',
            text: 'You publish and unpublish from the Agent builder header — there is no publish action in the library itself.',
          },
        ],
      },
      {
        id: 'workflows-store',
        title: 'Workflows',
        summary: 'Your saved multi-agent workflows: open, inspect or delete them.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The Workflows page lists your saved workflows as cards showing the mode (graph or swarm), the number of agents and nodes, whether it is scheduled, whether it is verified, and when it last ran.',
          },
          {
            kind: 'steps',
            items: [
              'Click New workflow to start a fresh workflow in the builder.',
              'Click Open on a card to edit it in the Workflow builder.',
              'Use the trash button to delete a workflow. Deleting a workflow never deletes its agents.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Workflows are private for now — there is no public workflow library.',
              'A “scheduled” chip appears on cards that carry a schedule; the Schedules page lists the details.',
            ],
          },
        ],
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Labs
  // ---------------------------------------------------------------------------
  {
    id: 'labs',
    title: 'Labs',
    sections: [
      {
        id: 'traces',
        title: 'Traces',
        summary:
          'Every agent and workflow run, and the only place to add a run to a dataset or a review queue.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Traces is the audit view of your runs. Each row shows the trace name, when it ran, its latency, tags, the input question and three actions. It has two tabs: Traces and Review queues.',
          },
          {
            kind: 'steps',
            items: [
              'Open Traces after running an agent. Use the pagination controls to move through older runs.',
              'Use Dataset on a row to add the run to a dataset (creating one on demand), producing a dataset item that keeps its source trace link.',
              'Use Replay to open the trace in the Playground, where you can edit and re-run one of its model calls.',
              'Use Queue to add the run to a review queue; choose or create the score configs the queue uses.',
              'Switch to the Review queues tab and click Review on a queue to label pending items. Scores are written straight to the trace.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Curation is namespaced per user, so you only ever see your own datasets, queues and score configs.',
              'If trace storage is not configured the page shows a clear empty state instead of failing.',
              'Adding the same trace to the same dataset upserts rather than duplicating.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'The only curation entry point',
            text: 'Datasets and review queues can only be fed from the Traces page — there are no such actions on the chat, builder or evaluations screens.',
          },
        ],
      },
      {
        id: 'playground',
        title: 'Playground',
        summary:
          'Replay a real LLM call, edit the prompt, A/B two models and judge the result.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The Playground replays a generation from a trace. It is opened from a trace row’s Replay action, which loads that trace’s model calls. The original messages and model are lifted into an editable prompt so you can iterate without changing the agent.',
          },
          {
            kind: 'steps',
            items: [
              'On Traces, click Replay on a row to open the Playground with that trace.',
              'Pick which LLM call to work with from the list on the left.',
              'Edit the prompt: change each message’s role, edit its content, add or remove messages. Content may contain {{variable}} placeholders — a variables panel appears and substitutes values before running.',
              'Choose a model, optionally a second model for an A/B comparison, and set temperature and max tokens.',
              'Click Run. The Outputs panel shows the original trace output beside each replay (and side by side when comparing two models), with latency and token counts.',
              'Click Judge to score the replay. Supply an optional reference answer to get a correctness score; relevance and faithfulness scores are always returned.',
              'Optionally name a dataset and click Save case to turn the last user message and the replay output into a dataset case.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'The variables panel is frontend-only — substitution happens before the call is made.',
              'Only chat-completions models are offered here.',
              'Saved cases are created on demand in the named dataset and can be used in Evaluations.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'Tight iteration loop',
            text: 'Replay, adjust one thing, judge, and save the good version as a dataset case — that is the fastest way to improve a prompt that is feeding an evaluation.',
          },
        ],
      },
      {
        id: 'evaluations',
        title: 'Evaluations',
        summary:
          'Run RAG offline evaluations against a golden dataset and compare runs metric by metric.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Evaluations measure quality against a golden dataset. A dataset is a list of cases; each case has a question, an optional expected answer and optional expected sources. A run evaluates cases and scores retrieval and generation separately.',
          },
          {
            kind: 'paragraph',
            text: 'A run can use one of two tasks. The RAG task calls the real knowledge search and a controlled generator, then scores the retrieved contexts and the answer. The agent task re-runs a saved agent end to end and scores the answer and its tool trajectory.',
          },
          {
            kind: 'steps',
            items: [
              'Open the Datasets tab and click New dataset. Add cases by hand or from a trace; a case can carry expected sources and an expected answer.',
              'Open a dataset to see its cases and the runs that used it. Use Add cases to append more.',
              'Click New evaluation (or Run on a dataset) and choose the dataset, the task (RAG or agent) and the knowledge bases or agents to use.',
              'Start the run. It runs in the background; the page polls until it completes. A run stops before its time budget and marks any remaining cases skipped.',
              'Open the finished run to see aggregate metrics and per-case detail, including the retrieved contexts, the generated answer and the judge’s reasoning.',
              'Use the Compare tab to line up two runs and compare their metrics.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Retrieval metrics (when expected sources exist): context recall, context precision, hit rate and MRR.',
              'Generation metrics: faithfulness, context relevance, answer relevance and answer correctness (when an expected answer exists).',
              'Agent-task runs additionally report tool precision, tool recall, tool F1 and the number of tool calls when expected tools are declared.',
              'Ground truth is optional per case — a metric lights up only when its inputs are present.',
              'Limits: 50 datasets, 200 cases per dataset and 20 cases per run.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Explainable scores',
            text: 'The per-case artifact keeps the unsupported claims and passage labels behind each score, so you can see why faithfulness or context relevance scored the way it did.',
          },
        ],
      },
      {
        id: 'metrics',
        title: 'Metrics',
        summary:
          'Seven-day run volume, latency, cost, tokens and score averages for your workspace.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Metrics is a compact analytics view built from your traces. It answers “how much am I running, how fast and how expensive” without opening the full trace list.',
          },
          {
            kind: 'bullets',
            items: [
              'KPI row: Runs (traces), p95 latency, Cost over 7 days and total Tokens, each with a small trend sparkline where one is meaningful.',
              'Daily volume: a bar chart of runs per day for the last seven days.',
              'Daily p95 latency: a bar chart of the 95th-percentile latency per day.',
              'Scores: the average and count of every numeric score, such as run feedback or evaluation metrics.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Needs traces',
            text: 'If analytics are not configured for the environment, the page explains what is missing rather than showing fabricated numbers. Run an agent to generate the first trace.',
          },
        ],
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Manage
  // ---------------------------------------------------------------------------
  {
    id: 'manage',
    title: 'Manage',
    sections: [
      {
        id: 'vault',
        title: 'Vault',
        summary:
          'Store provider keys, tokens and connection strings encrypted at rest, and reference them anywhere.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'The Vault keeps your secrets encrypted with a managed key. The browser never receives the raw value back from list or detail calls — only a masked preview. The one place a value is revealed is the owner-only Reveal action, and nothing is written to logs.',
          },
          {
            kind: 'paragraph',
            text: 'A provider secret can hold several models and a default model, and can be used as an agent’s model (provider-as-model) so runs are billed to your own key. Any stored value can be referenced elsewhere as {{vault:name}} or {{vault:name.field}} and is resolved server-side at use time.',
          },
          {
            kind: 'steps',
            items: [
              'Click Add secret. Give it a reference name and choose a provider (an OpenAI-compatible provider) or Generic for a token or connection string.',
              'For a provider, optionally fetch the provider’s live model list and select the models to offer, then choose a default model.',
              'Paste the value. You can Test an unsaved key from the dialog; saved provider secrets have a Test action on their card.',
              'Use Reveal to show the owner-only plaintext (Hide to close it), and Edit or Delete as needed.',
              'Reference the secret from anywhere using its {{vault:name}} placeholder — MCP API-key connections resolve it live.',
              'To use it as a model, set a provider secret as the agent’s model in the Agent builder, or pick it in the Chat composer (encoded as vault:<id>:<model>).',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'The stats row shows secret count, provider count, how many times values were resolved at run time, and last-used time.',
              'Per-key usage shows run count, tokens and last-used time once a provider key has powered runs.',
              'A Verified or Test-failed badge reflects the last connection test.',
              'Limits: 100 secrets per user; the encrypted payload is capped at 4000 characters, so keep values small.',
            ],
          },
          {
            kind: 'callout',
            tone: 'warning',
            title: 'Owner-blind by design',
            text: 'The API never returns plaintext or ciphertext. If you lose the value, reveal it once and store it somewhere safe — there is no way to reconstruct it from the metadata.',
          },
        ],
      },
      {
        id: 'usage',
        title: 'Usage',
        summary:
          'Live workspace usage: AI credits, 30-day token and cost analytics, provider keys and resource limits.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Usage has two tabs. Overview covers the workspace budget and analytics; Resources covers every per-user limit and the model rate table. Every number is server-derived — nothing is estimated in the browser.',
          },
          {
            kind: 'bullets',
            items: [
              'AI credits card: how many credits of your grant you have spent, how many remain and the equivalent dollar amount, or “unlimited”. Runs on your own Vault provider keys are not counted.',
              'KPI row (30 days): Runs, Tokens, Cost and p95 latency, with trend sparklines.',
              'Provider keys: your Vault secrets with previews, default models, test status and usage; Manage opens the Vault.',
              'Usage by model: cost and token share per model for the last 30 days.',
              'Resources: knowledge bases, storage, stored files, agents, workflows, skills, MCP connections and Vault secrets against their limits.',
              'Model rates: the input and output USD-per-1M-token rates used to price platform usage.',
            ],
          },
          {
            kind: 'steps',
            items: [
              'Open the Overview tab to check your remaining credits before a large batch of runs.',
              'If credits are low, add a provider key in the Vault to keep running on your own account, or ask an admin to grant more.',
              'Switch to Resources to see which limit is closest to being reached; near-limit bars turn amber.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Credits vs provider keys',
            text: 'Platform models draw down your AI credits. A run that uses your own Vault provider key is billed to that provider and is always allowed, even when credits are exhausted.',
          },
        ],
      },
      {
        id: 'settings',
        title: 'Settings',
        summary:
          'Your profile, appearance, timezone and notification preferences.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Settings holds your account-level preferences. Changes are staged locally and written with Save changes; the button is disabled until something changes.',
          },
          {
            kind: 'bullets',
            items: [
              'Profile: your name, your email (managed by single sign-on) and your User ID. Include the User ID when contacting support.',
              'Appearance: choose the Light or Dark theme.',
              'Language & region: your timezone, which is used for schedules and reports.',
              'Notifications: email on workflow failure and credit threshold alerts.',
            ],
          },
          {
            kind: 'steps',
            items: [
              'Open Settings from the account menu.',
              'Edit your full name, pick a theme, choose a timezone and toggle the notifications you want.',
              'Click Save changes. A success toast confirms the update.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'Set the timezone first',
            text: 'Schedules pre-fill from your Settings timezone. Setting it once here makes every new schedule correct by default.',
          },
        ],
      },
    ],
  },

  // ---------------------------------------------------------------------------
  // Help
  // ---------------------------------------------------------------------------
  {
    id: 'help',
    title: 'Help',
    sections: [
      {
        id: 'faq',
        title: 'FAQ',
        summary: 'Short answers to the questions that come up most often.',
        blocks: [
          {
            kind: 'bullets',
            items: [
              'Do I need a Bedrock or OpenAI account? No. Platform models are ready to use via your AI credits. You only add a provider key if you want runs billed to your own account.',
              'Do uploaded files become searchable automatically? Only files added to a knowledge base. Files in Storage are never ingested or indexed.',
              'How do I share an agent? Publish it from the Agent builder so it appears in the public Agents library; others install their own copy.',
              'Can I schedule an agent or workflow? Yes — add a schedule card/node in the builder, then check the Schedules page.',
              'Why did an answer cite a source I did not expect? Answers are grounded in retrieved passages; open the Source carousel to see the exact document and page behind each citation.',
              'How do I use my own API key? Add it to the Vault, then select it as the model in the builder or Chat composer.',
              'Where is a run’s trace? Every answer has a View trace link; the full trace also lives on the Traces page.',
              'How many things can I create? Common limits: 30 knowledge bases, 50 agents, 50 workflows, 50 skills and 100 Vault secrets per user.',
            ],
          },
        ],
      },
      {
        id: 'troubleshooting',
        title: 'Troubleshooting',
        summary: 'What to check when something does not work as expected.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Most issues fall into a few categories. Work through the matching entry below before contacting support, and include the affected resource id and the time it happened.',
          },
          {
            kind: 'bullets',
            items: [
              '“Agent runs are not configured” warning in Chat: the run endpoint is not set for this environment. In a managed workspace this is an operator setting; report it rather than retrying.',
              'A document stays Processing: ingestion retries automatically and a watchdog fails anything stuck past the threshold. Re-upload the document and note its id.',
              'Search returns nothing: confirm the knowledge base is Ready and attached to the agent, and that your query is not restricted by tags that no document carries.',
              'A remote MCP connection shows Reconnect: the token was revoked or expired. Run Reconnect from the connection card.',
              'A custom tool times out or errors: check the Test dialog first. Tools cannot reach the network — use HTTP Fetch and read-storage-file instead.',
              'The Chat composer stops accepting messages and the context meter is full: start a new chat to continue with a fresh context.',
              'Credits are exhausted: add a provider key in the Vault to run on your own account, or ask an admin for more credits.',
              'A workflow run produces no visible answer: open View final answer to read the persisted conversation in Chat. Intermediate agent text is intentionally not streamed.',
            ],
          },
          {
            kind: 'callout',
            tone: 'tip',
            title: 'Check status first',
            text: 'Before filing a report, open the status page from Support to confirm there is no active incident.',
          },
        ],
      },
      {
        id: 'support',
        title: 'Support',
        summary: 'How to reach the team and what to include in your message.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'Support is the hub for help. It links to email support, the security team, the live status page and this documentation.',
          },
          {
            kind: 'steps',
            items: [
              'Open Support from the footer or the sidebar.',
              'Choose a channel: email support for account, billing and product questions; security for vulnerabilities; the status page to check availability first.',
              'In your message, include your User ID (from Settings), the affected resource name or id, and the approximate time of the issue.',
            ],
          },
          {
            kind: 'bullets',
            items: [
              'Paid workspaces get a first response within one business day.',
              'Security reports are triaged around the clock.',
            ],
          },
        ],
      },
      {
        id: 'security',
        title: 'Report a security issue',
        summary: 'How to disclose a vulnerability responsibly and what to expect.',
        blocks: [
          {
            kind: 'paragraph',
            text: 'If you believe you have found a security issue, report it before public disclosure so it can be investigated and fixed. Email the security team with a description, reproduction steps and any supporting material.',
          },
          {
            kind: 'bullets',
            items: [
              'Include the affected URL or feature and the impact you believe it has.',
              'Share a proof of concept or screenshots where possible, rather than live exploitation.',
              'Do not access, modify or delete data that does not belong to you.',
              'In scope: authentication and authorisation flaws, server-side request forgery, injection or sandbox escapes, and cross-tenant access to data.',
              'Out of scope: scanner-only findings without demonstrated impact, missing best-practice headers, and attacks requiring a compromised device or credentials.',
            ],
          },
          {
            kind: 'callout',
            tone: 'info',
            title: 'Safe harbour',
            text: 'Researchers acting in good faith under the policy will not face legal action, provided they give the team a reasonable chance to fix the issue before public disclosure.',
          },
        ],
      },
    ],
  },
]

/** Flat list of every section with its group, used by the table of contents. */
export const DOC_TOC = DOCS.map((group) => ({
  id: group.id,
  title: group.title,
  sections: group.sections.map((section) => ({
    id: section.id,
    title: section.title,
  })),
}))

/** Total number of documented sections, shown in the page header. */
export const DOC_SECTION_COUNT = DOCS.reduce(
  (total, group) => total + group.sections.length,
  0,
)

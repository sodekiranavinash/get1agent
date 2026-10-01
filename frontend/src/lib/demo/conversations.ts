import { DOCS, IDS, daysAgo, hoursAgo } from './shared'

/**
 * Conversations for the chat screen + builder History.
 *
 * `/v1/conversations` returns the sidebar list; `/v1/conversations/{id}` returns
 * `{ conversation, turns }`. Each turn carries the full run event stream so the
 * shared reducer can rebuild the exact plan → todos → tool calls → answer the
 * run produced (that is what the runtime persists in S3).
 *
 * `TurnFromStored` replays these events, so the frames here must be valid
 * `AgentRunEvent` (agent) or `WorkflowRunEvent` (workflow) shapes.
 */

const knowledgeSources = {
  releaseNotes: {
    kind: 'knowledge',
    index: 1,
    title: 'release-notes-2026-q3.pdf',
    subtitle: 'Product documentation · page 2',
    snippet:
      'Q3 2026 · Highlights — streaming search results, opt-in reranking, and the removal of the legacy v1 upload endpoint.',
    documentId: DOCS.releaseNotes.id,
    knowledgeBaseId: IDS.kbProductDocs,
    contentType: 'application/pdf',
    page: 2,
  },
  apiGuide: {
    kind: 'knowledge',
    index: 2,
    title: 'api-integration-guide.pdf',
    subtitle: 'Product documentation · page 14',
    snippet:
      'Migrate uploads: request a presigned URL with POST /v2/documents/presign, PUT the bytes to S3, then call /complete.',
    documentId: DOCS.apiGuide.id,
    knowledgeBaseId: IDS.kbProductDocs,
    contentType: 'application/pdf',
    page: 14,
  },
  architecture: {
    kind: 'knowledge',
    index: 3,
    title: 'architecture-overview.pdf',
    subtitle: 'Product documentation · page 7',
    snippet:
      'The retrieval path fuses a semantic leg (S3 Vectors) with a lexical BM25 leg using Reciprocal Rank Fusion (k=60).',
    documentId: DOCS.architecture.id,
    knowledgeBaseId: IDS.kbProductDocs,
    contentType: 'application/pdf',
    page: 7,
  },
  webRelease: {
    kind: 'web',
    index: 4,
    title: 'Northwind Analytics — Q3 2026 release announcement',
    url: 'https://northwind.example/blog/q3-2026-release',
    snippet:
      'Streaming search results and opt-in reranking are generally available as of 12 September 2026.',
    favicon: '/demo/favicon-northwind.svg',
    image: '/demo/q3-release-card.svg',
  },
  webChangelog: {
    kind: 'web',
    index: 5,
    title: 'Changelog · northwind-analytics',
    url: 'https://northwind.example/changelog',
    snippet: 'v2.14.0 — streaming search, rerank flag, deprecate v1 documents endpoint.',
    favicon: '/demo/favicon-northwind.svg',
  },
}

const researchAnswer = `Three changes landed in the **Q3 2026** release, and two of them affect the REST API.

## What changed
- **Streaming search results** — \`/v2/search\` now streams ranked results as they arrive, which cut p95 latency by roughly 38% in the release notes' benchmarks [1][4].
- **Per-request reranking** — pass \`rerank: true\` to opt into a cross-encoder pass over the hybrid results. It stays off by default, so existing callers are unaffected [1][3].
- **Legacy \`v1\` upload removed** — \`POST /v1/documents\` is gone. The supported path is the presigned flow described in the integration guide [2].

## API impact
| Change | Endpoint | Action |
| --- | --- | --- |
| Streaming results | \`GET /v2/search\` | Set \`Accept: text/event-stream\` |
| Reranking | \`GET /v2/search\` | Add \`rerank=true\` |
| Upload removal | \`POST /v1/documents\` | Migrate to \`/v2/documents/presign\` → \`/complete\` [2] |

The embedding model and chunking defaults are unchanged, so re-indexing is not required. If you rely on the old upload endpoint, the migration is a one-endpoint swap; the integration guide has a worked example [2].

Sources: release notes (p2), integration guide (p14), architecture overview (p7), and the public release announcement.`

const supportAnswer = `To reset a password for a managed user, use the admin console — end users cannot reset a managed password themselves.

1. Open **Admin → Users** and search for the user.
2. Choose **Reset password**; this emails a single-use link that expires in 60 minutes [1].
3. If the user is locked out of SSO, break the identity binding first (**Unlink identity**), then reset [2].

The user must sign in within 60 minutes or the link has to be reissued [1].`

const researchEvents = [
  {
    type: 'run.started',
    runId: 'run_9f3a1c2e',
    agentId: IDS.agentResearch,
    sessionId: '1042-0000000000000000000000000000000',
  },
  {
    type: 'skills',
    skills: [
      { id: IDS.skillSummarise, name: 'summarise-doc' },
      { id: IDS.skillCite, name: 'cite-sources' },
    ],
  },
  {
    type: 'attachments',
    files: [{ id: IDS.storageBoardDeck, fileName: 'q3-board-deck.pdf', chars: 18_420 }],
  },
  { type: 'plan.started' },
  {
    type: 'plan',
    understanding:
      'The user wants a summary of what changed in the Q3 2026 release notes, with the API-relevant changes called out.',
    subQueries: [
      {
        id: 'sq-1',
        query: 'Q3 2026 release notes changes',
        todos: [
          {
            id: '1.1',
            title: 'Search product docs for the Q3 changelog',
            tool: 'search-user-knowledge-bases',
            query: 'Q3 2026 release notes what changed',
          },
          {
            id: '1.2',
            title: 'Cross-check against the public announcement',
            tool: 'web-search',
            query: 'Northwind Analytics Q3 2026 release',
          },
        ],
      },
      {
        id: 'sq-2',
        query: 'Which changes affect the REST API?',
        todos: [
          {
            id: '2.1',
            title: 'Pull the API integration guide for the upload migration',
            tool: 'search-user-knowledge-bases',
            query: 'v1 documents endpoint deprecation presigned upload',
          },
        ],
      },
    ],
  },
  {
    type: 'tool.start',
    name: 'search-user-knowledge-bases',
    toolUseId: 'toolu_01',
    input: {
      query: 'Q3 2026 release notes what changed',
      knowledgeBaseNames: ['product-docs'],
      topK: 8,
      rerank: true,
    },
  },
  {
    type: 'tool.result',
    toolUseId: 'toolu_01',
    status: 'success',
    input: { query: 'Q3 2026 release notes what changed' },
    data: '3 parents returned (release-notes-2026-q3.pdf p2, architecture-overview.pdf p7, api-integration-guide.pdf p14).',
    sources: [knowledgeSources.releaseNotes, knowledgeSources.architecture, knowledgeSources.apiGuide],
  },
  {
    type: 'tool.start',
    name: 'web-search',
    toolUseId: 'toolu_02',
    input: { query: 'Northwind Analytics Q3 2026 release', numResults: 5 },
  },
  {
    type: 'tool.result',
    toolUseId: 'toolu_02',
    status: 'success',
    input: { query: 'Northwind Analytics Q3 2026 release' },
    data: '2 results',
    sources: [knowledgeSources.webRelease, knowledgeSources.webChangelog],
  },
  {
    type: 'tool.start',
    name: 'search-user-knowledge-bases',
    toolUseId: 'toolu_03',
    input: {
      query: 'v1 documents endpoint deprecation presigned upload',
      knowledgeBaseNames: ['product-docs'],
      topK: 5,
    },
  },
  {
    type: 'tool.result',
    toolUseId: 'toolu_03',
    status: 'success',
    input: { query: 'v1 documents endpoint deprecation presigned upload' },
    data: '1 parent returned (api-integration-guide.pdf p14).',
    sources: [knowledgeSources.apiGuide],
  },
  { type: 'text', data: researchAnswer },
  { type: 'trace', traceId: IDS.traceResearch, traceUrl: `/v1/traces/demo.${IDS.traceResearch}` },
  {
    type: 'context',
    usedTokens: 12_480,
    limitTokens: 128_000,
    ratio: 0.0975,
    full: false,
    breakdown: { system: 1_820, tools: 2_140, messages: 8_520 },
  },
  {
    type: 'run.completed',
    stopReason: 'end_turn',
    usage: { inputTokens: 11_240, outputTokens: 1_240, totalTokens: 12_480 },
  },
]

const researchFollowUpEvents = [
  {
    type: 'run.started',
    runId: 'run_2b7d4e11',
    agentId: IDS.agentResearch,
    sessionId: '1042-0000000000000000000000000000000',
  },
  {
    type: 'skills',
    skills: [
      { id: IDS.skillSummarise, name: 'summarise-doc' },
      { id: IDS.skillCite, name: 'cite-sources' },
    ],
  },
  { type: 'plan.started' },
  {
    type: 'plan',
    understanding: 'Follow-up: the user only cares about the REST API surface.',
    subQueries: [
      {
        id: 'sq-1',
        query: 'REST API changes in Q3',
        todos: [
          {
            id: '1.1',
            title: 'Re-read the API integration guide',
            tool: 'search-user-knowledge-bases',
            query: 'REST API v2 changes rerank streaming',
          },
        ],
      },
    ],
  },
  {
    type: 'tool.start',
    name: 'search-user-knowledge-bases',
    toolUseId: 'toolu_11',
    input: {
      query: 'REST API v2 changes rerank streaming',
      knowledgeBaseNames: ['product-docs'],
      topK: 5,
    },
  },
  {
    type: 'tool.result',
    toolUseId: 'toolu_11',
    status: 'success',
    input: { query: 'REST API v2 changes rerank streaming' },
    data: '2 parents returned (release-notes-2026-q3.pdf p2, api-integration-guide.pdf p14).',
    sources: [knowledgeSources.releaseNotes, knowledgeSources.apiGuide],
  },
  {
    type: 'text',
    data: `Only two of the three changes touch the REST API [1]:

- **\`GET /v2/search\`** gained two optional behaviours — \`Accept: text/event-stream\` streams ranked results, and \`rerank=true\` turns on the cross-encoder pass [1].
- **\`POST /v1/documents\`** was removed. Use \`POST /v2/documents/presign\`, upload the bytes, then call \`/complete\` [2].

The latency and reranking defaults are unchanged for callers that send neither flag.`,
  },
  { type: 'trace', traceId: IDS.traceResearch, traceUrl: `/v1/traces/demo.${IDS.traceResearch}` },
  {
    type: 'run.completed',
    stopReason: 'end_turn',
    usage: { inputTokens: 9_820, outputTokens: 620, totalTokens: 10_440 },
  },
]

const supportEvents = [
  {
    type: 'run.started',
    runId: 'run_3d7e9b1f',
    agentId: IDS.agentSupport,
    sessionId: '1041-0000000000000000000000000000000',
  },
  { type: 'skills', skills: [{ id: IDS.skillTriage, name: 'ticket-triage' }] },
  { type: 'plan.started' },
  {
    type: 'plan',
    understanding: 'The user wants the steps to reset a managed user password.',
    subQueries: [
      {
        id: 'sq-1',
        query: 'Managed user password reset',
        todos: [
          {
            id: '1.1',
            title: 'Look up the password reset playbook',
            tool: 'search-user-knowledge-bases',
            query: 'reset password managed user',
          },
        ],
      },
    ],
  },
  {
    type: 'tool.start',
    name: 'search-user-knowledge-bases',
    toolUseId: 'toolu_21',
    input: {
      query: 'reset password managed user',
      knowledgeBaseNames: ['support-handbook'],
      topK: 5,
    },
  },
  {
    type: 'tool.result',
    toolUseId: 'toolu_21',
    status: 'success',
    input: { query: 'reset password managed user' },
    data: '2 parents returned (support-playbook.md, escalation-policy.pdf).',
    sources: [
      {
        kind: 'knowledge',
        index: 1,
        title: 'support-playbook.md',
        subtitle: 'Support handbook · section 4.2',
        snippet:
          'Managed users reset from Admin → Users → Reset password. The emailed link expires after 60 minutes.',
        documentId: 'd0c0a1b2-1001-4001-8001-000000001001',
        knowledgeBaseId: IDS.kbSupportHandbook,
        contentType: 'text/markdown',
      },
      {
        kind: 'knowledge',
        index: 2,
        title: 'escalation-policy.pdf',
        subtitle: 'Support handbook · page 3',
        snippet:
          'If a user is locked out of SSO, unlink the identity binding before resetting the password.',
        documentId: 'd0c0a1b2-1002-4002-8002-000000001002',
        knowledgeBaseId: IDS.kbSupportHandbook,
        contentType: 'application/pdf',
        page: 3,
      },
    ],
  },
  { type: 'text', data: supportAnswer },
  { type: 'trace', traceId: IDS.traceSupport, traceUrl: `/v1/traces/demo.${IDS.traceSupport}` },
  {
    type: 'context',
    usedTokens: 6_120,
    limitTokens: 128_000,
    ratio: 0.0478,
    full: false,
    breakdown: { system: 1_240, tools: 1_180, messages: 3_700 },
  },
  {
    type: 'run.completed',
    stopReason: 'end_turn',
    usage: { inputTokens: 5_640, outputTokens: 480, totalTokens: 6_120 },
  },
]

const workflowAnswer = `Both analysts came back with material the other did not have.

**Adoption.** Streaming search is the headline change, and the release announcement says it is already enabled on the public API [1].

**Numbers.** The analyst's spreadsheet shows p95 latency falling from 1.9s to 1.2s across the August rollout window — a 37% improvement, not the 38% quoted in the notes (the notes round up) [2].

**Recommendation.** Keep reranking off by default and enable it per-call once you have measured your own latency budget. The upload endpoint migration is the only breaking change.`

const workflowEvents = [
  {
    type: 'run.started',
    runId: 'run_c1a2b3d4',
    workflowId: IDS.workflowResearchTeam,
    sessionId: '1040-0000000000000000000000000000000',
    mode: 'graph',
  },
  {
    type: 'workflow',
    mode: 'graph',
    nodes: [
      {
        id: 'input',
        name: 'Host',
        agentName: 'Host',
        model: 'glm-5.3-flash',
        role: 'host',
        stage: 'dispatch',
      },
      {
        id: 'research-assistant',
        name: 'research-assistant',
        agentName: 'research-assistant',
        model: 'deepseek-v4-flash-vision-exp',
        role: 'agent',
      },
      {
        id: 'data-analyst',
        name: 'data-analyst',
        agentName: 'data-analyst',
        model: 'kimi-k2.6',
        role: 'agent',
      },
      {
        id: 'host-synth',
        name: 'Host',
        agentName: 'Host',
        model: 'glm-5.3-flash',
        role: 'host',
        stage: 'synthesis',
      },
    ],
  },
  { type: 'node.started', nodeId: 'input', nodeName: 'Host', agentName: 'Host', at: 0 },
  {
    type: 'node.stream',
    nodeId: 'input',
    event: {
      type: 'tool.start',
      name: 'dispatch_to_agent',
      toolUseId: 'toolu_31',
      input: { to: 'research-assistant', brief: 'Summarise what changed in Q3 2026.' },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'input',
    event: {
      type: 'tool.result',
      toolUseId: 'toolu_31',
      status: 'success',
      data: 'Dispatched to research-assistant and data-analyst.',
    },
  },
  { type: 'node.completed', nodeId: 'input', status: 'completed', at: 1_200 },
  { type: 'node.started', nodeId: 'research-assistant', at: 1_200 },
  {
    type: 'node.stream',
    nodeId: 'research-assistant',
    event: {
      type: 'tool.start',
      name: 'search-user-knowledge-bases',
      toolUseId: 'toolu_32',
      input: { query: 'Q3 2026 release notes', knowledgeBaseNames: ['product-docs'], topK: 8 },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'research-assistant',
    event: {
      type: 'tool.result',
      toolUseId: 'toolu_32',
      status: 'success',
      data: 'release-notes-2026-q3.pdf p2',
      sources: [knowledgeSources.releaseNotes],
    },
  },
  { type: 'node.completed', nodeId: 'research-assistant', status: 'completed', at: 6_400 },
  { type: 'node.started', nodeId: 'data-analyst', at: 6_400 },
  {
    type: 'node.stream',
    nodeId: 'data-analyst',
    event: {
      type: 'tool.start',
      name: 'code-interpreter',
      toolUseId: 'toolu_33',
      input: {
        code:
          "import pandas as pd\nlat = pd.read_csv('latency_aug.csv')\nprint(lat.p95_ms.iloc[0], '->', lat.p95_ms.iloc[-1])",
      },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'data-analyst',
    event: {
      type: 'tool.result',
      toolUseId: 'toolu_33',
      status: 'success',
      data: '1900 -> 1200  (-36.8%)',
    },
  },
  { type: 'node.completed', nodeId: 'data-analyst', status: 'completed', at: 11_900 },
  { type: 'node.started', nodeId: 'host-synth', nodeName: 'Host', agentName: 'Host', at: 11_900 },
  {
    type: 'node.stream',
    nodeId: 'host-synth',
    event: { type: 'text', data: workflowAnswer },
  },
  { type: 'node.completed', nodeId: 'host-synth', status: 'completed', at: 14_300 },
  { type: 'trace', traceId: IDS.traceWorkflow, traceUrl: `/v1/traces/demo.${IDS.traceWorkflow}` },
  {
    type: 'run.completed',
    answer: workflowAnswer,
    usage: { inputTokens: 18_940, outputTokens: 1_880, totalTokens: 20_820 },
  },
]

const contractEvents = [
  {
    type: 'run.started',
    runId: 'run_7a6b5c4d',
    agentId: IDS.agentContract,
    sessionId: '1039-0000000000000000000000000000000',
  },
  {
    type: 'attachments',
    files: [{ id: IDS.storageBoardDeck, fileName: 'q3-board-deck.pdf', chars: 18_420 }],
  },
  { type: 'plan.started' },
  {
    type: 'plan',
    understanding: 'Extract the commercial terms from the attached vendor contract.',
    subQueries: [
      {
        id: 'sq-1',
        query: 'Vendor contract commercial terms',
        todos: [
          {
            id: '1.1',
            title: 'Read the attached contract text',
            tool: 'code-interpreter',
            query: 'extract parties, term, liability cap',
          },
        ],
      },
    ],
  },
  {
    type: 'tool.start',
    name: 'code-interpreter',
    toolUseId: 'toolu_41',
    input: { code: "text = open('vendor_msa.txt').read()\nprint(len(text), 'chars')" },
  },
  {
    type: 'tool.result',
    toolUseId: 'toolu_41',
    status: 'success',
    data: '48210 chars',
  },
  {
    type: 'text',
    data: JSON.stringify(
      {
        parties: ['Northwind Analytics, Inc.', 'Helios Cloud GmbH'],
        effectiveDate: '2026-11-01',
        termMonths: 24,
        autoRenewal: true,
        terminationNoticeDays: 30,
        liabilityCap: '12 months of fees',
        governingLaw: 'Delaware, USA',
        unusualClauses: [
          'Unilateral price increase up to 8% with 60 days notice (clause 7.3).',
          'Exclusivity for the analytics category during the term (clause 11.1).',
        ],
      },
      null,
      2,
    ),
  },
  { type: 'trace', traceId: IDS.traceContract, traceUrl: `/v1/traces/demo.${IDS.traceContract}` },
  {
    type: 'run.completed',
    stopReason: 'end_turn',
    usage: { inputTokens: 7_420, outputTokens: 540, totalTokens: 7_960 },
  },
]

const analystEvents = [
  {
    type: 'run.started',
    runId: 'run_da_2026',
    agentId: IDS.agentDataAnalyst,
    sessionId: 'live-analyst',
  },
  { type: 'skills', skills: [{ id: IDS.skillSql, name: 'sql-analysis' }] },
  { type: 'plan.started' },
  {
    type: 'plan',
    understanding: 'The user wants feature requests charted by month from the attached CSV.',
    subQueries: [
      {
        id: 'sq-1',
        query: 'Feature requests by month',
        todos: [
          {
            id: '1.1',
            title: 'Load the CSV and group by month',
            tool: 'code-interpreter',
            query: 'group feature requests by month',
          },
          {
            id: '1.2',
            title: 'Summarise the trend',
            tool: 'code-interpreter',
            query: 'describe the monthly trend',
          },
        ],
      },
    ],
  },
  {
    type: 'tool.start',
    name: 'code-interpreter',
    toolUseId: 'toolu_da1',
    input: {
      code:
        "import pandas as pd\ndf = pd.read_csv('feature-requests.csv', parse_dates=['created_at'])\nprint(df.groupby(df.created_at.dt.to_period('M')).size())",
    },
  },
  {
    type: 'tool.result',
    toolUseId: 'toolu_da1',
    status: 'success',
    data:
      '2026-01 41\n2026-02 38\n2026-03 96\n2026-04 51\n2026-05 47\n2026-06 58\n2026-07 62\n2026-08 55\n2026-09 88',
  },
  {
    type: 'tool.start',
    name: 'code-interpreter',
    toolUseId: 'toolu_da2',
    input: { code: "print(df[df.created_at.dt.month == 3].category.value_counts().head(3))" },
  },
  {
    type: 'tool.result',
    toolUseId: 'toolu_da2',
    status: 'success',
    data: 'export        44\nintegrations  21\nreporting     12',
  },
  {
    type: 'text',
    data: `Feature requests peaked in **March (96)** and **September (88)**, against a baseline of roughly 50 a month.

- The March spike is almost entirely **export** requests (44 of 96) [1].
- September is broader: **integrations (21)** and **reporting (12)** lead [1].
- Excluding the two spikes, the monthly trend is flat — no steady growth.

Recommendation: triage the March export cluster as one epic; the September integrations group looks like a second, separate epic.`,
  },
  { type: 'trace', traceId: 'c3d4e5f60718293a4b5c6d7e8f90123', traceUrl: '/v1/traces/demo.analyst' },
  {
    type: 'run.completed',
    stopReason: 'end_turn',
    usage: { inputTokens: 14_200, outputTokens: 760, totalTokens: 14_960 },
  },
]

/** Pick the scripted live-run events for an agent by name. */
export function demoAgentRunScript(agentName: string): unknown[] {
  switch (agentName) {
    case 'support-copilot':
      return supportEvents
    case 'contract-reviewer':
      return contractEvents
    case 'data-analyst':
      return analystEvents
    default:
      return researchEvents
  }
}

/** A scripted human-in-the-loop question, one per demo agent that supports it. */
const hitlQuestions: Record<
  string,
  { questionId: string; question: string; options: string[]; allowCustom: boolean }
> = {
  'research-assistant': {
    questionId: 'v1:tool_call:toolu_demo_q1:demo',
    question:
      'Which should I focus on — the changes that affect API callers, or the user-facing highlights?',
    options: ['API changes', 'User-facing highlights', 'Both'],
    allowCustom: true,
  },
  'support-copilot': {
    questionId: 'v1:tool_call:toolu_demo_q2:demo',
    question: 'Is the managed user on the legacy password login, or signing in through SSO?',
    options: ['Legacy password', 'SSO', 'Not sure'],
    allowCustom: true,
  },
}

/**
 * A demo agent run split around a scripted human-in-the-loop question:
 * ``before`` ends on the `question` frame (the card shows), and ``after`` is the
 * continuation streamed once the visitor answers.
 */
export function demoAgentHitlScript(
  agentName: string,
): { before: unknown[]; after: unknown[] } | null {
  const question = hitlQuestions[agentName]
  if (!question) return null
  const events = agentName === 'support-copilot' ? supportEvents : researchEvents
  // Ask after the first tool round, so the timeline already has a step.
  return {
    before: [...events.slice(0, 6), { type: 'question', ...question }],
    after: events.slice(6),
  }
}

const supportSwarmEvents = [
  {
    type: 'run.started',
    runId: 'run_sw_2026',
    workflowId: IDS.workflowSupportTriage,
    sessionId: 'live-swarm',
    mode: 'swarm',
  },
  {
    type: 'workflow',
    mode: 'swarm',
    nodes: [
      { id: 'host', name: 'Host', agentName: 'Host', model: 'mimo-v2.5', role: 'host', stage: 'host' },
      {
        id: 'support-copilot',
        name: 'support-copilot',
        agentName: 'support-copilot',
        model: 'glm-5.3-flash',
        role: 'agent',
      },
    ],
  },
  { type: 'node.started', nodeId: 'host', nodeName: 'Host', agentName: 'Host', at: 0 },
  {
    type: 'node.stream',
    nodeId: 'host',
    event: {
      type: 'tool.start',
      name: 'handoff_to_agent',
      toolUseId: 'toolu_sw1',
      input: { to: 'support-copilot', message: 'Customer says the invoice total looks wrong.' },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'host',
    event: {
      type: 'tool.result',
      toolUseId: 'toolu_sw1',
      status: 'success',
      data: 'Handed off to support-copilot.',
    },
  },
  { type: 'node.handoff', from: ['host'], to: ['support-copilot'], message: 'Billing question' },
  { type: 'node.completed', nodeId: 'host', status: 'completed', at: 900 },
  { type: 'node.started', nodeId: 'support-copilot', at: 900 },
  {
    type: 'node.stream',
    nodeId: 'support-copilot',
    event: {
      type: 'tool.start',
      name: 'search-user-knowledge-bases',
      toolUseId: 'toolu_sw2',
      input: { query: 'invoice total changed proration', knowledgeBaseNames: ['support-handbook'] },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'support-copilot',
    event: {
      type: 'tool.result',
      toolUseId: 'toolu_sw2',
      status: 'success',
      data: 'billing-faqs.pdf',
      sources: [
        {
          kind: 'knowledge',
          index: 1,
          title: 'billing-faqs.pdf',
          subtitle: 'Support handbook · page 1',
          snippet:
            'Plan changes are prorated from the change date, which can make one invoice look higher.',
          documentId: 'd0c0a1b2-1003-4003-8003-000000001003',
          knowledgeBaseId: IDS.kbSupportHandbook,
          contentType: 'application/pdf',
          page: 1,
        },
      ],
    },
  },
  { type: 'node.completed', nodeId: 'support-copilot', status: 'completed', at: 6_100 },
  { type: 'node.started', nodeId: 'host', nodeName: 'Host', agentName: 'Host', at: 6_100 },
  {
    type: 'node.stream',
    nodeId: 'host',
    event: {
      type: 'text',
      data: `The invoice looks higher because the plan change is **prorated from the change date**, so one cycle includes both the old and new amounts [1].

- This is expected, not a billing error [1].
- If the customer changed plans mid-cycle, the next invoice returns to normal.
- For a goodwill credit, escalate to billing with the invoice id.`,
    },
  },
  { type: 'node.completed', nodeId: 'host', status: 'completed', at: 8_400 },
  { type: 'trace', traceId: 'b2c3d4e5f60718293a4b5c6d7e8f9012', traceUrl: '/v1/traces/demo.swarm' },
  {
    type: 'run.completed',
    answer: `The invoice looks higher because the plan change is **prorated from the change date**, so one cycle includes both the old and new amounts [1].`,
    usage: { inputTokens: 7_800, outputTokens: 420, totalTokens: 8_220 },
  },
]

const vendorDiligenceAnswer = `**Recommendation: proceed, but cap the auto-renewal and the price escalator.**

**Vendor.** Helios Cloud is a credible 2-year-old provider with a public security page and no
reported outages in the last four quarters [1].

**Contract.** The MSA auto-renews for 24 months with a 30-day notice window, and clause 7.3
allows a unilateral increase of up to 8% per year [2]. The liability cap is 12 months of fees.

**Cost.** At the quoted $18/seat/month for 140 seats, year one is ~$30.2k; with the escalator
that becomes ~$32.7k in year two (+8%) [3].

**Risks.** The auto-renewal window is the main exposure — calendar the 30-day notice 60 days
early. Everything else is standard.`

const vendorDiligenceEvents = [
  {
    type: 'run.started',
    runId: 'run_vd_2026',
    workflowId: IDS.workflowVendorDiligence,
    sessionId: '1040-0000000000000000000000000000000',
    mode: 'graph',
  },
  {
    type: 'workflow',
    mode: 'graph',
    nodes: [
      { id: 'input', name: 'Host', agentName: 'Host', model: 'glm-5.3-flash', role: 'host', stage: 'dispatch' },
      {
        id: 'research-assistant',
        name: 'research-assistant',
        agentName: 'research-assistant',
        model: 'deepseek-v4-flash-vision-exp',
        role: 'agent',
      },
      {
        id: 'contract-reviewer',
        name: 'contract-reviewer',
        agentName: 'contract-reviewer',
        model: 'gpt-5.6-luna',
        role: 'agent',
      },
      {
        id: 'data-analyst',
        name: 'data-analyst',
        agentName: 'data-analyst',
        model: 'kimi-k2.6',
        role: 'agent',
      },
      { id: 'host-synth', name: 'Host', agentName: 'Host', model: 'glm-5.3-flash', role: 'host', stage: 'synthesis' },
    ],
  },
  { type: 'node.started', nodeId: 'input', nodeName: 'Host', agentName: 'Host', at: 0 },
  {
    type: 'node.stream',
    nodeId: 'input',
    event: {
      type: 'tool.start',
      name: 'dispatch_to_agent',
      toolUseId: 'toolu_vd0',
      input: { to: 'research-assistant', brief: 'Profile Helios Cloud; flag any public incidents.' },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'input',
    event: { type: 'tool.result', toolUseId: 'toolu_vd0', status: 'success', data: 'Dispatched to three agents in order.' },
  },
  { type: 'node.completed', nodeId: 'input', status: 'completed', at: 900 },
  // The host dispatches all three teammates at once.
  { type: 'node.started', nodeId: 'research-assistant', at: 900 },
  { type: 'node.started', nodeId: 'contract-reviewer', at: 900 },
  { type: 'node.started', nodeId: 'data-analyst', at: 900 },
  {
    type: 'node.stream',
    nodeId: 'research-assistant',
    event: {
      type: 'tool.start',
      name: 'search-user-knowledge-bases',
      toolUseId: 'toolu_vd1',
      input: { query: 'Helios Cloud vendor profile security incidents', knowledgeBaseNames: ['product-docs'], topK: 8 },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'research-assistant',
    event: {
      type: 'tool.result',
      toolUseId: 'toolu_vd1',
      status: 'success',
      data: '1 parent returned (architecture-overview.pdf p7).',
      sources: [knowledgeSources.architecture],
    },
  },
  {
    type: 'node.stream',
    nodeId: 'research-assistant',
    event: {
      type: 'tool.start',
      name: 'web-search',
      toolUseId: 'toolu_vd2',
      input: { query: 'Helios Cloud GmbH security page', numResults: 5 },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'research-assistant',
    event: {
      type: 'tool.result',
      toolUseId: 'toolu_vd2',
      status: 'success',
      data: '2 results',
      sources: [knowledgeSources.webChangelog],
    },
  },
  { type: 'node.completed', nodeId: 'research-assistant', status: 'completed', at: 7_200 },
  {
    type: 'node.stream',
    nodeId: 'contract-reviewer',
    event: {
      type: 'tool.start',
      name: 'code-interpreter',
      toolUseId: 'toolu_vd3',
      input: { code: "terms = parse('helios_msa.pdf')\npprint(terms['renewal'], terms['escalator'])" },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'contract-reviewer',
    event: {
      type: 'tool.result',
      toolUseId: 'toolu_vd3',
      status: 'success',
      data: "renewal=24mo notice=30d\nescalator=+8%/yr (clause 7.3)\nliability=12 months fees",
    },
  },
  { type: 'node.completed', nodeId: 'contract-reviewer', status: 'completed', at: 13_400 },
  {
    type: 'node.stream',
    nodeId: 'data-analyst',
    event: {
      type: 'tool.start',
      name: 'code-interpreter',
      toolUseId: 'toolu_vd4',
      input: { code: 'cost(seats=140, price=18, years=2, escalator=0.08)' },
    },
  },
  {
    type: 'node.stream',
    nodeId: 'data-analyst',
    event: { type: 'tool.result', toolUseId: 'toolu_vd4', status: 'success', data: 'y1=$30,240  y2=$32,659' },
  },
  { type: 'node.completed', nodeId: 'data-analyst', status: 'completed', at: 18_900 },
  { type: 'node.started', nodeId: 'host-synth', nodeName: 'Host', agentName: 'Host', at: 18_900 },
  { type: 'node.stream', nodeId: 'host-synth', event: { type: 'text', data: vendorDiligenceAnswer } },
  { type: 'node.completed', nodeId: 'host-synth', status: 'completed', at: 22_100 },
  { type: 'trace', traceId: 'e5f6a7b8c9d0112233445566778899aa', traceUrl: '/v1/traces/demo.vendordiligence' },
  {
    type: 'run.completed',
    answer: vendorDiligenceAnswer,
    usage: { inputTokens: 24_600, outputTokens: 1_540, totalTokens: 26_140 },
  },
]

/** Workflows stream the matching multi-agent script (graph or swarm). */
export function demoWorkflowRunScript(workflowName: string): unknown[] {
  if (workflowName === 'support-triage') return supportSwarmEvents
  if (workflowName === 'vendor-diligence') return vendorDiligenceEvents
  return workflowEvents
}

export const demoConversations = [
  {
    conversationId: IDS.convResearch,
    agentId: IDS.agentResearch,
    agentName: 'research-assistant',
    targetType: 'agent',
    kind: 'chat',
    title: 'What changed in the Q3 release notes?',
    lastPreview: 'Three changes landed in the Q3 2026 release…',
    messageCount: 4,
    runCount: 2,
    lastRunId: 'run_2b7d4e11',
    lastTraceId: IDS.traceResearch,
    lastTraceUrl: `/v1/traces/demo.${IDS.traceResearch}`,
    feedback: null,
    createdAt: daysAgo(1),
    updatedAt: hoursAgo(2),
  },
  {
    conversationId: IDS.convWorkflow,
    agentId: IDS.workflowResearchTeam,
    agentName: 'research-team',
    targetType: 'workflow',
    kind: 'chat',
    title: 'Q3 release impact on latency',
    lastPreview: 'Both analysts came back with material the other did not have…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_c1a2b3d4',
    lastTraceId: IDS.traceWorkflow,
    lastTraceUrl: `/v1/traces/demo.${IDS.traceWorkflow}`,
    feedback: { runId: 'run_c1a2b3d4', value: 'up', categories: ['Helpful'], comment: '', updatedAt: hoursAgo(8) },
    createdAt: daysAgo(2),
    updatedAt: hoursAgo(9),
  },
  {
    conversationId: IDS.convSupport,
    agentId: IDS.agentSupport,
    agentName: 'support-copilot',
    targetType: 'agent',
    kind: 'chat',
    title: 'How do I reset a managed user password?',
    lastPreview: 'Open Admin → Users, then choose Reset password…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_3d7e9b1f',
    lastTraceId: IDS.traceSupport,
    lastTraceUrl: `/v1/traces/demo.${IDS.traceSupport}`,
    feedback: null,
    createdAt: daysAgo(1),
    updatedAt: daysAgo(1),
  },
  {
    conversationId: IDS.convContract,
    agentId: IDS.agentContract,
    agentName: 'contract-reviewer',
    targetType: 'agent',
    kind: 'run',
    title: 'Helios Cloud MSA review',
    lastPreview: '{"parties":["Northwind Analytics, Inc.",…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_7a6b5c4d',
    lastTraceId: IDS.traceContract,
    lastTraceUrl: `/v1/traces/demo.${IDS.traceContract}`,
    feedback: null,
    createdAt: daysAgo(4),
    updatedAt: daysAgo(4),
  },
  {
    conversationId: IDS.convArchitecture,
    agentId: IDS.agentResearch,
    agentName: 'research-assistant',
    targetType: 'agent',
    kind: 'chat',
    title: 'Summarise the architecture overview for a new engineer',
    lastPreview: 'Four layers: ingestion, retrieval, agents and the API…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_a1b2c3d4',
    lastTraceId: 'a1b2c3d4e5f60718293a4b5c6d7e8f91',
    lastTraceUrl: '/v1/traces/demo.a1b2c3d4e5f60718293a4b5c6d7e8f91',
    feedback: null,
    createdAt: daysAgo(2),
    updatedAt: daysAgo(2),
  },
  {
    conversationId: IDS.convSla,
    agentId: IDS.agentSupport,
    agentName: 'support-copilot',
    targetType: 'agent',
    kind: 'chat',
    title: 'What is the SLA for a P1 incident?',
    lastPreview: 'P1 incidents get a 30-minute first response, 24/7…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_d4e5f607',
    lastTraceId: 'd4e5f60718293a4b5c6d7e8f9012345',
    lastTraceUrl: '/v1/traces/demo.d4e5f60718293a4b5c6d7e8f9012345',
    feedback: null,
    createdAt: daysAgo(8),
    updatedAt: daysAgo(8),
  },
  {
    conversationId: IDS.convFeatures,
    agentId: IDS.agentDataAnalyst,
    agentName: 'data-analyst',
    targetType: 'agent',
    kind: 'chat',
    title: 'Chart feature requests by month',
    lastPreview: 'Requests peak in March and September…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_c3d4e5f6',
    lastTraceId: 'c3d4e5f60718293a4b5c6d7e8f90123',
    lastTraceUrl: '/v1/traces/demo.c3d4e5f60718293a4b5c6d7e8f90123',
    feedback: null,
    createdAt: daysAgo(6),
    updatedAt: daysAgo(6),
  },
  {
    conversationId: IDS.convSwarm,
    agentId: IDS.workflowSupportTriage,
    agentName: 'support-triage',
    targetType: 'workflow',
    kind: 'chat',
    title: 'Invoice total looks wrong',
    lastPreview: 'The invoice is higher because the plan change is prorated…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_sw_2026',
    lastTraceId: 'b2c3d4e5f60718293a4b5c6d7e8f9012',
    lastTraceUrl: '/v1/traces/demo.swarm',
    feedback: null,
    createdAt: daysAgo(3),
    updatedAt: hoursAgo(26),
  },
  {
    conversationId: IDS.convVendor,
    agentId: IDS.workflowVendorDiligence,
    agentName: 'vendor-diligence',
    targetType: 'workflow',
    kind: 'chat',
    title: 'Helios Cloud vendor due diligence',
    lastPreview: 'Recommendation: proceed, but cap the auto-renewal and the price escalator…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_vd_2026',
    lastTraceId: 'e5f6a7b8c9d0112233445566778899aa',
    lastTraceUrl: '/v1/traces/demo.vendordiligence',
    feedback: null,
    createdAt: daysAgo(2),
    updatedAt: daysAgo(1),
  },
  {
    conversationId: IDS.convCompare,
    agentId: IDS.agentResearch,
    agentName: 'research-assistant',
    targetType: 'agent',
    kind: 'chat',
    title: 'Compare the Q3 changes to the Q2 release',
    lastPreview: 'Q3 is mostly an API release; Q2 was all retrieval…',
    messageCount: 2,
    runCount: 1,
    lastRunId: 'run_9f3a1c2f',
    lastTraceId: IDS.traceResearch,
    lastTraceUrl: `/v1/traces/demo.${IDS.traceResearch}`,
    feedback: { runId: 'run_9f3a1c2f', value: 'up', categories: ['Accurate'], comment: '', updatedAt: daysAgo(3) },
    createdAt: daysAgo(3),
    updatedAt: daysAgo(3),
  },
]

/**
 * Extra history conversations reuse a scripted transcript (with a different
 * question) so the builder History tab and the chat transcript stay consistent
 * without hand-writing five more event streams.
 */
const historyScripts: Record<
  number,
  { question: string; model: string; traceId: string; events: unknown[]; hours: number }
> = {
  [IDS.convArchitecture]: {
    question: 'Summarise the architecture overview for a new engineer.',
    model: 'deepseek-v4-flash-vision-exp',
    traceId: 'a1b2c3d4e5f60718293a4b5c6d7e8f91',
    events: researchEvents,
    hours: 30,
  },
  [IDS.convSla]: {
    question: 'What is the SLA for a P1 incident?',
    model: 'glm-5.3-flash',
    traceId: 'd4e5f60718293a4b5c6d7e8f9012345',
    events: supportEvents,
    hours: 190,
  },
  [IDS.convFeatures]: {
    question: 'Chart feature requests by month from the attached CSV.',
    model: 'kimi-k2.6',
    traceId: 'c3d4e5f60718293a4b5c6d7e8f90123',
    events: analystEvents,
    hours: 140,
  },
  [IDS.convCompare]: {
    question: 'Compare the Q3 changes to the Q2 release.',
    model: 'deepseek-v4-flash-vision-exp',
    traceId: IDS.traceResearch,
    events: researchFollowUpEvents,
    hours: 70,
  },
}

const turn = (
  runId: string,
  question: string,
  agentId: string,
  agentName: string,
  model: string,
  traceId: string,
  events: unknown[],
  startedHoursAgo: number,
) => ({
  runId,
  question,
  model,
  agentId,
  agentName,
  targetType: 'agent' as const,
  startedAt: hoursAgo(startedHoursAgo),
  completedAt: hoursAgo(Math.max(0, startedHoursAgo - 0.02)),
  status: 'completed',
  traceId,
  traceUrl: `/v1/traces/demo.${traceId}`,
  feedback: null,
  events,
})

export function demoConversationDetail(id: number) {
  const conversation =
    demoConversations.find((entry) => entry.conversationId === id) ?? demoConversations[0]

  let turns: unknown[]
  if (conversation.conversationId === IDS.convResearch) {
    turns = [
      turn(
        'run_9f3a1c2e',
        'What changed in the Q3 release notes?',
        IDS.agentResearch,
        'research-assistant',
        'deepseek-v4-flash-vision-exp',
        IDS.traceResearch,
        researchEvents,
        26,
      ),
      turn(
        'run_2b7d4e11',
        'Which of those changes affect the REST API?',
        IDS.agentResearch,
        'research-assistant',
        'deepseek-v4-flash-vision-exp',
        IDS.traceResearch,
        researchFollowUpEvents,
        2,
      ),
    ]
  } else if (conversation.conversationId === IDS.convSupport) {
    turns = [
      turn(
        'run_3d7e9b1f',
        'How do I reset a managed user password?',
        IDS.agentSupport,
        'support-copilot',
        'glm-5.3-flash',
        IDS.traceSupport,
        supportEvents,
        30,
      ),
    ]
  } else if (conversation.conversationId === IDS.convVendor) {
    turns = [
      {
        runId: 'run_vd_2026',
        question: 'Run a due-diligence review of Helios Cloud before we sign.',
        model: 'glm-5.3-flash',
        agentId: IDS.workflowVendorDiligence,
        agentName: 'vendor-diligence',
        targetType: 'workflow' as const,
        mode: 'graph' as const,
        startedAt: hoursAgo(30),
        completedAt: hoursAgo(29.9),
        status: 'completed',
        traceId: 'e5f6a7b8c9d0112233445566778899aa',
        traceUrl: '/v1/traces/demo.vendordiligence',
        feedback: { runId: 'run_vd_2026', value: 'up', categories: ['Good sources'], comment: '', updatedAt: daysAgo(1) },
        events: vendorDiligenceEvents,
      },
    ]
  } else if (conversation.conversationId === IDS.convSwarm) {
    turns = [
      {
        runId: 'run_sw_2026',
        question: 'The customer says their invoice total looks wrong.',
        model: 'mimo-v2.5',
        agentId: IDS.workflowSupportTriage,
        agentName: 'support-triage',
        targetType: 'workflow' as const,
        mode: 'swarm' as const,
        startedAt: hoursAgo(26),
        completedAt: hoursAgo(25.9),
        status: 'completed',
        traceId: 'b2c3d4e5f60718293a4b5c6d7e8f9012',
        traceUrl: '/v1/traces/demo.swarm',
        feedback: null,
        events: supportSwarmEvents,
      },
    ]
  } else if (historyScripts[conversation.conversationId]) {
    const extra = historyScripts[conversation.conversationId]
    turns = [
      turn(
        conversation.lastRunId ?? `run_${conversation.conversationId}`,
        extra.question,
        conversation.agentId,
        conversation.agentName,
        extra.model,
        extra.traceId,
        extra.events,
        extra.hours,
      ),
    ]
  } else if (conversation.conversationId === IDS.convWorkflow) {
    turns = [
      {
        runId: 'run_c1a2b3d4',
        question: 'How did the Q3 release affect search latency?',
        model: 'glm-5.3-flash',
        agentId: IDS.workflowResearchTeam,
        agentName: 'research-team',
        targetType: 'workflow' as const,
        mode: 'graph' as const,
        startedAt: hoursAgo(9),
        completedAt: hoursAgo(8.9),
        status: 'completed',
        traceId: IDS.traceWorkflow,
        traceUrl: `/v1/traces/demo.${IDS.traceWorkflow}`,
        feedback: { runId: 'run_c1a2b3d4', value: 'up', categories: ['Helpful'], comment: '', updatedAt: hoursAgo(8) },
        events: workflowEvents,
      },
    ]
  } else {
    turns = [
      turn(
        'run_7a6b5c4d',
        'Extract the key commercial terms from this vendor contract.',
        IDS.agentContract,
        'contract-reviewer',
        'gpt-5.6-luna',
        IDS.traceContract,
        contractEvents,
        96,
      ),
    ]
  }

  return { conversation, turns }
}

/** `/v1/agents/{id}/runs` — the builder History tab (same Conversation shape). */
export function demoAgentRuns(agentId: string) {
  return demoConversations.filter((entry) => entry.agentId === agentId)
}

/** Kept for symmetry with the real API's list envelope. */
export const demoConversationList = {
  conversations: demoConversations,
  usage: { conversations: demoConversations.length },
}

import { DOCS, IDS, daysAgo, hoursAgo } from './shared'

/**
 * Labs data: the trace list, per-trace detail (the Playground's LLM calls), the
 * Metrics payload, and the annotation-queue / dataset stores.
 */

/** `/v1/lab/traces` — the trace table (`input`/`output` feed the "Input" column). */
export const demoTraces = [
  {
    id: IDS.traceResearch,
    name: 'agent:research-assistant',
    timestamp: hoursAgo(2),
    sessionId: String(IDS.convResearch),
    latency: 12.4,
    tags: ['agent', 'research-assistant', 'deepseek-v4-flash-vision-exp'],
    input: { question: 'Which of those changes affect the REST API?' },
    output: { answer: 'Only two of the three changes touch the REST API…' },
  },
  {
    id: IDS.traceWorkflow,
    name: 'workflow:research-team',
    timestamp: hoursAgo(9),
    sessionId: String(IDS.convWorkflow),
    latency: 41.8,
    tags: ['workflow', 'research-team', 'graph'],
    input: { question: 'How did the Q3 release affect search latency?' },
    output: { answer: 'Both analysts came back with material the other did not have…' },
  },
  {
    id: IDS.traceSupport,
    name: 'agent:support-copilot',
    timestamp: daysAgo(1),
    sessionId: String(IDS.convSupport),
    latency: 5.1,
    tags: ['agent', 'support-copilot', 'glm-5.3-flash'],
    input: { question: 'How do I reset a managed user password?' },
    output: { answer: 'Open Admin → Users, then choose Reset password…' },
  },
  {
    id: IDS.traceContract,
    name: 'agent:contract-reviewer',
    timestamp: daysAgo(4),
    sessionId: String(IDS.convContract),
    latency: 18.9,
    tags: ['agent', 'contract-reviewer', 'gpt-5.6-luna'],
    input: { question: 'Extract the key commercial terms from this vendor contract.' },
    output: { answer: '{"parties":["Northwind Analytics, Inc.",…' },
  },
  {
    id: 'a1b2c3d4e5f60718293a4b5c6d7e8f91',
    name: 'agent:research-assistant',
    timestamp: daysAgo(2),
    sessionId: '1038',
    latency: 9.7,
    tags: ['agent', 'research-assistant'],
    input: { question: 'Summarise the architecture overview for a new engineer.' },
    output: { answer: 'The platform has four layers: ingestion, retrieval, agents, and the API…' },
  },
  {
    id: 'b2c3d4e5f60718293a4b5c6d7e8f9012',
    name: 'workflow:support-triage',
    timestamp: daysAgo(3),
    sessionId: '1037',
    latency: 22.3,
    tags: ['workflow', 'support-triage', 'swarm'],
    input: { question: 'Customer says their invoice total looks wrong.' },
    output: { answer: 'Routed to billing; the discrepancy is a proration on the August plan change…' },
  },
  {
    id: 'c3d4e5f60718293a4b5c6d7e8f90123',
    name: 'agent:data-analyst',
    timestamp: daysAgo(6),
    sessionId: '1036',
    latency: 15.2,
    tags: ['agent', 'data-analyst'],
    input: { question: 'Chart feature requests by month from the attached CSV.' },
    output: { answer: 'Requests peak in March and September; the March spike is all export-related…' },
  },
  {
    id: 'd4e5f60718293a4b5c6d7e8f9012345',
    name: 'agent:support-copilot',
    timestamp: daysAgo(8),
    sessionId: '1035',
    latency: 4.4,
    tags: ['agent', 'support-copilot'],
    input: { question: 'What is the SLA for a P1 incident?' },
    output: { answer: 'P1 incidents get a 30-minute first response, 24/7…' },
  },
]

const observation = (
  id: string,
  name: string,
  model: string,
  messages: { role: string; content: string }[],
  content: string,
  startOffsetMs: number,
  durationMs: number,
  usage: Record<string, number>,
) => ({
  id,
  type: 'GENERATION',
  name,
  model,
  input: { messages },
  output: { role: 'assistant', content },
  usage,
  startTime: hoursAgo(2),
  endTime: new Date(Date.parse(hoursAgo(2)) + durationMs).toISOString(),
  _offset: startOffsetMs,
})

const researchSystem =
  'You are Northwind Analytics’ research assistant. Answer using the attached knowledge bases first, then the web. Cite every factual claim with [n].'
const researchUser = 'Which of those changes affect the REST API?'

export const demoTraceDetails: Record<string, unknown> = {
  [IDS.traceResearch]: {
    id: IDS.traceResearch,
    name: 'agent:research-assistant',
    input: { question: researchUser },
    output: { answer: 'Only two of the three changes touch the REST API…' },
    latency: 12.4,
    tags: ['agent', 'research-assistant'],
    timestamp: hoursAgo(2),
    observations: [
      observation(
        'obs_research_planner',
        'planner',
        'deepseek-v4-flash-vision-exp',
        [
          { role: 'system', content: 'Return a short JSON plan of sub-queries and tool steps.' },
          {
            role: 'user',
            content:
              'Which of those changes affect the REST API?\n\nHistory:\nuser: What changed in the Q3 release notes?',
          },
        ],
        '{"understanding":"The user only cares about REST API surface changes.","subQueries":[{"id":"sq-1","query":"REST API changes in Q3","todos":[{"id":"1.1","title":"Re-read the API integration guide","tool":"search-user-knowledge-bases","query":"REST API v2 changes rerank streaming"}]}]}',
        0,
        1_840,
        { input: 412, output: 96, total: 508 },
      ),
      observation(
        'obs_research_answer',
        'answer',
        'deepseek-v4-flash-vision-exp',
        [
          { role: 'system', content: researchSystem },
          { role: 'user', content: researchUser },
          {
            role: 'assistant',
            content:
              'Context [1]: release-notes-2026-q3.pdf p2 — streaming search, rerank flag, v1 upload removed.\nContext [2]: api-integration-guide.pdf p14 — presigned upload flow.',
          },
        ],
        'Only two of the three changes touch the REST API [1]:\n\n- **GET /v2/search** gained two optional behaviours — `Accept: text/event-stream` streams ranked results, and `rerank=true` turns on the cross-encoder pass [1].\n- **POST /v1/documents** was removed. Use `POST /v2/documents/presign`, upload the bytes, then call `/complete` [2].',
        1_900,
        4_260,
        { input: 8_940, output: 620, total: 9_560 },
      ),
    ],
  },
}

/** Fallback detail for traces without a bespoke observation set. */
export function demoLabTraceDetail(traceId: string) {
  const explicit = demoTraceDetails[traceId]
  if (explicit) return { trace: explicit }
  const trace = demoTraces.find((entry) => entry.id === traceId) ?? demoTraces[0]
  return {
    trace: {
      id: trace.id,
      name: trace.name,
      input: trace.input,
      output: trace.output,
      latency: trace.latency,
      tags: trace.tags,
      timestamp: trace.timestamp,
      observations: [
        observation(
          `obs_${trace.id.slice(0, 6)}`,
          'answer',
          trace.tags[2] ?? 'deepseek-v4-flash-vision-exp',
          [
            { role: 'system', content: researchSystem },
            {
              role: 'user',
              content: String((trace.input as { question?: string }).question ?? ''),
            },
          ],
          String((trace.output as { answer?: string }).answer ?? ''),
          0,
          Math.round(trace.latency * 1000),
          { input: 6_400, output: 480, total: 6_880 },
        ),
      ],
    },
  }
}

/** `/v1/lab/datasets` — Langfuse-native datasets, namespaced `u_<userId>/<name>`. */
export const demoLabDatasets = {
  datasets: [
    {
      name: 'rag-golden-set',
      fullName: IDS.datasetGolden,
      description: 'Hand-labelled RAG questions over product-docs and support-handbook.',
      createdAt: daysAgo(13),
    },
    {
      name: 'support-faqs',
      fullName: IDS.datasetSupport,
      description: 'The 5 questions the support team gets most often.',
      createdAt: daysAgo(7),
    },
  ],
}

export const demoLabQueues = {
  queues: [
    {
      id: IDS.queueSupport,
      name: 'support-review',
      description: 'Weekly spot-check of support-copilot answers.',
      scoreConfigIds: ['sc_correctness', 'sc_tone'],
    },
  ],
}

export const demoLabScoreConfigs = {
  scoreConfigs: [
    {
      id: 'sc_correctness',
      name: 'correctness',
      dataType: 'NUMERIC',
      categories: [],
      minValue: 0,
      maxValue: 1,
    },
    {
      id: 'sc_tone',
      name: 'tone',
      dataType: 'CATEGORICAL',
      categories: [{ label: 'good' }, { label: 'too formal' }, { label: 'unclear' }],
      minValue: null,
      maxValue: null,
    },
  ],
}

export const demoLabQueueItems = (queueId: string) => ({
  items:
    queueId === IDS.queueSupport
      ? [
          {
            id: 'qi_1',
            objectId: IDS.traceSupport,
            objectType: 'TRACE',
            status: 'PENDING',
          },
          {
            id: 'qi_2',
            objectId: 'd4e5f60718293a4b5c6d7e8f9012345',
            objectType: 'TRACE',
            status: 'PENDING',
          },
        ]
      : [],
})

/**
 * `/v1/lab/metrics` — a 30-day series with a plausible weekly shape. UsagePage
 * requests days=30, MetricsPage days=7; both read the same arrays.
 */
const series = Array.from({ length: 30 }, (_, index) => {
  const day = 29 - index
  const weekday = (index + 1) % 7
  const weekend = weekday === 0 || weekday === 6
  const base = weekend ? 3 : 7
  const count = base + ((index * 3) % 5)
  const p95 = 1_500 + ((index * 137) % 900) - (weekend ? 200 : 0)
  const cost = Number((count * 0.0042).toFixed(4))
  return {
    date: daysAgo(day),
    count,
    p95Latency: p95,
    cost,
    tokens: count * 3_800,
  }
})

export const demoMetrics = {
  configured: true,
  days: 30,
  totals: {
    traces: series.reduce((sum, row) => sum + row.count, 0),
    avgLatency: 620,
    p95Latency: 1_840,
    cost: Number(series.reduce((sum, row) => sum + row.cost, 0).toFixed(4)),
    tokens: series.reduce((sum, row) => sum + (row.tokens ?? 0), 0),
  },
  series,
  models: [
    {
      model: 'deepseek-v4-flash-vision-exp',
      count: 96,
      cost: 1.42,
      tokens: 384_200,
    },
    { model: 'glm-5.3-flash', count: 54, cost: 0.66, tokens: 212_400 },
    { model: 'kimi-k2.6', count: 22, cost: 0.41, tokens: 88_100 },
    { model: 'gpt-5.6-luna', count: 11, cost: 1.86, tokens: 42_600 },
  ],
  scores: [
    { name: 'answer_relevance', avg: 0.86, count: 64 },
    { name: 'faithfulness', avg: 0.79, count: 64 },
    { name: 'context_relevance', avg: 0.83, count: 52 },
    { name: 'tool_precision', avg: 0.91, count: 28 },
  ],
}

/**
 * The metrics payload windowed to the requested number of days, so the Metrics
 * page (7d) and the Usage page (30d) each get a matching series + totals.
 */
export function demoMetricsFor(days: number) {
  const count = Math.max(1, Math.min(Math.round(days) || 30, series.length))
  const window = series.slice(-count)
  return {
    ...demoMetrics,
    days: count,
    totals: {
      traces: window.reduce((sum, row) => sum + row.count, 0),
      avgLatency: 620,
      p95Latency: Math.max(...window.map((row) => row.p95Latency)),
      cost: Number(window.reduce((sum, row) => sum + row.cost, 0).toFixed(4)),
      tokens: window.reduce((sum, row) => sum + (row.tokens ?? 0), 0),
    },
    series: window,
  }
}

/** The knowledge-base document cited by the golden dataset's first case. */
export const goldenCaseSources = [
  { documentId: DOCS.releaseNotes.id, page: 2 },
  { documentId: DOCS.architecture.id, page: 7 },
]

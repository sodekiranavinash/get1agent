/** Evaluation lab: types and query keys for RAG offline evaluation. */

export type ExpectedSource = {
  documentId: string
  page?: number | null
}

export type EvalDataset = {
  datasetId: string
  name: string
  description: string
  caseCount?: number | null
  createdAt: string
  updatedAt: string
}

export type EvalCase = {
  caseId: string
  datasetId: string
  query: string
  expectedOutput: string
  expectedSources: ExpectedSource[]
  sourceTraceId?: string | null
  metadata: Record<string, unknown>
  createdAt: string
}

export type EvalDatasetRun = {
  id: string
  name: string
  description: string
  createdAt?: string
  metadata?: Record<string, unknown>
}

export type EvalRunMode = 'rag' | 'retrieval'
export type EvalTask = 'rag' | 'agent'

export type EvalRun = {
  runId: string
  datasetId: string
  datasetName: string
  knowledgeBaseNames: string[]
  config: { mode: EvalRunMode; rerank?: boolean; task?: EvalTask; agentId?: string }
  status: 'queued' | 'running' | 'completed' | 'failed'
  caseCount: number
  completedCount: number
  failedCount: number
  skippedCount: number
  metrics: Record<string, number>
  error: string
  createdAt: string
  updatedAt: string
  completedAt?: string
}

export type EvalCaseResult = {
  caseId: string
  query: string
  status: 'ok' | 'error' | 'skipped'
  metrics: Record<string, number>
  error: string
  latencyMs: number
  retrievedCount: number
}

export type EvalArtifact = {
  query: string
  answer: string
  expectedOutput: string
  status: string
  error: string
  mode: EvalRunMode
  contexts: Array<{
    documentId?: string
    page?: number | null
    fileName?: string
    text: string
  }>
  metrics: Record<string, number>
  judge: {
    reasoning: string
    relevanceReasoning?: string
    contextReasoning?: string
    correctnessReasoning: string
    claims?: { text: string; supported: boolean }[]
    passages?: { index: number; relevant: boolean }[]
  }
  retrieval: {
    chunks?: Array<Record<string, unknown>>
    sources?: Array<Record<string, unknown>>
    meta?: Record<string, unknown>
  }
}

export const EVALS_QUERY_KEY = 'evals'
export const EVAL_DATASET_QUERY_KEY = 'eval-dataset'
export const EVAL_RUN_QUERY_KEY = 'eval-run'

export function datasetQueryKey(datasetId: string): string {
  return `${EVAL_DATASET_QUERY_KEY}:${datasetId}`
}

export function runQueryKey(runId: string): string {
  return `${EVAL_RUN_QUERY_KEY}:${runId}`
}

export function datasetRunsQueryKey(datasetId: string): string {
  return `eval-dataset-runs:${datasetId}`
}

/** Display order + labels for every metric the runner can produce. */
export const METRIC_LABELS: Record<string, string> = {
  faithfulness: 'Faithfulness',
  answer_relevance: 'Answer relevance',
  context_relevance: 'Context relevance',
  answer_correctness: 'Answer correctness',
  context_recall: 'Context recall',
  context_precision: 'Context precision',
  hit_rate: 'Hit rate',
  mrr: 'MRR',
  tool_precision: 'Tool precision',
  tool_recall: 'Tool recall',
  tool_f1: 'Tool F1',
  tool_calls: 'Tool calls',
}

export const METRIC_ORDER = [
  'faithfulness',
  'answer_relevance',
  'context_relevance',
  'answer_correctness',
  'context_recall',
  'context_precision',
  'hit_rate',
  'mrr',
  'tool_precision',
  'tool_recall',
  'tool_f1',
  'tool_calls',
] as const

export function metricLabel(name: string): string {
  return METRIC_LABELS[name] ?? name.replace(/_/g, ' ')
}

/** Metrics present in an aggregate (skips the `_cases` companion counters). */
export function orderedMetrics(metrics: Record<string, number>): string[] {
  const names = Object.keys(metrics || {}).filter((name) => !name.endsWith('_cases'))
  const ordered: string[] = []
  for (const name of METRIC_ORDER) {
    if (names.includes(name)) ordered.push(name)
  }
  for (const name of names) {
    if (!(METRIC_ORDER as readonly string[]).includes(name)) ordered.push(name)
  }
  return ordered
}

export function formatPercent(value: number | undefined): string {
  if (value === undefined || value === null) return '—'
  return `${Math.round(value * 100)}%`
}

export function formatMode(mode: string): string {
  return mode === 'retrieval' ? 'Retrieval only' : 'RAG (answer + judge)'
}

export function formatTask(task?: string): string {
  return task === 'agent' ? 'Agent' : 'RAG'
}

/** Evaluation lab (Langfuse-native): traces, datasets, annotation queues. */

export type LabTrace = {
  id: string
  name: string
  timestamp: string | null
  sessionId: string | null
  latency: number | null
  tags: string[]
  input: unknown
  output: unknown
}

export type LabDataset = {
  name: string
  fullName: string
  description: string
  createdAt?: string
}

export type LabQueue = {
  id: string
  name: string
  description: string
  scoreConfigIds: string[]
}

export type LabScoreConfig = {
  id: string
  name: string
  dataType: string
  categories?: Array<{ label: string }>
  minValue?: number | null
  maxValue?: number | null
}

export type LabQueueItem = {
  id: string
  objectId: string
  objectType: string
  status: string
}

export type LabTraceDetail = {
  id?: string
  name?: string
  input?: unknown
  output?: unknown
  latency?: number | null
  tags?: string[]
  timestamp?: string | null
}

export const LAB_TRACES_QUERY_KEY = 'lab-traces'
export const LAB_DATASETS_QUERY_KEY = 'lab-datasets'
export const LAB_QUEUES_QUERY_KEY = 'lab-queues'
export const LAB_SCORE_CONFIGS_QUERY_KEY = 'lab-score-configs'

function fromObject(value: unknown, keys: string[]): string {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    const record = value as Record<string, unknown>
    for (const key of keys) {
      const candidate = record[key]
      if (typeof candidate === 'string' && candidate.trim()) return candidate.trim()
    }
  }
  return ''
}

/** Best-effort readable text from a trace's input/output blob. */
export function traceText(value: unknown, keys: string[]): string {
  if (typeof value === 'string') return value.trim()
  const nested = fromObject(value, keys)
  if (nested) return nested
  if (value === null || value === undefined) return ''
  try {
    return JSON.stringify(value)
  } catch {
    return ''
  }
}

export function traceQuestion(
  trace: { input?: unknown } | null | undefined,
): string {
  if (!trace) return ''
  return traceText(trace.input, ['question', 'input', 'query', 'text', 'message'])
}

export function traceAnswer(
  trace: { output?: unknown } | null | undefined,
): string {
  if (!trace) return ''
  return traceText(trace.output, ['answer', 'output', 'text', 'content'])
}

export function formatLatency(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return '—'
  if (seconds < 1) return `${Math.round(seconds * 1000)} ms`
  return `${seconds.toFixed(2)} s`
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return '—'
  try {
    return new Date(iso).toLocaleString()
  } catch {
    return iso
  }
}

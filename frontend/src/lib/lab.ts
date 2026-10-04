/** Evaluation lab (AWS-native): traces, datasets, annotation queues. */

export type LabTrace = {
  id: string
  traceId?: string
  name: string
  timestamp: string | null
  sessionId: string | null
  conversationId?: string | number | null
  agentId?: string | null
  agentName?: string | null
  model?: string | null
  status?: string
  level?: string
  latency: number | null
  latencyMs?: number | null
  tags: string[]
  input: unknown
  output: unknown
  usage?: Record<string, number | null>
  costMicroUsd?: number
  observationCount?: number
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

export type LabTraceDetail = LabTrace & {
  startedAt?: string | null
  endedAt?: string | null
  provider?: string | null
  statusMessage?: string | null
  observations?: TraceObservation[]
  /** Present when the trace predates the store and only X-Ray had a tree. */
  xray?: { traceId: string; durationMs: number | null; spans: unknown[] } | null
}

/** The observation types the runtime emits (a Langfuse-style trace tree). */
export type TraceObservationType =
  | 'GENERATION'
  | 'TOOL'
  | 'EVENT'
  | 'SPAN'
  | 'RETRIEVER'

export type TraceObservation = {
  id: string
  parentObservationId: string | null
  type: TraceObservationType
  name: string
  model?: string | null
  /** Epoch milliseconds. */
  startTime?: number | null
  endTime?: number | null
  durationMs?: number | null
  level?: string
  statusMessage?: string | null
  input?: unknown
  output?: unknown
  usage?: Record<string, number | null> | null
  metadata?: Record<string, unknown>
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

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return '—'
  if (ms < 1) return '<1 ms'
  if (ms < 1000) return `${Math.round(ms)} ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(2)} s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${Math.round(seconds % 60)}s`
}

export function usageTotals(
  usage?: Record<string, number | null> | null,
): { input: number; output: number; total: number } {
  const input = Number(usage?.inputTokens ?? 0)
  const output = Number(usage?.outputTokens ?? 0)
  const total = Number(usage?.totalTokens ?? input + output)
  return { input, output, total }
}

export function formatTokens(count: number): string {
  if (!count) return '0'
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 10_000) return `${Math.round(count / 1000)}k`
  return count.toLocaleString()
}

export function formatCostUsd(microUsd: number | null | undefined): string | null {
  if (!microUsd) return null
  const usd = microUsd / 1_000_000
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

/** Visual identity for each observation type (colour + short label). */
export const OBSERVATION_META: Record<
  string,
  { label: string; text: string; dot: string }
> = {
  GENERATION: { label: 'Generation', text: 'text-violet', dot: 'bg-violet' },
  TOOL: { label: 'Tool', text: 'text-teal', dot: 'bg-teal' },
  EVENT: { label: 'Event', text: 'text-warning', dot: 'bg-warning' },
  RETRIEVER: { label: 'Retriever', text: 'text-accent', dot: 'bg-accent' },
  SPAN: { label: 'Span', text: 'text-muted', dot: 'bg-muted' },
}

export function observationMeta(type: string | undefined) {
  return OBSERVATION_META[String(type || 'SPAN').toUpperCase()] ?? OBSERVATION_META.SPAN
}

/** Friendly labels for the app's internal span attribute keys. */
const KEY_LABELS: Record<string, string> = {
  trace_name: 'Trace',
  session_id: 'Session',
  user_id: 'User',
  input: 'Input',
  output: 'Output',
  metadata: 'Metadata',
  model: 'Model',
  provider: 'Provider',
  agentId: 'Agent ID',
  agentName: 'Agent',
  runId: 'Run',
  conversationId: 'Conversation',
}

/**
 * Turn an internal attribute key (`get1agent.trace_name`, `agentId`) into a
 * human label ("Trace", "Agent ID"). Users never see the raw key.
 */
export function humanizeKey(key: string): string {
  const raw = String(key || '').replace(/^get1agent\./, '')
  if (KEY_LABELS[raw]) return KEY_LABELS[raw]
  return raw
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_.]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
    .trim()
}

/** Parse a JSON-looking string, otherwise return the value unchanged. */
export function parseMaybeJson(value: unknown): unknown {
  if (typeof value !== 'string') return value
  const text = value.trim()
  if (!text || !/^[[{]/.test(text)) return value
  try {
    return JSON.parse(text)
  } catch {
    return value
  }
}

export type MessagePart = { role: string; content: string }

/** Extract a chat message list from `{messages:[…]}` / `[{role,content}]`. */
export function extractMessages(value: unknown): MessagePart[] | null {
  const parsed = parseMaybeJson(value)
  let list: unknown = parsed
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const record = parsed as Record<string, unknown>
    if (Array.isArray(record.messages)) list = record.messages
    else if (typeof record.role === 'string') list = [record]
  }
  if (!Array.isArray(list)) return null
  const messages: MessagePart[] = []
  for (const entry of list) {
    if (!entry || typeof entry !== 'object') return null
    const record = entry as Record<string, unknown>
    const role = typeof record.role === 'string' ? record.role : 'user'
    let content = record.content
    if (typeof content !== 'string') {
      content = content == null ? '' : safeStringify(content)
    }
    messages.push({ role, content: String(content) })
  }
  return messages.length ? messages : null
}

export function safeStringify(value: unknown): string {
  if (value == null) return ''
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

export function isPlainObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

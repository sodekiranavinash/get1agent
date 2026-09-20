import type { AgentOutputFormat } from './agents'
import type { AgentSource, AgentUsage, RunContext } from './agentRun'

/** A single tool invocation inside an assistant turn. */
export type ChatToolStatus = 'running' | 'success' | 'error'

export type ChatToolCall = {
  id: string
  name: string
  status: ChatToolStatus
  /** The invocation arguments as JSON text, streamed while the tool runs. */
  input?: string
  /** Streamed/returned tool output, rendered as monospace text. */
  output?: string
  /** Citation sources extracted from the tool result. */
  sources?: ChatSource[]
}

/** A citation source (a web page or a knowledge-base document/page). */
export type ChatSource = AgentSource & { id: string }

/** The lifecycle of one plan step. */
export type ChatTodoStatus = 'pending' | 'active' | 'done' | 'error'

export type ChatPlanTodo = {
  id: string
  title: string
  /** Tool the planner assigned to this step (best effort). */
  tool?: string
  /** Query the planner suggested for that tool. */
  query?: string
  status: ChatTodoStatus
  /** Tool invocations grouped under this step. */
  tools: ChatToolCall[]
}

/** One sub-query, with its own todo list. */
export type ChatSubQuery = {
  id: string
  query: string
  todos: ChatPlanTodo[]
}

/** The model's plan for a turn: understanding and sub-queries (each with todos). */
export type ChatPlan = {
  understanding: string
  subQueries: ChatSubQuery[]
}

export type ChatTurnStatus = 'streaming' | 'done' | 'error' | 'stopped'

/** One user question plus the assistant's streamed run and final answer. */
export type ChatTurn = {
  id: string
  question: string
  answer: string
  tools: ChatToolCall[]
  /** Citation sources collected across the turn's tool calls. */
  sources: ChatSource[]
  plan: ChatPlan | null
  /** True while the planner is working, before the plan arrives. */
  planning: boolean
  status: ChatTurnStatus
  error?: string
  usage?: AgentUsage
  /** Context-window fill for the conversation after this turn. */
  context?: RunContext
  outputFormat: AgentOutputFormat
  agentId: string
  agentName: string
  model: string
  at: string
  startedAt: number
  endedAt?: number
}

export function formatUsage(usage?: AgentUsage): string | null {
  if (!usage) return null
  const total =
    usage.totalTokens ?? (Number(usage.inputTokens ?? 0) + Number(usage.outputTokens ?? 0))
  if (!total) return null
  return `${total.toLocaleString()} tokens`
}

export function formatDuration(startedAt: number, endedAt?: number): string | null {
  if (!endedAt) return null
  const ms = Math.max(0, endedAt - startedAt)
  if (ms < 1000) return `${ms}ms`
  const seconds = ms / 1000
  if (seconds < 60) return `${seconds.toFixed(1)}s`
  const minutes = Math.floor(seconds / 60)
  return `${minutes}m ${Math.round(seconds % 60)}s`
}

/** A compact, human-readable preview of any tool stream payload. */
export function stringifyToolData(data: unknown): string {
  if (data == null) return ''
  if (typeof data === 'string') return data
  try {
    return JSON.stringify(data)
  } catch {
    return String(data)
  }
}

/** Pretty-print a tool invocation payload for the UI. */
export function formatToolInput(input: unknown): string {
  if (input == null) return ''
  if (typeof input === 'string') {
    try {
      return JSON.stringify(JSON.parse(input), null, 2)
    } catch {
      return input
    }
  }
  try {
    return JSON.stringify(input, null, 2)
  } catch {
    return String(input)
  }
}

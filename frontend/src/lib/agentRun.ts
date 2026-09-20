/**
 * Streaming client for the AgentCore runtime proxy (Function URL).
 *
 * The proxy forwards the Auth0 token to AgentCore, which validates it; the
 * runtime streams normalized SSE frames. Configure `VITE_AGENT_RUN_URL` with
 * the proxy's Function URL (prod) or the local worker URL (dev).
 */

export type AgentUsage = Record<string, number | null>

/** Context-window fill for the conversation, reported by the runtime. */
export type ContextBreakdown = {
  /** System prompt tokens. */
  system: number
  /** Tool/function schema tokens. */
  tools: number
  /** Conversation history tokens. */
  messages: number
}

export type RunContext = {
  usedTokens: number
  limitTokens: number
  /** usedTokens / limitTokens (0–1+). */
  ratio: number
  /** True once the conversation has reached the model's context limit. */
  full: boolean
  /** Per-component token split (system prompt / tools / history). */
  breakdown?: ContextBreakdown
}

export type AgentPlanTodo = {
  id: string
  title: string
  detail?: string
  tool?: string
  query?: string
}

export type AgentPlanSubQuery = {
  id: string
  query: string
  todos: AgentPlanTodo[]
}

/** A citation source extracted from a tool result (web page or KB document). */
export type AgentSource = {
  kind: 'web' | 'knowledge'
  /** Run-global citation number, matching the inline ``[n]`` in the answer. */
  index?: number
  title: string
  url?: string
  subtitle?: string
  snippet?: string
  /** Knowledge sources: the document to preview and the cited page. */
  documentId?: string
  knowledgeBaseId?: string
  contentType?: string
  page?: number
  /** Web sources: preview assets returned by the search provider. */
  favicon?: string
  image?: string
}

export type AgentRunEvent =
  | { type: 'run.started'; runId: string; agentId: string; sessionId: string }
  | { type: 'plan.started' }
  | {
      type: 'plan'
      understanding?: string
      subQueries?: AgentPlanSubQuery[]
    }
  | { type: 'text'; data: string }
  | { type: 'tool.start'; name: string; toolUseId?: string; input?: unknown }
  | { type: 'tool.input'; toolUseId?: string; input?: unknown }
  | { type: 'tool.stream'; name?: string; toolUseId?: string; data?: unknown }
  | {
      type: 'tool.result'
      toolUseId?: string
      status?: string
      data?: string
      input?: unknown
      sources?: AgentSource[]
    }
  | { type: 'run.completed'; stopReason?: string; usage?: AgentUsage }
  | {
      type: 'context'
      usedTokens: number
      limitTokens: number
      ratio: number
      full: boolean
      breakdown?: ContextBreakdown
    }
  | { type: 'run.error'; message: string }

const RUN_URL = (import.meta.env.VITE_AGENT_RUN_URL ?? '').replace(/\/+$/, '')

export function agentRunConfigured(): boolean {
  return RUN_URL.length > 0
}

type RunParams = {
  token: string
  agentId: string
  input: string
  conversationId: string
  /** Per-run model override; falls back to the agent's saved model. */
  model?: string
  onEvent: (event: AgentRunEvent) => void
  signal?: AbortSignal
}

export async function runAgentStream(params: RunParams): Promise<void> {
  if (!RUN_URL) throw new Error('Agent run URL is not configured')
  const sessionId = params.conversationId.length >= 33 ? params.conversationId : `${params.conversationId}-${'0'.repeat(33)}`.slice(0, 64)

  const response = await fetch(`${RUN_URL}/invocations`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${params.token}`,
      'content-type': 'application/json',
      accept: 'text/event-stream',
      'x-agent-session': sessionId,
    },
    body: JSON.stringify({
      agentId: params.agentId,
      input: params.input,
      conversationId: params.conversationId,
      ...(params.model ? { model: params.model } : {}),
    }),
    signal: params.signal,
  })

  if (!response.ok || !response.body) {
    throw new Error(`Agent run failed (${response.status})`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find((entry) => entry.startsWith('data:'))
      if (!line) continue
      try {
        params.onEvent(JSON.parse(line.slice(5).trim()) as AgentRunEvent)
      } catch {
        // Ignore keep-alives / partial frames.
      }
    }
  }
}

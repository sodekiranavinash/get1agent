/**
 * Streaming client for the agent-run proxy.
 *
 * Runs stream from a Lambda MicroVM (up to 8 hours) whose endpoint is minted by
 * the API Gateway control plane (`POST /v1/agent-run/session`). The MicroVM
 * forwards the Auth0 token to AgentCore, which validates it; the runtime
 * streams normalized SSE frames. Set `VITE_AGENT_RUN_MICROVM=true` for the
 * MicroVM path, or point `VITE_AGENT_RUN_URL` at the local worker (dev).
 */

import { API_BASE_URL } from './api'

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
// When true, runs stream from a Lambda MicroVM (up to 8 hours, vs the
// 15-minute Function cap). The session is bootstrapped through API Gateway
// (`POST /v1/agent-run/session`, JWT-authorised at the gateway), which launches
// the MicroVM and returns its endpoint + ingress token. When false (local dev),
// stream straight from `RUN_URL/invocations`.
const USE_MICROVM = (import.meta.env.VITE_AGENT_RUN_MICROVM ?? '') === 'true'

export function agentRunConfigured(): boolean {
  return USE_MICROVM || RUN_URL.length > 0
}

/** Wire shape from the control plane (`expiresAt` is an ISO timestamp). */
type MicrovmSessionResponse = { endpoint: string; token: string; expiresAt: string }
type MicrovmSession = { endpoint: string; token: string; expiresAt: number }
let cachedSession: MicrovmSession | null = null

// Reuse a MicroVM session only while it still has a comfortable margin left: a
// MicroVM is launched on demand and terminates after it has been idle for a
// while, so a stale endpoint must be re-bootstrapped before then.
const SESSION_REUSE_MARGIN_MS = 10 * 60 * 1000

/** Ask the gateway control plane for a MicroVM endpoint + ingress token. */
async function microvmSession(authToken: string): Promise<{ endpoint: string; token: string }> {
  if (cachedSession && cachedSession.expiresAt - Date.now() > SESSION_REUSE_MARGIN_MS) {
    return { endpoint: cachedSession.endpoint, token: cachedSession.token }
  }
  const response = await fetch(`${API_BASE_URL}/v1/agent-run/session`, {
    method: 'POST',
    headers: { authorization: `Bearer ${authToken}`, 'content-type': 'application/json' },
    body: '{}',
  })
  if (!response.ok) throw new Error(`Agent session failed (${response.status})`)
  const data = (await response.json()) as MicrovmSessionResponse
  const expiresAt = Date.parse(data.expiresAt)
  cachedSession = {
    endpoint: data.endpoint,
    token: data.token,
    expiresAt: Number.isFinite(expiresAt) ? expiresAt : Date.now() + 20 * 60 * 1000,
  }
  return { endpoint: data.endpoint, token: data.token }
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

/** Incremental SSE frame parser; invokes `onEvent` for each `data:` frame. */
function makeFrameParser(onEvent: (event: AgentRunEvent) => void): (chunk: string) => void {
  let buffer = ''
  return (chunk) => {
    buffer += chunk
    const frames = buffer.split('\n\n')
    buffer = frames.pop() ?? ''
    for (const frame of frames) {
      const line = frame.split('\n').find((entry) => entry.startsWith('data:'))
      if (!line) continue
      try {
        onEvent(JSON.parse(line.slice(5).trim()) as AgentRunEvent)
      } catch {
        // Ignore keep-alives / partial frames.
      }
    }
  }
}

function runPayload(params: RunParams) {
  return {
    agentId: params.agentId,
    input: params.input,
    conversationId: params.conversationId,
    ...(params.model ? { model: params.model } : {}),
  }
}

/**
 * Stream a run through the Lambda MicroVM over WebSocket.
 *
 * Browsers can't put the MicroVM ingress token in an HTTP header (the CORS
 * preflight strips custom headers and the ingress rejects it), so the token
 * travels in the `lambda-microvms.authentication.*` WebSocket subprotocol.
 * The Auth0 token is sent in the first message and forwarded to AgentCore.
 */
async function runViaMicrovm(params: RunParams): Promise<void> {
  const session = await microvmSession(params.token)
  const parse = makeFrameParser(params.onEvent)

  await new Promise<void>((resolve, reject) => {
    const socket = new WebSocket(`wss://${session.endpoint}/invocations`, [
      'lambda-microvms',
      `lambda-microvms.authentication.${session.token}`,
      'lambda-microvms.port.8080',
    ])
    let settled = false
    const abort = () => socket.close()
    params.signal?.addEventListener('abort', abort)

    socket.onopen = () => {
      socket.send(JSON.stringify({ token: params.token, payload: runPayload(params) }))
    }
    socket.onmessage = (event) => {
      if (typeof event.data === 'string') parse(event.data)
    }
    socket.onerror = () => {
      if (!settled) {
        settled = true
        reject(new Error('Agent stream failed'))
      }
    }
    socket.onclose = () => {
      params.signal?.removeEventListener('abort', abort)
      if (!settled) {
        settled = true
        resolve()
      }
    }
  })
}

export async function runAgentStream(params: RunParams): Promise<void> {
  if (USE_MICROVM) {
    await runViaMicrovm(params)
    return
  }
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
    body: JSON.stringify(runPayload(params)),
    signal: params.signal,
  })

  if (!response.ok || !response.body) {
    throw new Error(`Agent run failed (${response.status})`)
  }

  const parse = makeFrameParser(params.onEvent)
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    parse(decoder.decode(value, { stream: true }))
  }
}

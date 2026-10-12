/**
 * Avi's streaming client.
 *
 * This is the **only** file in the widget that knows the difference between a
 * guest and a signed-in user. Both audiences end up streaming the same SSE frames
 * from the same MicroVM proxy, because both present a signed token:
 *
 *   signed-in  `POST /v1/avi/session` → session token (the gateway verified the
 *              Auth0 JWT, the control plane resolved the userId and signed it)
 *   guest      `POST /v1/avi/badge`   → guest badge (same mechanism, guest: true)
 *
 * Local development streams straight from the agent service
 * (`VITE_AVI_URL=http://localhost:8091`) so the whole loop runs without a MicroVM.
 */

import type { AgentRunEvent, AgentSource } from './agentRun'
import { makeFrameParser } from './agentRun'
import type { ApiClient } from './api'
import { API_BASE_URL } from './api'
import { createRunFields, reduceRunEvent, type RunFields } from './runState'

/** Avi's own frame: the classifier's verdict, plus example questions on a refusal. */
export type AviIntentFrame = {
  type: 'avi.intent'
  kind: 'platform' | 'off_topic' | 'unsafe'
  intent: string
  confidence: number
  stage: string
  examples: string[]
}

export type AviFrame = AgentRunEvent | AviIntentFrame | AviStageFrame

export function isIntentFrame(frame: unknown): frame is AviIntentFrame {
  return (
    typeof frame === 'object' &&
    frame !== null &&
    (frame as { type?: string }).type === 'avi.intent'
  )
}

/**
 * Avi's live-progress frame: one thing the turn is doing, in order.
 *
 * Emitted by the backend at real milestones (`avi/frames.py`), never inferred by
 * the widget — so the log can name the actual tool, the classified intent and the
 * number of matched pages rather than showing one generic sentence for nine
 * seconds. Stages arrive in order and are appended; the last one is the active
 * step while the run streams.
 */
export type AviStageFrame = {
  type: 'avi.stage'
  stage: string
  label: string
  /** The literal thing behind the label: a query, a feature, a count. */
  detail?: string
  /** The real tool name, kept for transparency. */
  tool?: string
}

export function isStageFrame(frame: unknown): frame is AviStageFrame {
  return (
    typeof frame === 'object' &&
    frame !== null &&
    (frame as { type?: string }).type === 'avi.stage'
  )
}

const RUN_URL = (import.meta.env.VITE_AVI_URL ?? '').replace(/\/+$/, '')
/** Deployed by default; set to 'false' to force the local agent URL. */
const USE_MICROVM = (import.meta.env.VITE_AVI_MICROVM ?? '') !== 'false'

export function aviConfigured(): boolean {
  return USE_MICROVM || RUN_URL.length > 0
}

type MicrovmSession = { endpoint: string; token: string; session: string; expiresAt: number }

// One MicroVM serves many turns; reuse it while it still has margin left, since a
// cold MicroVM costs ~2.3s and the user would feel that on every message.
const SESSION_REUSE_MARGIN_MS = 8 * 60 * 1000

let cachedSession: MicrovmSession | null = null
let cachedGuest: GuestSession | null = null

export function resetAviSession(): void {
  cachedSession = null
  cachedGuest = null
}

type AviErrorBody = {
  error?: string
  code?: string
  retryAfterSeconds?: number | null
  signInRequired?: boolean
}

/** The caller is over their Avi budget (or the guest cap). */
export class AviLimitError extends Error {
  retryAfterSeconds: number
  signInRequired: boolean

  constructor(message: string, retryAfterSeconds: number, signInRequired: boolean) {
    super(message)
    this.name = 'AviLimitError'
    this.retryAfterSeconds = retryAfterSeconds
    this.signInRequired = signInRequired
  }
}

async function readErrorBody(response: Response): Promise<AviErrorBody> {
  try {
    return ((await response.json()) as AviErrorBody) ?? {}
  } catch {
    return {}
  }
}

/** Turn a failed response into the error the caller should see. */
async function errorFor(response: Response): Promise<Error> {
  const body = await readErrorBody(response)
  const message = body.error || `Avi is unavailable (${response.status})`
  if (response.status === 429) {
    // `Retry-After` is the authoritative value; the body carries it too for the
    // case where a proxy strips the header.
    const header = Number(response.headers.get('retry-after') ?? 0)
    const retry = Number(body.retryAfterSeconds ?? 0) || header || 0
    return new AviLimitError(message, retry, Boolean(body.signInRequired))
  }
  return new Error(message)
}

/** Emit a limit as a normal frame, so the widget renders its own card. */
function emitLimit(handlers: AviStreamHandlers, error: AviLimitError): void {
  handlers.onFrame({
    type: 'run.error',
    runId: `avirun_limit_${Date.now()}`,
    message: error.message,
    retryAfterSeconds: error.retryAfterSeconds,
    signInRequired: error.signInRequired,
  } as unknown as AviFrame)
}

/** Ask the control plane for a MicroVM session (signed-in).
 *
 * The same call launches the MicroVM, so a session is one round trip that returns
 * both the ingress pair and the signed token the agent service will verify.
 */
async function microvmSession(authToken: string): Promise<MicrovmSession> {
  if (cachedSession && cachedSession.expiresAt - Date.now() > SESSION_REUSE_MARGIN_MS) {
    return cachedSession
  }
  const response = await fetch(`${API_BASE_URL}/v1/avi/session`, {
    method: 'POST',
    headers: {
      authorization: `Bearer ${authToken}`,
      'content-type': 'application/json',
    },
    body: '{}',
  })
  if (!response.ok) throw await errorFor(response)
  const data = (await response.json()) as {
    endpoint: string
    token: string
    session: string
    expiresAt: string
  }
  const expiresAt = Date.parse(data.expiresAt)
  cachedSession = {
    endpoint: data.endpoint,
    token: data.token,
    session: data.session,
    expiresAt: Number.isFinite(expiresAt) ? expiresAt : Date.now() + 20 * 60 * 1000,
  }
  return cachedSession
}

type GuestSession = { endpoint: string; token: string; badge: string; expiresAt: number }

/** Ask the control plane for a guest badge **and** the MicroVM to use it with.
 *
 * One round trip: the control plane applies the per-IP badge budget, launches the
 * MicroVM and signs a guest token, so the agent service verifies a signature
 * exactly as it does for a signed-in user.
 */
async function guestSession(): Promise<GuestSession> {
  if (cachedGuest && cachedGuest.expiresAt - Date.now() > SESSION_REUSE_MARGIN_MS) {
    return cachedGuest
  }
  const response = await fetch(`${API_BASE_URL}/v1/avi/badge`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ withMicrovm: true }),
  })
  if (!response.ok) throw await errorFor(response)
  const data = (await response.json()) as {
    badge: string
    endpoint?: string
    token?: string
    expiresAt: string
  }
  if (!data.endpoint || !data.token) {
    throw new Error('Avi is briefly unavailable — please try again')
  }
  const expiresAt = Date.parse(data.expiresAt)
  cachedGuest = {
    endpoint: data.endpoint,
    token: data.token,
    badge: data.badge,
    expiresAt: Number.isFinite(expiresAt) ? expiresAt : Date.now() + 10 * 60 * 1000,
  }
  return cachedGuest
}

export type AviTurn = {
  question: string
  history: { role: 'user' | 'assistant'; content: string }[]
  route: string
  conversationId?: string
  runId?: string
}

export type AviStreamHandlers = {
  /** The signed-in user's access token, or undefined for a guest. */
  authToken?: string
  onFrame: (frame: AviFrame) => void
  signal?: AbortSignal
}

/** Parse an SSE byte stream into frames. */
async function* framesFrom(response: Response): AsyncGenerator<AviFrame> {
  if (!response.body) return
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    // SSE frames are separated by a blank line; keep the trailing partial.
    const parts = buffer.split('\n\n')
    buffer = parts.pop() ?? ''
    for (const part of parts) {
      const line = part
        .split('\n')
        .find((candidate) => candidate.startsWith('data:'))
      if (!line) continue
      const payload = line.slice(5).trim()
      if (!payload) continue
      try {
        yield JSON.parse(payload) as AviFrame
      } catch {
        // A malformed frame must not kill the stream.
      }
    }
  }
}

/** Stream one Avi turn, calling `onFrame` for every frame as it arrives. */
export async function streamAviTurn(
  turn: AviTurn,
  handlers: AviStreamHandlers,
): Promise<void> {
  const body = JSON.stringify({
    question: turn.question,
    history: turn.history,
    route: turn.route,
    conversationId: turn.conversationId,
    runId: turn.runId,
  })

  // Local development: the agent service directly.
  if (!USE_MICROVM && RUN_URL) {
    const response = await fetch(`${RUN_URL}/invocations`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        accept: 'text/event-stream',
        ...(handlers.authToken ? { authorization: `Bearer ${handlers.authToken}` } : {}),
      },
      body,
      signal: handlers.signal,
    })
    if (!response.ok) {
      const failure = await errorFor(response)
      if (failure instanceof AviLimitError) {
        emitLimit(handlers, failure)
        return
      }
      throw failure
    }
    for await (const frame of framesFrom(response)) handlers.onFrame(frame)
    return
  }

  // Signed-in and guest sessions have different shapes, so resolve the endpoint,
  // ingress token and agent token per branch rather than widening a union.
  let endpoint: string
  let ingressToken: string
  let token: string
  if (handlers.authToken) {
    const session = await microvmSession(handlers.authToken)
    endpoint = session.endpoint
    ingressToken = session.token
    token = session.session
  } else {
    const guest = await guestSession()
    endpoint = guest.endpoint
    ingressToken = guest.token
    token = guest.badge
  }

  // The MicroVM ingress token cannot be sent as a cross-origin HTTP header, so
  // browsers use a WebSocket and carry it in the authentication subprotocol — the
  // same transport the agent-run client uses.
  await streamOverSocket({ endpoint, ingressToken, token, body, handlers })
}

function streamOverSocket(input: {
  endpoint: string
  ingressToken: string
  token: string
  body: string
  handlers: AviStreamHandlers
}): Promise<void> {
  const { endpoint, ingressToken, token, body, handlers } = input
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(`wss://${endpoint}/invocations`, [
      'lambda-microvms',
      `lambda-microvms.authentication.${ingressToken}`,
      'lambda-microvms.port.8080',
    ])
    let settled = false

    const finish = (error?: Error) => {
      if (settled) return
      settled = true
      try {
        socket.close()
      } catch {
        // already closing
      }
      if (error) reject(error)
      else resolve()
    }

    socket.onopen = () => {
      socket.send(JSON.stringify({ token, payload: JSON.parse(body) }))
    }
    // The shared incremental parser, not a per-message split: a WebSocket frame
    // boundary is not an SSE frame boundary, and splitting per message silently
    // drops any frame the proxy happened to cut in half.
    const parse = makeFrameParser<AviFrame>((frame) => {
      handlers.onFrame(frame)
      if (frame.type === 'run.completed' || frame.type === 'run.error') finish()
    })
    socket.onmessage = (event) => {
      if (typeof event.data === 'string' && event.data) parse(event.data)
    }
    socket.onerror = () => finish(new Error('Avi connection failed'))
    socket.onclose = () => finish()

    handlers.signal?.addEventListener('abort', () => finish(new Error('aborted')))
  })
}

// --------------------------------------------------------------------------- #
// Widget-facing state
// --------------------------------------------------------------------------- #

export type AviIntent = {
  kind: AviIntentFrame['kind']
  intent: string
  stage: string
  examples: string[]
}

export type AviWidgetTurn = {
  id: string
  question: string
  run: RunFields
  intent: AviIntent | null
  /** The live work log for this turn, in the order the backend emitted it. */
  stages: AviStage[]
  /** The model that produced this answer (from `run.started`), for feedback. */
  model?: string
  /** The thumb the user left, if any. Kept on the turn so it survives a reload. */
  feedback?: { value: AviFeedbackValue; comment?: string }
}

/** One entry in the work log. */
export type AviStage = {
  key: string
  label: string
  detail?: string
  tool?: string
}

export function newAviTurn(question: string): AviWidgetTurn {
  return {
    id: `avi_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
    question,
    run: createRunFields(),
    intent: null,
    stages: [],
  }
}

/** Apply one frame to a turn (the intent and stage frames are stored, not reduced). */
export function applyAviFrame(turn: AviWidgetTurn, frame: AviFrame): AviWidgetTurn {
  if (isIntentFrame(frame)) {
    return {
      ...turn,
      intent: {
        kind: frame.kind,
        intent: frame.intent,
        stage: frame.stage,
        examples: frame.examples ?? [],
      },
    }
  }

  if (isStageFrame(frame)) {
    const stages = turn.stages ?? []
    const last = stages[stages.length - 1]
    // The backend can re-announce a milestone (a retry after a transient error).
    // Collapsing a consecutive duplicate keeps the log readable without a counter.
    if (last && last.key === frame.stage && last.label === frame.label) {
      return turn
    }
    return {
      ...turn,
      stages: [
        ...stages,
        { key: frame.stage, label: frame.label, detail: frame.detail, tool: frame.tool },
      ],
    }
  }

  const run = reduceRunEvent(turn.run, frame)
  const next: AviWidgetTurn = { ...turn, run }

  // `runState` deliberately ignores the model; feedback wants it, so capture it.
  if (frame.type === 'run.started' && frame.model) next.model = frame.model

  if (frame.type === 'run.completed') {
    // The reducer blanks the answer when a tool call starts (text before a tool
    // is preamble). If the turn then ended without more text, the server's
    // authoritative answer is the only copy left — adopt it rather than show
    // "No answer."
    const finalText = typeof frame.text === 'string' ? frame.text.trim() : ''
    if (!run.answer.trim() && finalText) {
      next.run = { ...run, answer: finalText }
    }
    // Avi gathers its citations *before* the first model call, so a turn that
    // never calls a tool reports them only here.
    const late = frame.sources ?? []
    if (late.length > 0) {
      next.run = mergeRunSources(next.run, late, turn.id)
    }
  }

  return next
}

/** Merge run-global citations without duplicating one already collected. */
function mergeRunSources(run: RunFields, incoming: AgentSource[], turnId: string): RunFields {
  const seen = new Set(
    (run.sources ?? []).map((source) => source.route || source.url || source.title),
  )
  const merged = [...(run.sources ?? [])]
  incoming.forEach((source, index) => {
    const key = source.route || source.url || source.title
    if (!key || seen.has(key)) return
    seen.add(key)
    // `RunFields.sources` is `ChatSource` (it needs an id for the citation
    // badges); the reducer adds one the same way for `tool.result` sources.
    merged.push({ ...source, id: `${turnId}-late-${index}` })
  })
  return { ...run, sources: merged }
}

// --------------------------------------------------------------------------- #
// Feedback (signed-in only)
// --------------------------------------------------------------------------- #

export type AviFeedbackValue = 'up' | 'down'

export type AviFeedbackInput = {
  runId: string
  value: AviFeedbackValue
  comment?: string
  question?: string
  answerPreview?: string
  conversationId?: string
  route?: string
  model?: string
  classifierKind?: string
  intent?: string
  latencyMs?: number
  tokensIn?: number
  tokensOut?: number
  sources?: { title?: string; route?: string }[]
}

/**
 * Record a thumb for one Avi answer.
 *
 * It goes to the ordinary JWT-protected API, not to the agent service: the
 * browser cannot mint the MicroVM ingress token, so the agent service's own
 * `POST /feedback` is unreachable from here. user-api writes the same
 * `AVIFEEDBACK#` item through the same repository, so the admin feedback table
 * sees one stream of data regardless of which path recorded it.
 */
export async function sendAviFeedback(
  api: ApiClient,
  input: AviFeedbackInput,
): Promise<void> {
  await api.post<{ stored: boolean; runId?: string }>('/v1/avi/feedback', input)
}

/** The transcript to send on the next turn (bounded by the server too). */
export function historyFor(turns: AviWidgetTurn[]): {
  role: 'user' | 'assistant'
  content: string
}[] {
  const history: { role: 'user' | 'assistant'; content: string }[] = []
  for (const turn of turns) {
    history.push({ role: 'user', content: turn.question })
    if (turn.run.answer.trim()) {
      history.push({ role: 'assistant', content: turn.run.answer })
    }
  }
  // The server keeps the last few turns and a character budget; this is a cheap
  // client-side guard so a long dialog does not send megabytes.
  return history.slice(-16)
}

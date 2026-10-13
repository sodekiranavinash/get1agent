/**
 * AI Assistant's client.
 *
 * The widget talks to **one** Lambda through two API Gateway routes, and this is
 * the only file that knows which one to use:
 *
 *   signed-in  `POST /v1/ai-assistant/ask`    → API Gateway verified the Auth0 JWT
 *   guest      `POST /v1/ai-assistant/guest`  → no authorizer; the Lambda hashes the
 *                                               caller's IP into a rate-limit bucket
 *
 * Identity is never sent in the body — the gateway's verified claims are the only
 * thing the backend trusts, so there is no session to establish first and no token
 * to mint. One request per turn.
 *
 * The response is **buffered, not streamed**: API Gateway cannot stream and caps an
 * integration at 30s, so the Lambda returns the whole run as one SSE body. The
 * frame parser below is therefore reading a complete body rather than a live
 * socket — the frames are identical, only the arrival time differs.
 *
 * `VITE_AI_ASSISTANT_URL` is the local-development override: it points at the
 * `ai-assistant` service in the Floci stack (port 8091, started by `make floci`),
 * which keeps the whole loop working without a deploy.
 */

import type { AgentRunEvent, AgentSource } from './agentRun'
import type { ApiClient } from './api'
import { API_BASE_URL } from './api'
import { createRunFields, reduceRunEvent, type RunFields } from './runState'

/** AI Assistant's own frame: the classifier's verdict, plus example questions on a refusal. */
export type AviIntentFrame = {
  type: 'ai-assistant.intent'
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
    (frame as { type?: string }).type === 'ai-assistant.intent'
  )
}

/**
 * AI Assistant's live-progress frame: one thing the turn is doing, in order.
 *
 * Emitted by the backend at real milestones (`ai-assistant/frames.py`), never inferred by
 * the widget — so the log can name the actual tool, the classified intent and the
 * number of matched pages rather than showing one generic sentence for nine
 * seconds. Stages arrive in order and are appended; the last one is the active
 * step while the run streams.
 */
export type AviStageFrame = {
  type: 'ai-assistant.stage'
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
    (frame as { type?: string }).type === 'ai-assistant.stage'
  )
}

const LOCAL_URL = (import.meta.env.VITE_AI_ASSISTANT_URL ?? '').replace(/\/+$/, '')

/** Local development talks to the service directly; otherwise the gateway routes. */
function turnUrl(authenticated: boolean): string {
  const route = authenticated ? '/v1/ai-assistant/ask' : '/v1/ai-assistant/guest'
  // The local override is an **origin** (`http://localhost:8091`), not a route —
  // it replaces the gateway, not the path. Returning it bare posted every turn to
  // `/`, which the local server answers with a 404 body that has no `error` field,
  // so the widget said "AI Assistant is unavailable (404)" — while the service
  // itself was healthy. The route has to be appended on both branches.
  return LOCAL_URL ? `${LOCAL_URL}${route}` : `${API_BASE_URL}${route}`
}

/**
 * Whether the widget can reach AI Assistant at all.
 *
 * Both deployed routes live behind the same API base URL, so a build is configured
 * as long as it has one. The old `VITE_AI_ASSISTANT_MICROVM` flag is gone with the
 * MicroVM it selected.
 */
export function aviConfigured(): boolean {
  return LOCAL_URL.length > 0 || API_BASE_URL.length > 0
}

type AviErrorBody = {
  error?: string
  code?: string
  retryAfterSeconds?: number | null
  signInRequired?: boolean
}

/** The caller is over their AI Assistant budget (or the guest cap). */
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
  const message = body.error || `AI Assistant is unavailable (${response.status})`
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

/**
 * Parse a buffered SSE body into frames.
 *
 * The body is already complete, so this is a split rather than a stream reader —
 * but it is written to tolerate a partial trailing frame anyway, because a proxy
 * may still cut the body short and a half-frame must not throw.
 */
function framesFrom(body: string): AviFrame[] {
  const frames: AviFrame[] = []
  for (const part of body.split('\n\n')) {
    const line = part
      .split('\n')
      .find((candidate) => candidate.startsWith('data:'))
    if (!line) continue
    const payload = line.slice(5).trim()
    if (!payload) continue
    try {
      frames.push(JSON.parse(payload) as AviFrame)
    } catch {
      // A malformed frame must not cost the rest of the answer.
    }
  }
  return frames
}

/**
 * Send one AI Assistant turn and apply the frames it returns.
 *
 * One request, one response: the route (not a body field) decides whether the
 * gateway's Auth0 authorizer is in front, so a signed-in user's request carries
 * their bearer token and a guest's carries none.
 */
export async function streamAviTurn(
  turn: AviTurn,
  handlers: AviStreamHandlers,
): Promise<void> {
  const authenticated = Boolean(handlers.authToken)
  const response = await fetch(turnUrl(authenticated), {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      accept: 'text/event-stream',
      ...(handlers.authToken ? { authorization: `Bearer ${handlers.authToken}` } : {}),
    },
    body: JSON.stringify({
      question: turn.question,
      history: turn.history,
      route: turn.route,
      conversationId: turn.conversationId,
      runId: turn.runId,
    }),
    signal: handlers.signal,
  })

  if (!response.ok) {
    const failure = await errorFor(response)
    if (failure instanceof AviLimitError) {
      // A cap is part of the conversation, not a crash: render it as a frame so
      // the widget shows its own card instead of a generic error banner.
      emitLimit(handlers, failure)
      return
    }
    throw failure
  }

  for (const frame of framesFrom(await response.text())) handlers.onFrame(frame)
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
  feedback?: { value: AiAssistantFeedbackValue; comment?: string }
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
    // AI Assistant gathers its citations *before* the first model call, so a turn that
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

export type AiAssistantFeedbackValue = 'up' | 'down'

export type AiAssistantFeedbackInput = {
  runId: string
  value: AiAssistantFeedbackValue
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
 * Record a thumb for one AI Assistant answer.
 *
 * It goes to the ordinary JWT-protected API, not to the agent service: the
 * browser cannot mint the MicroVM ingress token, so the agent service's own
 * `POST /feedback` is unreachable from here. user-api writes the same
 * `AIFEEDBACK#` item through the same repository, so the admin feedback table
 * sees one stream of data regardless of which path recorded it.
 */
export async function sendAiAssistantFeedback(
  api: ApiClient,
  input: AiAssistantFeedbackInput,
): Promise<void> {
  await api.post<{ stored: boolean; runId?: string }>('/v1/ai-assistant/feedback', input)
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

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  applyAviFrame,
  aviConfigured,
  historyFor,
  newAviTurn,
  sendAiAssistantFeedback,
  streamAviTurn,
  type AiAssistantFeedbackValue,
  type AviFrame,
  type AviWidgetTurn,
} from '../../lib/aiAssistant'
import type { ApiClient } from '../../lib/api'
import { markRunStopped } from '../../lib/runState'

/**
 * AI Assistant's dialog state: the transcript, the in-flight turn, and the send action.
 *
 * AI Assistant keeps **no server-side turn state** — the browser sends the whole
 * transcript every time — so this hook owns the conversation for the session,
 * persists it to `sessionStorage` (so closing and reopening the dialog does not
 * lose it), and clears it on "New chat".
 */
const STORAGE_KEY = 'ai-assistant.transcript.v1'
/**
 * The signed-in conversation id.
 *
 * The **server** mints it (the browser cannot), reports it as
 * `run.started.sessionId`, and stores each finished turn under it. The widget
 * must therefore remember it and send it back on the next turn — otherwise every
 * turn is stored as its own conversation, or (with no id at all) not stored.
 */
const CONVERSATION_KEY = 'ai-assistant.conversation.v1'
const MAX_TURNS = 12

function loadConversationId(): string {
  try {
    return sessionStorage.getItem(CONVERSATION_KEY) ?? ''
  } catch {
    return ''
  }
}

function saveConversationId(id: string): void {
  try {
    if (id) sessionStorage.setItem(CONVERSATION_KEY, id)
    else sessionStorage.removeItem(CONVERSATION_KEY)
  } catch {
    // Storage is a nicety; never let it break the dialog.
  }
}

function loadTranscript(): AviWidgetTurn[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw) as AviWidgetTurn[]
    if (!Array.isArray(parsed)) return []
    // Only keep settled turns; a reload cannot resume a half-streamed answer.
    return parsed
      .filter((turn) => turn && typeof turn.question === 'string' && turn.run)
      .map((turn) => ({
        ...turn,
        // A transcript written before the work log existed has no `stages`.
        stages: Array.isArray(turn.stages) ? turn.stages : [],
        run: { ...turn.run, status: turn.run.status === 'streaming' ? 'stopped' : turn.run.status },
      }))
      .slice(-MAX_TURNS)
  } catch {
    return []
  }
}

function saveTranscript(turns: AviWidgetTurn[]): void {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(turns.slice(-MAX_TURNS)))
  } catch {
    // Storage is a nicety; never let it break the dialog.
  }
}

export type AviStatus = 'idle' | 'streaming' | 'error' | 'limited'

export function useAiAssistant({
  route,
  authToken,
  open,
  api,
}: {
  route: string
  /** The signed-in user's access token; absent for a guest. */
  authToken?: string
  open: boolean
  /** The app's API client, used only to post a thumb. */
  api: ApiClient
}) {
  const [turns, setTurns] = useState<AviWidgetTurn[]>(() => loadTranscript())
  const [status, setStatus] = useState<AviStatus>('idle')
  const [error, setError] = useState('')
  const [retryAfter, setRetryAfter] = useState(0)
  const [signInRequired, setSignInRequired] = useState(false)
  const [conversationId, setConversationId] = useState<string>(() => loadConversationId())
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement | null>(null)
  // A ref as well as state: `send` reads it when the request is built, so a
  // `run.started` frame that lands mid-turn cannot race the render.
  const conversationRef = useRef(conversationId)

  const adoptConversation = useCallback((id: string) => {
    if (!id || conversationRef.current === id) return
    conversationRef.current = id
    setConversationId(id)
    saveConversationId(id)
  }, [])

  useEffect(() => {
    saveTranscript(turns)
  }, [turns])

  // Follow the answer as it streams in.
  useEffect(() => {
    if (!open) return
    const node = scrollRef.current
    if (!node) return
    node.scrollTop = node.scrollHeight
  }, [open, turns])

  // Cancel an in-flight turn when the dialog closes or the page unmounts.
  useEffect(() => {
    if (open) return
    abortRef.current?.abort()
  }, [open])

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setStatus('idle')
    // Settle the turn too. `run.status` is what the message renders from, and an
    // aborted stream never delivers its terminal frame — so without this the
    // work-log and skeleton kept animating forever on a request that was already
    // cut off.
    setTurns((current) =>
      current.map((turn) =>
        turn.run.status === 'streaming' ? { ...turn, run: markRunStopped(turn.run) } : turn,
      ),
    )
  }, [])

  const send = useCallback(
    async (question: string) => {
      const text = question.trim()
      if (!text || status === 'streaming') return
      if (!aviConfigured()) {
        setStatus('error')
        setError('AI Assistant is not configured in this build.')
        return
      }

      setError('')
      setRetryAfter(0)
      setSignInRequired(false)
      const pending = newAviTurn(text)
      const history = historyFor(turns)
      const controller = new AbortController()
      abortRef.current = controller
      setStatus('streaming')
      setTurns((current) => [...current, pending].slice(-MAX_TURNS))

      const onFrame = (frame: AviFrame) => {
        // The control plane / agent service mints the conversation on the first
        // signed-in turn and reports it here; carry it forward from now on.
        if (frame.type === 'run.started' && authToken && frame.sessionId) {
          adoptConversation(frame.sessionId)
        }
        setTurns((current) =>
          current.map((turn) => (turn.id === pending.id ? applyAviFrame(turn, frame) : turn)),
        )
        if (frame.type === 'run.error') {
          const detail = frame as { message?: string; retryAfterSeconds?: number; signInRequired?: boolean }
          const retry = Number(detail.retryAfterSeconds ?? 0)
          if (retry > 0) {
            setStatus('limited')
            setRetryAfter(retry)
            setSignInRequired(Boolean(detail.signInRequired))
          } else {
            setStatus('error')
            setError(detail.message || 'Something went wrong.')
          }
        }
      }

      try {
        await streamAviTurn(
          {
            question: text,
            history,
            route,
            conversationId: authToken ? conversationRef.current || undefined : undefined,
          },
          { authToken, onFrame, signal: controller.signal },
        )
        setStatus((current) => (current === 'streaming' ? 'idle' : current))
      } catch (err) {
        const message = err instanceof Error ? err.message : String(err)
        if (/abort/i.test(message)) {
          setStatus('idle')
        } else {
          setStatus('error')
          setError(message)
        }
      } finally {
        abortRef.current = null
        // A stream can end without its terminal frame — the user pressed Stop, the
        // socket dropped, or a proxy timed out. `run.status` is what the message
        // renders from, so anything still marked `streaming` here would animate its
        // work log forever on a request that is already over. Idempotent for a
        // completed run (already `done`).
        setTurns((current) =>
          current.map((turn) =>
            turn.run.status === 'streaming' ? { ...turn, run: markRunStopped(turn.run) } : turn,
          ),
        )
      }
    },
    [adoptConversation, authToken, route, status, turns],
  )

  const reset = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setTurns([])
    setStatus('idle')
    setError('')
    setRetryAfter(0)
    setSignInRequired(false)
    // A new chat starts a new stored conversation; the next turn mints one.
    conversationRef.current = ''
    setConversationId('')
    saveConversationId('')
  }, [])

  /**
   * Record a thumb for a finished turn.
   *
   * The mark is optimistic (a rating that does not feel registered gets pressed
   * twice) and rolled back if the write fails. It is only offered to a signed-in
   * caller: a guest's rating has no account to attach to and is discarded
   * server-side, so asking for one would be dishonest.
   */
  const rate = useCallback(
    async (turnId: string, value: AiAssistantFeedbackValue, comment = '') => {
      const turn = turns.find((entry) => entry.id === turnId)
      const runId = turn?.run.runId
      if (!turn || !runId) return
      const previous = turn.feedback
      setTurns((current) =>
        current.map((entry) => (entry.id === turnId ? { ...entry, feedback: { value, comment } } : entry)),
      )
      try {
        await sendAiAssistantFeedback(api, {
          runId,
          value,
          comment,
          question: turn.question,
          answerPreview: turn.run.answer.slice(0, 1_000),
          conversationId: conversationRef.current || undefined,
          route,
          model: turn.model,
          classifierKind: turn.intent?.kind,
          intent: turn.intent?.intent,
          latencyMs:
            turn.run.endedAt && turn.run.startedAt
              ? turn.run.endedAt - turn.run.startedAt
              : undefined,
          tokensIn: turn.run.usage?.inputTokens ?? undefined,
          tokensOut: turn.run.usage?.outputTokens ?? undefined,
          sources: (turn.run.sources ?? []).map((source) => ({
            title: source.title,
            route: source.route,
          })),
        })
      } catch {
        setTurns((current) =>
          current.map((entry) => (entry.id === turnId ? { ...entry, feedback: previous } : entry)),
        )
      }
    },
    [api, route, turns],
  )

  const lastTurn = turns[turns.length - 1]
  const examples = lastTurn?.intent?.examples ?? []

  return {
    turns,
    status,
    error,
    retryAfter,
    signInRequired,
    examples,
    streaming: status === 'streaming',
    send,
    stop,
    reset,
    rate,
    scrollRef,
  }
}

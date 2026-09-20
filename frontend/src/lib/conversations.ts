import type { AgentRunEvent } from './agentRun'
import type { AgentOutputFormat } from './agents'
import type { ChatTurn } from './chat'
import { createRunFields, reduceRunEvent } from './runState'

/** A chat/builder conversation (global numeric id, embedded in the URL). */
export type Conversation = {
  conversationId: number
  agentId: string
  agentName: string
  kind: 'chat' | 'run'
  title: string
  lastPreview: string
  messageCount: number
  runCount: number
  createdAt: string
  updatedAt: string
}

/** One persisted turn: the question plus the full run event stream. */
export type StoredTurn = {
  runId: string
  question: string
  model?: string
  agentId?: string
  agentName?: string
  startedAt?: string
  completedAt?: string
  status?: string
  events?: AgentRunEvent[]
}

export type ConversationDetail = {
  conversation: Conversation
  turns: StoredTurn[]
}

/** Rebuild a renderable chat turn by replaying the stored run events. */
export function turnFromStored(
  stored: StoredTurn,
  outputFormat: AgentOutputFormat,
): ChatTurn {
  const startedAt = stored.startedAt ? new Date(stored.startedAt).getTime() : Date.now()
  const endedAt = stored.completedAt ? new Date(stored.completedAt).getTime() : undefined
  let turn: ChatTurn = {
    id: stored.runId,
    question: stored.question,
    outputFormat,
    agentId: stored.agentId ?? '',
    agentName: stored.agentName ?? '',
    model: stored.model ?? '',
    at: stored.startedAt ?? new Date().toISOString(),
    ...createRunFields(startedAt),
  }
  for (const event of stored.events ?? []) {
    turn = reduceRunEvent(turn, event)
  }
  // Replay stamps timing with ``Date.now()``; restore the real timestamps so the
  // duration shown for a reopened run matches what actually happened.
  turn = { ...turn, startedAt, ...(endedAt ? { endedAt } : {}) }
  if (turn.status !== 'streaming') {
    turn = { ...turn, planning: false }
  }
  return turn
}

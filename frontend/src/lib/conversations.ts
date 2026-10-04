import type { AgentRunEvent } from './agentRun'
import type { AgentOutputFormat } from './agents'
import type { ChatTurn } from './chat'
import type { Feedback } from './feedback'
import { createRunFields, reduceRunEvent } from './runState'
import type { WorkflowMode } from './workflows'
import type { WorkflowRunEvent } from './workflowRun'
import {
  createWorkflowRunFields,
  reduceWorkflowEvent,
  runSources,
} from './workflowRunState'

/** A chat/builder conversation (global numeric id, embedded in the URL). */
export type Conversation = {
  conversationId: number
  agentId: string
  agentName: string
  /** Whether ``agentId`` is an agent id or a workflow id. */
  targetType?: 'agent' | 'workflow'
  kind: 'chat' | 'run'
  title: string
  lastPreview: string
  messageCount: number
  runCount: number
  /** Latest run id + trace (keys the builder-history feedback). */
  lastRunId?: string | null
  lastTraceId?: string | null
  /** Signed, expiring AWS (CloudWatch) trace link for the latest run (API-minted). */
  lastTraceUrl?: string | null
  /** The user's feedback for the latest run, if any. */
  feedback?: Feedback | null
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
  targetType?: 'agent' | 'workflow'
  mode?: WorkflowMode
  startedAt?: string
  completedAt?: string
  status?: string
  traceId?: string | null
  /** Signed, expiring AWS (CloudWatch) trace link (API-minted on read). */
  traceUrl?: string | null
  /** The user's feedback for this run, if any. */
  feedback?: Feedback | null
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

  if (stored.targetType === 'workflow') {
    let workflow = createWorkflowRunFields(stored.mode ?? 'graph', startedAt)
    for (const event of stored.events ?? []) {
      workflow = reduceWorkflowEvent(workflow, event as unknown as WorkflowRunEvent)
    }
    // Older transcripts have no per-node timestamps, so replay would stamp them
    // all at "now" and show a bogus 0ms per node. Drop those durations.
    const timedNodes = (stored.events ?? []).some((event) => {
      const frame = event as { type?: string; at?: unknown }
      return (
        (frame.type === 'node.started' || frame.type === 'node.completed') &&
        typeof frame.at === 'number'
      )
    })
    if (!timedNodes) {
      workflow = {
        ...workflow,
        nodes: workflow.nodes.map((node) => ({
          ...node,
          startedAt: undefined,
          endedAt: undefined,
        })),
      }
    }
    workflow = {
      ...workflow,
      startedAt,
      ...(endedAt ? { endedAt } : {}),
      traceUrl: stored.traceUrl ?? workflow.traceUrl,
      traceId: stored.traceId ?? workflow.traceId,
    }
    return {
      id: stored.runId,
      runId: stored.runId,
      question: stored.question,
      answer: workflow.answer,
      tools: [],
      sources: runSources(workflow),
      plan: null,
      planning: false,
      skills: [],
      status: workflow.status,
      error: workflow.error,
      usage: workflow.usage,
      traceUrl: workflow.traceUrl,
      traceId: workflow.traceId,
      feedback: stored.feedback ?? null,
      outputFormat,
      agentId: stored.agentId ?? '',
      agentName: stored.agentName ?? '',
      model: stored.model ?? '',
      at: stored.startedAt ?? new Date().toISOString(),
      startedAt,
      endedAt,
      targetType: 'workflow',
      workflow,
    }
  }

  let turn: ChatTurn = {
    id: stored.runId,
    runId: stored.runId,
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
  // Prefer the API-minted signed link over any raw URL replayed from the events.
  turn = {
    ...turn,
    traceUrl: stored.traceUrl ?? turn.traceUrl,
    traceId: stored.traceId ?? turn.traceId,
    feedback: stored.feedback ?? null,
  }
  return turn
}

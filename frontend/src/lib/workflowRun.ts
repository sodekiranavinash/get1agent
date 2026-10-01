/**
 * Streaming client + event types for workflow runs.
 *
 * Reuses the shared invocation transport in `agentRun.ts` (MicroVM/WebSocket in
 * prod, SSE from the local worker in dev). The runtime dispatches on
 * `workflowId`, so the payload differs but the wire envelope is the same.
 */

import {
  streamInvocation,
  type AgentRunEvent,
  type AgentSource,
  type AgentUsage,
  type PendingQuestion,
} from './agentRun'
import type { ChatQuestion } from './chat'
import type { WorkflowMode } from './workflows'

/** A node the runtime knows about (sent once at the start of a run). */
export type WorkflowRunNodeMeta = {
  id: string
  name: string
  agentName: string
  model?: string
  /** The synthesized host agent(s) vs a saved agent. */
  role?: 'host' | 'agent'
  /**
   * Host stage: the swarm entry host, the graph dispatcher, or the graph
   * synthesizer (which produces the final answer).
   */
  stage?: 'host' | 'dispatch' | 'synthesis'
}

/** One node's run, as tracked by the UI reducer. */
export type WorkflowNodeRun = {
  id: string
  name: string
  agentName: string
  model?: string
  role?: 'host' | 'agent'
  stage?: 'host' | 'dispatch' | 'synthesis'
  status: 'pending' | 'running' | 'done' | 'error'
  /** The node's streamed final text. */
  output: string
  tools: WorkflowToolCall[]
  sources: WorkflowSource[]
  startedAt?: number
  endedAt?: number
  usage?: AgentUsage
}

export type WorkflowToolCall = {
  id: string
  name: string
  status: 'running' | 'success' | 'error'
  input?: string
  output?: string
  sources?: WorkflowSource[]
}

export type WorkflowSource = AgentSource & { id: string }

export type WorkflowHandoff = {
  id: string
  from: string[]
  to: string[]
  message?: string
  at: number
}

export type WorkflowRunFields = {
  runId?: string
  mode: WorkflowMode
  status: 'streaming' | 'done' | 'error' | 'stopped' | 'awaiting_input'
  nodes: WorkflowNodeRun[]
  handoffs: WorkflowHandoff[]
  answer: string
  error?: string
  usage?: AgentUsage
  sources: WorkflowSource[]
  /** Present while the host is paused for the user's answer. */
  humanQuestion?: ChatQuestion
  traceUrl?: string | null
  traceId?: string | null
  startedAt: number
  endedAt?: number
}

export type WorkflowRunEvent =
  | { type: 'run.started'; runId: string; workflowId: string; sessionId: string; mode: WorkflowMode }
  | {
      type: 'workflow'
      mode: WorkflowMode
      nodes: WorkflowRunNodeMeta[]
    }
  | { type: 'node.started'; nodeId: string; nodeName?: string; agentName?: string; at?: number }
  | { type: 'node.handoff'; from: string[]; to: string[]; message?: string }
  | { type: 'node.completed'; nodeId: string; status: string; usage?: AgentUsage; at?: number }
  | { type: 'node.stream'; nodeId: string; event: AgentRunEvent }
  | { type: 'trace'; traceId?: string | null; traceUrl?: string | null }
  | {
      /** Human-in-the-loop: the workflow host paused for the user's answer. */
      type: 'question'
      nodeId?: string
      questionId: string
      question: string
      options?: string[]
      allowCustom?: boolean
      answer?: string
    }
  | { type: 'run.completed'; answer?: string; usage?: AgentUsage }
  | { type: 'run.error'; message: string }

type WorkflowRunParams = {
  token: string
  workflowId: string
  input: string
  conversationId: string
  /** Host answer-depth override (summarize | normal | detailed). */
  answerMode?: string
  /** Host reasoning-effort override (low | medium | high). */
  reasoning?: string
  /** Per-run agent selection (order preserved); omitted = the saved agents. */
  agentIds?: string[]
  /** Chat-only human-in-the-loop (see `RunParams.humanInLoop`). */
  humanInLoop?: boolean
  /** Answers to a paused workflow; resumes the same run. */
  interruptResponses?: { interruptId: string; response: string }[]
  /** The pending question, replayed into the resumed turn's transcript. */
  pendingQuestion?: PendingQuestion
  /** The paused turn's run id, so the resume replaces it instead of appending. */
  resumeRunId?: string
  onEvent: (event: WorkflowRunEvent) => void
  signal?: AbortSignal
}

export async function runWorkflowStream(params: WorkflowRunParams): Promise<void> {
  await streamInvocation<WorkflowRunEvent>({
    token: params.token,
    payload: {
      workflowId: params.workflowId,
      input: params.input,
      conversationId: params.conversationId,
      ...(params.answerMode ? { answerMode: params.answerMode } : {}),
      ...(params.reasoning ? { reasoning: params.reasoning } : {}),
      ...(params.agentIds ? { agentIds: params.agentIds } : {}),
      ...(params.humanInLoop !== undefined ? { humanInLoop: params.humanInLoop } : {}),
      ...(params.interruptResponses ? { interruptResponses: params.interruptResponses } : {}),
      ...(params.pendingQuestion ? { pendingQuestion: params.pendingQuestion } : {}),
      ...(params.resumeRunId ? { resumeRunId: params.resumeRunId } : {}),
    },
    onEvent: params.onEvent,
    signal: params.signal,
  })
}

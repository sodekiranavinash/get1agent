import type { AgentRunEvent } from '../agentRun'
import type { WorkflowRunEvent } from '../workflowRun'
import {
  demoAgentHitlScript,
  demoAgentRunScript,
  demoWorkflowRunScript,
} from './conversations'

/**
 * Scripted live runs for the read-only demo.
 *
 * A visitor can send a message in chat and watch a realistic run stream in:
 * the same `run.started → skills → plan → tool.* → text → trace → completed`
 * frames the real runtime emits, replayed from the demo transcripts with a
 * typing effect. The shared reducers on the chat screen rebuild the plan, tool
 * calls, citations and source previews exactly as they do for a real run.
 */

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms))

function abortError(): Error {
  const error = new Error('Aborted')
  error.name = 'AbortError'
  return error
}

/** Split text into word-boundary chunks for a typing effect. */
function chunkText(text: string): string[] {
  const chunks: string[] = []
  let current = ''
  for (const token of text.split(/(\s+)/)) {
    if (current && (current + token).length > 140) {
      chunks.push(current)
      current = ''
    }
    current += token
  }
  if (current) chunks.push(current)
  return chunks
}

const DELAY: Record<string, number> = {
  'run.started': 220,
  skills: 180,
  attachments: 180,
  'plan.started': 260,
  plan: 520,
  'tool.start': 320,
  'tool.input': 160,
  'tool.stream': 80,
  'tool.result': 560,
  trace: 120,
  context: 120,
  'run.completed': 60,
  question: 400,
  workflow: 260,
  'node.started': 280,
  'node.handoff': 280,
  'node.completed': 280,
  'node.stream': 160,
  'run.error': 60,
}

async function emit(
  event: Record<string, unknown>,
  onEvent: (event: unknown) => void,
  signal: AbortSignal | undefined,
): Promise<void> {
  const type = String(event.type ?? '')

  // Workflow text is nested inside the `node.stream` frame.
  if (type === 'node.stream') {
    const inner = event.event as Record<string, unknown> | undefined
    if (inner && inner.type === 'text' && typeof inner.data === 'string') {
      for (const piece of chunkText(inner.data)) {
        if (signal?.aborted) throw abortError()
        onEvent({ ...event, event: { ...inner, data: piece } })
        await sleep(24)
      }
      return
    }
  }

  if (type === 'text' && typeof event.data === 'string') {
    for (const piece of chunkText(event.data)) {
      if (signal?.aborted) throw abortError()
      onEvent({ ...event, data: piece })
      await sleep(24)
    }
    return
  }

  onEvent(event)
  await sleep(DELAY[type] ?? 120)
}

async function stream(
  script: unknown[],
  onEvent: (event: unknown) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (signal?.aborted) throw abortError()
  await sleep(220)
  for (const raw of script) {
    await emit(raw as Record<string, unknown>, onEvent, signal)
  }
}

export async function streamDemoAgentRun(
  agentName: string,
  onEvent: (event: AgentRunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  // A demo agent may pause on a human-in-the-loop question: stream up to and
  // including the `question` frame, then stop so the visitor can answer.
  const hitl = demoAgentHitlScript(agentName)
  await stream(
    hitl ? hitl.before : demoAgentRunScript(agentName),
    onEvent as unknown as (event: unknown) => void,
    signal,
  )
}

/** Continue a demo run after the visitor answered its question. */
export async function streamDemoAgentAnswer(
  agentName: string,
  onEvent: (event: AgentRunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const hitl = demoAgentHitlScript(agentName)
  if (!hitl) return
  await stream(hitl.after, onEvent as unknown as (event: unknown) => void, signal)
}

export async function streamDemoWorkflowRun(
  workflowName: string,
  onEvent: (event: WorkflowRunEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  await stream(
    demoWorkflowRunScript(workflowName),
    onEvent as unknown as (event: unknown) => void,
    signal,
  )
}

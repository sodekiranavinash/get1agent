/**
 * Reducer that turns the workflow runtime's SSE frames into renderable state.
 *
 * Each agent node keeps its own little run (streamed text, tool calls, sources)
 * and the run keeps a global handoff list. Shared by the workflow builder and the
 * chat screen so both render identical structure.
 */

import { formatToolInput, stringifyToolData } from './chat'
import type { AgentRunEvent } from './agentRun'
import type {
  WorkflowNodeRun,
  WorkflowRunEvent,
  WorkflowRunFields,
  WorkflowRunNodeMeta,
  WorkflowSource,
  WorkflowToolCall,
} from './workflowRun'
import type { WorkflowMode } from './workflows'

export function createWorkflowRunFields(
  mode: WorkflowMode,
  startedAt = Date.now(),
): WorkflowRunFields {
  return {
    mode,
    status: 'streaming',
    nodes: [],
    handoffs: [],
    answer: '',
    sources: [],
    startedAt,
  }
}

function makeNode(meta: {
  id: string
  name?: string
  agentName?: string
  model?: string
  role?: 'host' | 'agent'
  stage?: 'host' | 'dispatch' | 'synthesis'
}): WorkflowNodeRun {
  return {
    id: meta.id,
    name: meta.name || meta.agentName || meta.id,
    agentName: meta.agentName || meta.name || meta.id,
    model: meta.model,
    role: meta.role,
    stage: meta.stage,
    status: 'pending',
    output: '',
    tools: [],
    sources: [],
  }
}

function sourceKey(source: WorkflowSource): string {
  return source.url || `${source.kind}:${source.title}:${source.subtitle ?? ''}`
}

function mergeSources(current: WorkflowSource[], incoming: WorkflowSource[]): WorkflowSource[] {
  const seen = new Set(current.map(sourceKey))
  const next = [...current]
  for (const source of incoming) {
    const key = sourceKey(source)
    if (!key || seen.has(key)) continue
    seen.add(key)
    next.push(source)
  }
  return next
}

function updateNode(
  state: WorkflowRunFields,
  nodeId: string,
  fn: (node: WorkflowNodeRun) => WorkflowNodeRun,
): WorkflowRunFields {
  let found = false
  const nodes = state.nodes.map((node) => {
    if (node.id !== nodeId) return node
    found = true
    return fn(node)
  })
  if (!found) {
    nodes.push(fn(makeNode({ id: nodeId })))
  }
  return { ...state, nodes }
}

/**
 * The node whose text becomes the final answer: the graph synthesizer or the
 * swarm host. Older transcripts carry no `stage`, so fall back to the reserved
 * node id for the recorded mode.
 */
function isAnswerNode(state: WorkflowRunFields, nodeId: string): boolean {
  const node = state.nodes.find((entry) => entry.id === nodeId)
  if (node?.stage === 'synthesis' || node?.stage === 'host') return true
  if (node?.stage === 'dispatch') return false
  return state.mode === 'swarm' ? nodeId === 'host' : nodeId === 'host-synth'
}

function applyToolStart(node: WorkflowNodeRun, event: Extract<AgentRunEvent, { type: 'tool.start' }>): WorkflowNodeRun {
  const formatted = formatToolInput(event.input)
  const id = event.toolUseId || crypto.randomUUID()
  if (event.toolUseId && node.tools.some((tool) => tool.id === event.toolUseId)) {
    return {
      ...node,
      tools: node.tools.map((tool) =>
        tool.id === event.toolUseId ? { ...tool, input: formatted || tool.input } : tool,
      ),
    }
  }
  const running = !event.toolUseId
    ? [...node.tools].reverse().find((tool) => tool.status === 'running' && tool.name === event.name)
    : undefined
  if (running) {
    return {
      ...node,
      tools: node.tools.map((tool) => (tool.id === running.id ? { ...tool, input: formatted } : tool)),
    }
  }
  const tool: WorkflowToolCall = { id, name: event.name, status: 'running', input: formatted }
  return { ...node, tools: [...node.tools, tool] }
}

function applyInnerEvent(node: WorkflowNodeRun, event: AgentRunEvent): WorkflowNodeRun {
  switch (event.type) {
    case 'text':
      return { ...node, status: 'running', output: node.output + event.data }
    case 'tool.start':
      return { ...applyToolStart(node, event), status: 'running' }
    case 'tool.input': {
      if (!event.toolUseId) return node
      const text = formatToolInput(event.input)
      if (!text) return node
      return {
        ...node,
        tools: node.tools.map((tool) =>
          tool.id === event.toolUseId ? { ...tool, input: text } : tool,
        ),
      }
    }
    case 'tool.stream': {
      if (!event.toolUseId) return node
      const chunk = stringifyToolData(event.data)
      if (!chunk) return node
      return {
        ...node,
        tools: node.tools.map((tool) =>
          tool.id === event.toolUseId ? { ...tool, output: (tool.output ?? '') + chunk } : tool,
        ),
      }
    }
    case 'tool.result': {
      const targetId =
        event.toolUseId ?? [...node.tools].reverse().find((tool) => tool.status === 'running')?.id
      if (!targetId) return node
      const status: WorkflowToolCall['status'] = event.status === 'error' ? 'error' : 'success'
      const incoming: WorkflowSource[] = (event.sources ?? []).map((source, index) => ({
        ...source,
        id: `${targetId}-${index}`,
      }))
      return {
        ...node,
        tools: node.tools.map((tool) =>
          tool.id === targetId
            ? {
                ...tool,
                status,
                output: event.data || tool.output,
                input: event.input ? formatToolInput(event.input) : tool.input,
                sources: incoming.length > 0 ? incoming : tool.sources,
              }
            : tool,
        ),
        sources: mergeSources(node.sources, incoming),
      }
    }
    case 'run.error':
      return { ...node, status: 'error' }
    default:
      return node
  }
}

/** Fold one workflow runtime event into the run state. */
export function reduceWorkflowEvent(
  state: WorkflowRunFields,
  event: WorkflowRunEvent,
): WorkflowRunFields {
  switch (event.type) {
    case 'run.started':
      return { ...state, runId: event.runId, mode: event.mode }

    case 'workflow':
      return {
        ...state,
        mode: event.mode,
        nodes: event.nodes.map((node) => {
          // Older transcripts sent `nodeId`; the current wire shape uses `id`.
          const meta = node as WorkflowRunNodeMeta & { nodeId?: string }
          const id = meta.id ?? meta.nodeId ?? ''
          const normalized: WorkflowRunNodeMeta = { ...meta, id }
          const existing = state.nodes.find((entry) => entry.id === id)
          return existing ? { ...existing, ...makeNode(normalized) } : makeNode(normalized)
        }),
      }

    case 'node.started':
      return updateNode(state, event.nodeId, (node) => ({
        ...node,
        name: event.nodeName || node.name,
        agentName: event.agentName || node.agentName,
        status: 'running',
        startedAt: node.startedAt ?? event.at ?? Date.now(),
      }))

    case 'node.handoff':
      return {
        ...state,
        handoffs: [
          ...state.handoffs,
          {
            id: crypto.randomUUID(),
            from: event.from,
            to: event.to,
            message: event.message,
            at: Date.now(),
          },
        ],
      }

    case 'node.completed':
      return updateNode(state, event.nodeId, (node) => ({
        ...node,
        status: event.status === 'failed' ? 'error' : 'done',
        endedAt: event.at ?? Date.now(),
        usage: event.usage ?? node.usage,
      }))

    case 'node.stream': {
      const next = updateNode(state, event.nodeId, (node) =>
        applyInnerEvent(node, event.event),
      )
      // Stream the final-answer host's text into the answer as it arrives, so
      // the chat types it out. Intermediate agents never stream text.
      if (event.event.type !== 'text' || !isAnswerNode(next, event.nodeId)) {
        return next
      }
      return { ...next, answer: next.answer + event.event.data }
    }

    case 'question':
      return {
        ...state,
        // Any text streamed before the question is preamble, not the answer.
        answer: '',
        status: 'awaiting_input',
        humanQuestion: {
          questionId: event.questionId,
          question: event.question,
          options: event.options ?? [],
          allowCustom: event.allowCustom ?? true,
          ...(event.answer ? { answer: event.answer } : {}),
        },
      }

    case 'trace':
      return {
        ...state,
        traceUrl: event.traceUrl ?? state.traceUrl,
        traceId: event.traceId ?? state.traceId,
      }

    case 'run.completed':
      return {
        ...state,
        status: 'done',
        answer: event.answer ?? state.answer,
        usage: event.usage ?? state.usage,
        endedAt: Date.now(),
        nodes: state.nodes.map((node) =>
          node.status === 'running' ? { ...node, status: 'done', endedAt: Date.now() } : node,
        ),
      }

    case 'run.error':
      return {
        ...state,
        status: 'error',
        error: event.message,
        endedAt: Date.now(),
        nodes: state.nodes.map((node) =>
          node.status === 'running' ? { ...node, status: 'error', endedAt: Date.now() } : node,
        ),
      }

    default:
      return state
  }
}

/** Aggregate every node's sources, numbered globally, for the source list. */
export function runSources(state: WorkflowRunFields): WorkflowSource[] {
  const seen = new Set<string>()
  const sources: WorkflowSource[] = []
  for (const node of state.nodes) {
    for (const source of node.sources) {
      const key = sourceKey(source)
      if (!key || seen.has(key)) continue
      seen.add(key)
      sources.push(source)
    }
  }
  return sources
}

export function markWorkflowStopped(state: WorkflowRunFields): WorkflowRunFields {
  return {
    ...state,
    status: 'stopped',
    endedAt: Date.now(),
    nodes: state.nodes.map((node) =>
      node.status === 'running' ? { ...node, status: 'done', endedAt: Date.now() } : node,
    ),
  }
}

export function markWorkflowError(state: WorkflowRunFields, message: string): WorkflowRunFields {
  return { ...state, status: 'error', error: message, endedAt: Date.now() }
}

/** Resume a paused workflow after the user answered its host's question. */
export function beginWorkflowResume(
  state: WorkflowRunFields,
  answer: string,
): WorkflowRunFields {
  return {
    ...state,
    status: 'streaming',
    error: undefined,
    endedAt: undefined,
    humanQuestion: state.humanQuestion
      ? { ...state.humanQuestion, answer }
      : state.humanQuestion,
  }
}

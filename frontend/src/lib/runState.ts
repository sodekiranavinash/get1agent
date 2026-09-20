/**
 * Shared reducer that turns the runtime's SSE events into UI run state.
 *
 * Both the chat screen and the agent builder consume the same stream, so the
 * plan → todo → tool → answer state machine lives here once and each surface
 * renders it with `RunTimeline`.
 */

import type { AgentPlanTodo, AgentRunEvent, AgentUsage, RunContext } from './agentRun'
import {
  formatToolInput,
  stringifyToolData,
  type ChatPlan,
  type ChatPlanTodo,
  type ChatSource,
  type ChatTodoStatus,
  type ChatToolCall,
  type ChatTurnStatus,
} from './chat'

/** The run fields shared by a chat turn and a builder run. */
export type RunFields = {
  answer: string
  plan: ChatPlan | null
  /** True while the planner is working, before the plan arrives. */
  planning: boolean
  tools: ChatToolCall[]
  /** Citation sources collected across the run's tool calls. */
  sources: ChatSource[]
  status: ChatTurnStatus
  error?: string
  usage?: AgentUsage
  /** Context-window fill for the conversation (used/limit + full flag). */
  context?: RunContext
  startedAt: number
  endedAt?: number
}

export function createRunFields(startedAt = Date.now()): RunFields {
  return {
    answer: '',
    plan: null,
    planning: true,
    tools: [],
    sources: [],
    status: 'streaming',
    startedAt,
  }
}

function makeTodo(todo: AgentPlanTodo, fallbackId: string): ChatPlanTodo {
  return {
    id: todo.id || fallbackId,
    title: todo.title,
    tool: todo.tool,
    query: todo.query,
    status: 'pending',
    tools: [],
  }
}

function makePlan(event: {
  understanding?: string
  subQueries?: { id?: string; query?: string; todos?: AgentPlanTodo[] }[]
}): ChatPlan {
  return {
    understanding: event.understanding ?? '',
    subQueries: (event.subQueries ?? []).map((subQuery, index) => ({
      id: subQuery.id || `sq-${index + 1}`,
      query: subQuery.query ?? '',
      todos: (subQuery.todos ?? []).map((todo, todoIndex) =>
        makeTodo(todo, `${index + 1}.${todoIndex + 1}`),
      ),
    })),
  }
}

function fallbackPlan(): ChatPlan {
  return {
    understanding: '',
    subQueries: [
      {
        id: 'sq-1',
        query: '',
        todos: [
          {
            id: 'working',
            title: 'Working on your request',
            status: 'active',
            tools: [],
          },
        ],
      },
    ],
  }
}

/** Apply `fn` to every todo in the plan, returning a fresh plan. */
function mapTodos(plan: ChatPlan, fn: (todo: ChatPlanTodo) => ChatPlanTodo): ChatPlan {
  return {
    ...plan,
    subQueries: plan.subQueries.map((subQuery) => ({
      ...subQuery,
      todos: subQuery.todos.map(fn),
    })),
  }
}

function plannedTools(planned: string | undefined): string[] {
  return (planned ?? '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean)
}

function toolMatchesOne(name: string, expected: string): boolean {
  const actual = name.toLowerCase()
  const target = expected.toLowerCase()
  if (actual.includes(target) || target.includes(actual)) return true
  const base = actual.split(/[/.]/).filter(Boolean).pop() ?? actual
  return base.includes(target) || target.includes(base)
}

function toolMatches(name: string, planned: string): boolean {
  return plannedTools(planned).some((expected) => toolMatchesOne(name, expected))
}

/**
 * Attach a tool invocation to the right plan step.
 *
 * The plan is ordered, so tool calls are consumed in order: a call stays on the
 * current step while that step still expects it, and the step advances as soon
 * as a call belongs to a later step. This keeps two consecutive steps that use
 * the same tool (e.g. two `web-search` calls) correctly separated.
 */
function attachTool(plan: ChatPlan, tool: ChatToolCall): ChatPlan {
  const subQueries = plan.subQueries.map((subQuery) => ({
    ...subQuery,
    todos: subQuery.todos.map((todo) => ({ ...todo, tools: [...todo.tools] })),
  }))
  const todos = subQueries.flatMap((subQuery) => subQuery.todos)

  const active = todos.find((todo) => todo.status === 'active')
  if (active) {
    const expects = plannedTools(active.tool)
    const used = active.tools.map((entry) => entry.name)
    const remaining = expects.filter(
      (expected) => !used.some((name) => toolMatchesOne(name, expected)),
    )
    const belongsHere =
      expects.length === 0
        ? !todos.some(
            (todo) => todo.status === 'pending' && todo.tool && toolMatches(tool.name, todo.tool),
          )
        : remaining.some((expected) => toolMatchesOne(tool.name, expected))
    if (belongsHere) {
      active.tools.push(tool)
      return { ...plan, subQueries }
    }
    active.status = 'done'
  }

  let target = todos.find(
    (todo) => todo.status === 'pending' && todo.tool && toolMatches(tool.name, todo.tool),
  )
  if (!target) target = todos.find((todo) => todo.status === 'pending')

  if (target) {
    target.status = 'active'
    target.tools.push(tool)
    return { ...plan, subQueries }
  }

  const adhoc: ChatPlanTodo = {
    id: crypto.randomUUID(),
    title: tool.name,
    status: 'active',
    tools: [tool],
  }
  if (subQueries.length > 0) {
    subQueries[subQueries.length - 1].todos.push(adhoc)
  } else {
    subQueries.push({ id: crypto.randomUUID(), query: '', todos: [adhoc] })
  }
  return { ...plan, subQueries }
}

function updateTool(
  plan: ChatPlan | null,
  toolId: string | undefined,
  updater: (tool: ChatToolCall) => ChatToolCall,
): ChatPlan | null {
  if (!plan || !toolId) return plan
  let found = false
  const next = mapTodos(plan, (todo) => {
    if (!todo.tools.some((tool) => tool.id === toolId)) return todo
    found = true
    return {
      ...todo,
      tools: todo.tools.map((tool) => (tool.id === toolId ? updater(tool) : tool)),
    }
  })
  return found ? next : plan
}

function finishTool(
  plan: ChatPlan | null,
  toolId: string | undefined,
  status: ChatToolCall['status'],
  data: string | undefined,
  input?: string,
  sources?: ChatSource[],
): ChatPlan | null {
  if (!plan || !toolId) return plan
  let found = false
  const next = mapTodos(plan, (todo) => {
    if (!todo.tools.some((tool) => tool.id === toolId)) return todo
    found = true
    const tools = todo.tools.map((tool) =>
      tool.id === toolId
        ? { ...tool, status, output: data || tool.output, input: input || tool.input, sources }
        : tool,
    )
    // Keep the step active so further tool calls group under it; it is marked
    // done when the model advances to another step or the run completes.
    const todoStatus: ChatTodoStatus = status === 'error' ? 'error' : 'active'
    return { ...todo, tools, status: todoStatus }
  })
  return found ? next : plan
}

function completePlan(plan: ChatPlan | null): ChatPlan | null {
  if (!plan) return plan
  return mapTodos(plan, (todo) =>
    todo.status === 'error' ? todo : { ...todo, status: 'done' as const },
  )
}

function failActive(plan: ChatPlan | null): ChatPlan | null {
  if (!plan) return plan
  return mapTodos(plan, (todo) =>
    todo.status === 'active' ? { ...todo, status: 'error' as const } : todo,
  )
}

function sourceKey(source: ChatSource): string {
  return source.url || `${source.kind}:${source.title}:${source.subtitle ?? ''}`
}

function mergeSources(current: ChatSource[], incoming: ChatSource[]): ChatSource[] {
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

function applyToolStart<T extends RunFields>(
  state: T,
  event: Extract<AgentRunEvent, { type: 'tool.start' }>,
): T {
  const formatted = formatToolInput(event.input)
  const refresh = (toolId: string): T => ({
    ...state,
    planning: false,
    tools: state.tools.map((tool) =>
      tool.id === toolId ? { ...tool, input: formatted || tool.input } : tool,
    ),
    plan: updateTool(state.plan, toolId, (tool) => ({
      ...tool,
      input: formatted || tool.input,
    })),
  })
  if (event.toolUseId && state.tools.some((tool) => tool.id === event.toolUseId)) {
    return refresh(event.toolUseId)
  }
  const running = !event.toolUseId
    ? [...state.tools]
        .reverse()
        .find((tool) => tool.status === 'running' && tool.name === event.name)
    : undefined
  if (running) return refresh(running.id)

  const tool: ChatToolCall = {
    id: event.toolUseId || crypto.randomUUID(),
    name: event.name,
    status: 'running',
    input: formatted,
  }
  return {
    ...state,
    // Text streamed before a tool call is preamble/narration, never the answer.
    answer: '',
    planning: false,
    tools: [...state.tools, tool],
    plan: attachTool(state.plan ?? fallbackPlan(), tool),
  }
}

function applyToolInput<T extends RunFields>(
  state: T,
  event: Extract<AgentRunEvent, { type: 'tool.input' }>,
): T {
  if (!event.toolUseId) return state
  const text = formatToolInput(event.input)
  if (!text) return state
  return {
    ...state,
    tools: state.tools.map((tool) =>
      tool.id === event.toolUseId ? { ...tool, input: text } : tool,
    ),
    plan: updateTool(state.plan, event.toolUseId, (tool) => ({ ...tool, input: text })),
  }
}

function applyToolStream<T extends RunFields>(
  state: T,
  event: Extract<AgentRunEvent, { type: 'tool.stream' }>,
): T {
  if (!event.toolUseId) return state
  const chunk = stringifyToolData(event.data)
  if (!chunk) return state
  const append = (tool: ChatToolCall): ChatToolCall => ({
    ...tool,
    output: (tool.output ?? '') + chunk,
  })
  return {
    ...state,
    tools: state.tools.map((tool) =>
      tool.id === event.toolUseId ? append(tool) : tool,
    ),
    plan: updateTool(state.plan, event.toolUseId, append),
  }
}

function applyToolResult<T extends RunFields>(
  state: T,
  event: Extract<AgentRunEvent, { type: 'tool.result' }>,
): T {
  const status: ChatToolCall['status'] = event.status === 'error' ? 'error' : 'success'
  const formattedInput = event.input ? formatToolInput(event.input) : undefined
  const targetId =
    event.toolUseId ??
    [...state.tools].reverse().find((tool) => tool.status === 'running')?.id
  if (!targetId) return state

  const incoming: ChatSource[] = (event.sources ?? []).map((source, index) => ({
    ...source,
    id: `${targetId}-${index}`,
  }))
  return {
    ...state,
    tools: state.tools.map((tool) =>
      tool.id === targetId
        ? {
            ...tool,
            status,
            output: event.data || tool.output,
            input: formattedInput || tool.input,
            sources: incoming.length > 0 ? incoming : tool.sources,
          }
        : tool,
    ),
    sources: mergeSources(state.sources, incoming),
    plan: finishTool(state.plan, targetId, status, event.data, formattedInput, incoming),
  }
}

/** Fold one runtime event into the run state. */
export function reduceRunEvent<T extends RunFields>(state: T, event: AgentRunEvent): T {
  switch (event.type) {
    case 'plan.started':
      return { ...state, planning: true }
    case 'plan':
      return { ...state, planning: false, plan: makePlan(event) }
    case 'text':
      return { ...state, answer: state.answer + event.data, planning: false }
    case 'tool.start':
      return applyToolStart(state, event)
    case 'tool.input':
      return applyToolInput(state, event)
    case 'tool.stream':
      return applyToolStream(state, event)
    case 'tool.result':
      return applyToolResult(state, event)
    case 'run.completed':
      return {
        ...state,
        status: 'done',
        usage: event.usage,
        endedAt: Date.now(),
        planning: false,
        plan: completePlan(state.plan),
      }
    case 'context':
      return {
        ...state,
        context: {
          usedTokens: event.usedTokens,
          limitTokens: event.limitTokens,
          ratio: event.ratio,
          full: event.full,
          breakdown: event.breakdown,
        },
      }
    case 'run.error':
      return {
        ...state,
        status: 'error',
        error: event.message,
        endedAt: Date.now(),
        planning: false,
        plan: failActive(state.plan),
      }
    default:
      return state
  }
}

/** Mark a run stopped by the user (client-side abort). */
export function markRunStopped<T extends RunFields>(state: T): T {
  return { ...state, status: 'stopped', endedAt: Date.now() }
}

/** Mark a run failed outside the event stream (transport error). */
export function markRunError<T extends RunFields>(state: T, message: string): T {
  return {
    ...state,
    status: 'error',
    error: message,
    endedAt: Date.now(),
    planning: false,
    plan: failActive(state.plan),
  }
}

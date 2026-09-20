import { useApiClient, type ApiClient } from './api'
import { invalidateQuery, useQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'

export const AGENTS_QUERY_KEY = 'agents'
export const AGENT_LIBRARY_QUERY_KEY = 'agent-library'

// Keep these in sync with backend/services/user-api/handler.py.
export const MAX_AGENTS_PER_USER = 50
export const AGENT_NAME_MIN = 1
export const AGENT_NAME_MAX = 64
export const AGENT_DESCRIPTION_MAX = 1000

export type AgentStatus = 'draft' | 'verified' | 'published'
export type AgentVisibility = 'private' | 'public'
export type AgentSource = 'write' | 'library'
export type AgentReasoning = 'low' | 'medium' | 'high'
export type AgentOutputFormat = 'markdown' | 'text' | 'json'
export type AgentNodeKind =
  | 'input'
  | 'agent'
  | 'knowledge'
  | 'skills'
  | 'tools'
  | 'output'
  | 'schedule'

export type AgentServerSelection = {
  id: string
  name: string
  source: 'builtin' | 'mcp'
  /** `null` means the whole server; a list restricts it to those tools. */
  tools: string[] | null
}

export type AgentSchedule = {
  enabled: boolean
  cron: string
  timezone: string
}

export type AgentMemory = {
  /** Persist durable user memory across sessions for this agent. */
  enabled: boolean
}

export type AgentNodeData = {
  kind: AgentNodeKind
  title: string
  /** The starting user message shown on the input card. */
  input?: string
  /** Storage file ids the user attaches as input alongside the query. */
  inputFileIds?: string[]
  /** Optional starter questions surfaced on the chat screen. */
  defaultQuestions?: string[]
  prompt?: string
  model?: string
  reasoning?: AgentReasoning
  outputFormat?: AgentOutputFormat
  /** How the final answer should be shaped (shown on the output card). */
  outputInstructions?: string
  /** Agent node: enable cross-session user memory. */
  memoryEnabled?: boolean
  knowledgeBaseIds?: string[]
  /** Knowledge node: rerank the hybrid results before returning them. */
  rerank?: boolean
  skillIds?: string[]
  servers?: AgentServerSelection[]
  schedule?: AgentSchedule
}

export type AgentGraphNode = {
  id: string
  type: AgentNodeKind
  position: { x: number; y: number }
  data: AgentNodeData
}

export type AgentGraphEdge = {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
  type?: string
  animated?: boolean
  style?: Record<string, unknown>
  markerEnd?: unknown
  data?: { mode?: 'always' | 'on_demand'; label?: string }
}

export type ConnectionOption = {
  id: string
  name: string
  status: string
  enabled: boolean
  toolCount: number
}

export type AgentGraph = {
  nodes: AgentGraphNode[]
  edges: AgentGraphEdge[]
}

export type AgentConfig = {
  /** Canonical config schema version (bumped when the shape changes). */
  version: number
  prompt: string
  model: string
  reasoning: AgentReasoning
  outputFormat: AgentOutputFormat
  /** Normalized input node (query + attached storage files). */
  input: { query: string; fileIds: string[] }
  /** Optional starter questions shown on the chat screen. */
  defaultQuestions: string[]
  /** Normalized output node. */
  output: { format: AgentOutputFormat; instructions: string }
  knowledgeBaseIds: string[]
  /** Whether the agent reranks knowledge retrieval results (opt-in). */
  knowledgeRerank: boolean
  skillIds: string[]
  servers: AgentServerSelection[]
  /** Cross-session user memory. */
  memory: AgentMemory
  schedule: AgentSchedule
  graph: AgentGraph
}

export type Agent = {
  id: string
  name: string
  description: string
  status: AgentStatus
  visibility: AgentVisibility
  source: AgentSource
  version: number
  model: string | null
  reasoning: AgentReasoning | null
  outputFormat: AgentOutputFormat | null
  defaultQuestions: string[]
  nodeCount: number
  knowledgeBaseCount: number
  skillCount: number
  serverCount: number
  schedule: AgentSchedule | null
  verifiedAt: string | null
  lastRunAt: string | null
  publishedAt: string | null
  installCount: number
  forkedFrom: string | null
  createdAt: string
  updatedAt: string
  isMine?: boolean
}

export type AgentDetail = Agent & { config: AgentConfig }

export type AgentList = {
  agents: Agent[]
  usage: { agents: number; limits: { agents: number } }
}

export type AgentLibraryList = { agents: Agent[] }

export type AgentVerifyResult = {
  valid: boolean
  errors: string[]
  warnings: string[]
  agent: AgentDetail
}

export type AgentPayload = {
  name: string
  description: string
  config: AgentConfig
}

export type AgentDraft = {
  name: string
  description: string
  config: AgentConfig
}

// --- reference data ----------------------------------------------------------

/** Canonical config schema version. Keep in sync with the backend. */
export const AGENT_CONFIG_VERSION = 2

// Curated OpenCode Go models (OpenAI-compatible `/chat/completions`), ordered
// cheapest/fastest first. Keep the ids in sync with SUPPORTED_AGENT_MODELS in
// backend/services/user-api/handler.py. `contextWindow` mirrors the runtime's
// `agentflow/models.py` map (the context meter uses it before a run reports the
// exact fill).
export const AGENT_MODELS = [
  { id: 'mimo-v2.5', label: 'MiMo V2.5', blurb: 'Cheapest · everyday', contextWindow: 128_000 },
  { id: 'glm-5.3-flash', label: 'GLM 5.3 Flash', blurb: 'Fast · balanced', contextWindow: 128_000 },
  { id: 'qwen3.8-flash', label: 'Qwen3.8 Flash', blurb: 'Fast · long context', contextWindow: 128_000 },
  {
    id: 'deepseek-v4-flash-vision-exp',
    label: 'DeepSeek V4 Flash Vision Exp',
    blurb: 'Vision · fast · experimental',
    contextWindow: 128_000,
  },
  { id: 'gpt-5.6-luna', label: 'GPT 5.6 Luna', blurb: 'OpenAI · precise', contextWindow: 1_050_000 },
  { id: 'kimi-k2.6', label: 'Kimi K2.6', blurb: 'Strong reasoning', contextWindow: 256_000 },
] as const

export const DEFAULT_AGENT_CONTEXT_WINDOW = 128_000

export function agentModelContextWindow(model?: string | null): number {
  return AGENT_MODELS.find((entry) => entry.id === model)?.contextWindow ?? DEFAULT_AGENT_CONTEXT_WINDOW
}

export const AGENT_REASONING_LEVELS: AgentReasoning[] = ['low', 'medium', 'high']

export const AGENT_OUTPUT_FORMATS: AgentOutputFormat[] = ['markdown', 'text', 'json']

export const DEFAULT_AGENT_MODEL = AGENT_MODELS[0].id

/** Map a saved (possibly legacy) model id onto a supported one. */
export function resolveAgentModel(model?: string | null): string {
  return AGENT_MODELS.some((entry) => entry.id === model)
    ? (model as string)
    : DEFAULT_AGENT_MODEL
}

export const DEFAULT_AGENT_SCHEDULE: AgentSchedule = {
  enabled: false,
  cron: '',
  timezone: 'UTC',
}

export type AgentScheduleFrequency = 'hourly' | 'daily' | 'weekdays' | 'weekly' | 'monthly'

export type AgentScheduleParts = {
  frequency: AgentScheduleFrequency
  /** Minute of the hour, 0-59. */
  minute: number
  /** Hour of the day, 0-23. Ignored for hourly. */
  hour: number
  /** Day of week, 0 = Sunday … 6 = Saturday. Only used by weekly. */
  weekday: number
  /** Day of month, 1-28. Only used by monthly. */
  dayOfMonth: number
}

export const SCHEDULE_WEEKDAY_LABELS = [
  'Sunday',
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
]

export const SCHEDULE_FREQUENCIES: { value: AgentScheduleFrequency; label: string }[] = [
  { value: 'hourly', label: 'Every hour' },
  { value: 'daily', label: 'Every day' },
  { value: 'weekdays', label: 'Every weekday (Mon–Fri)' },
  { value: 'weekly', label: 'Every week' },
  { value: 'monthly', label: 'Every month' },
]

export const SCHEDULE_HOURS = Array.from({ length: 24 }, (_, hour) => hour)
export const SCHEDULE_MINUTES = Array.from({ length: 60 }, (_, index) => index)
export const SCHEDULE_DAYS_OF_MONTH = Array.from({ length: 28 }, (_, index) => index + 1)

export const DEFAULT_SCHEDULE_PARTS: AgentScheduleParts = {
  frequency: 'daily',
  minute: 0,
  hour: 9,
  weekday: 1,
  dayOfMonth: 1,
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

/** Compose a 5-field cron expression from the builder selections. */
export function cronFromParts(parts: AgentScheduleParts): string {
  switch (parts.frequency) {
    case 'hourly':
      return `${parts.minute} * * * *`
    case 'weekdays':
      return `${parts.minute} ${parts.hour} * * 1-5`
    case 'weekly':
      return `${parts.minute} ${parts.hour} * * ${parts.weekday}`
    case 'monthly':
      return `${parts.minute} ${parts.hour} ${parts.dayOfMonth} * *`
    case 'daily':
    default:
      return `${parts.minute} ${parts.hour} * * *`
  }
}

/** Parse a cron expression back into builder selections, or null when custom. */
export function partsFromCron(cron: string): AgentScheduleParts | null {
  const fields = cron.trim().split(/\s+/)
  if (fields.length !== 5) return null
  const [minuteField, hourField, dayField, monthField, weekdayField] = fields
  if (!/^\d{1,2}$/.test(minuteField)) return null
  const minute = Number(minuteField)
  if (minute > 59) return null
  if (monthField !== '*') return null

  if (hourField === '*') {
    if (dayField !== '*' || weekdayField !== '*') return null
    return { ...DEFAULT_SCHEDULE_PARTS, frequency: 'hourly', minute }
  }

  if (!/^\d{1,2}$/.test(hourField)) return null
  const hour = Number(hourField)
  if (hour > 23) return null

  if (dayField === '*' && weekdayField === '*') {
    return { ...DEFAULT_SCHEDULE_PARTS, frequency: 'daily', minute, hour }
  }
  if (dayField === '*' && weekdayField === '1-5') {
    return { ...DEFAULT_SCHEDULE_PARTS, frequency: 'weekdays', minute, hour }
  }
  if (dayField === '*' && /^[0-6]$/.test(weekdayField)) {
    return { ...DEFAULT_SCHEDULE_PARTS, frequency: 'weekly', minute, hour, weekday: Number(weekdayField) }
  }
  if (weekdayField === '*' && /^\d{1,2}$/.test(dayField)) {
    const dayOfMonth = Number(dayField)
    if (dayOfMonth < 1 || dayOfMonth > 28) return null
    return { ...DEFAULT_SCHEDULE_PARTS, frequency: 'monthly', minute, hour, dayOfMonth }
  }
  return null
}

/** Human-readable one-liner for a cron expression (used on the card). */
export function describeSchedule(cron: string): string {
  const parts = partsFromCron(cron)
  if (!parts) return cron
  const time = `${pad2(parts.hour)}:${pad2(parts.minute)}`
  switch (parts.frequency) {
    case 'hourly':
      return parts.minute === 0 ? 'Every hour' : `Every hour at :${pad2(parts.minute)}`
    case 'daily':
      return `Every day at ${time}`
    case 'weekdays':
      return `Every weekday at ${time}`
    case 'weekly':
      return `Every ${SCHEDULE_WEEKDAY_LABELS[parts.weekday]} at ${time}`
    case 'monthly':
      return `Monthly on day ${parts.dayOfMonth} at ${time}`
  }
}

/** 24-hour time as a friendly 12-hour clock label, e.g. 13:05 -> "1:05 PM". */
export function formatClock12(hour: number, minute: number): string {
  const period = hour < 12 ? 'AM' : 'PM'
  const display = hour % 12 === 0 ? 12 : hour % 12
  return `${display}:${pad2(minute)} ${period}`
}

const WEEKDAY_INDEX: Record<string, number> = {
  Sun: 0,
  Mon: 1,
  Tue: 2,
  Wed: 3,
  Thu: 4,
  Fri: 5,
  Sat: 6,
}

const tzFormatters = new Map<string, Intl.DateTimeFormat>()

function tzFormatter(timeZone: string): Intl.DateTimeFormat {
  let formatter = tzFormatters.get(timeZone)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat('en-US', {
      timeZone,
      hourCycle: 'h23',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      weekday: 'short',
    })
    tzFormatters.set(timeZone, formatter)
  }
  return formatter
}

type ZonedParts = { year: number; month: number; day: number; hour: number; minute: number; weekday: number }

function zonedParts(date: Date, timeZone: string): ZonedParts {
  const parts = tzFormatter(timeZone).formatToParts(date)
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? '0'
  return {
    year: Number(value('year')),
    month: Number(value('month')),
    day: Number(value('day')),
    hour: Number(value('hour')),
    minute: Number(value('minute')),
    weekday: WEEKDAY_INDEX[value('weekday')] ?? 0,
  }
}

function timeZoneOffset(ts: number, timeZone: string): number {
  const local = zonedParts(new Date(ts), timeZone)
  const asUtc = Date.UTC(local.year, local.month - 1, local.day, local.hour, local.minute)
  return asUtc - ts
}

/** Convert a wall-clock time in `timeZone` to a UTC instant (DST-safe). */
function zonedWallTimeToTs(
  year: number,
  month: number,
  day: number,
  hour: number,
  minute: number,
  timeZone: string,
): number {
  const guess = Date.UTC(year, month - 1, day, hour, minute)
  const offset = timeZoneOffset(guess, timeZone)
  let ts = guess - offset
  const refined = timeZoneOffset(ts, timeZone)
  if (refined !== offset) ts = guess - refined
  return ts
}

/** The next `count` instants the schedule will fire, in chronological order. */
export function nextScheduleRuns(
  parts: AgentScheduleParts,
  timeZone: string,
  count = 3,
  from: Date = new Date(),
): Date[] {
  try {
    const now = from.getTime()
    const runs: number[] = []
    const consider = (year: number, month: number, day: number, hour: number, minute: number) => {
      const ts = zonedWallTimeToTs(year, month, day, hour, minute, timeZone)
      if (ts > now) runs.push(ts)
    }

    if (parts.frequency === 'hourly') {
      for (let i = 0; i < 26 && runs.length < count; i += 1) {
        const p = zonedParts(new Date(now + i * 3_600_000), timeZone)
        consider(p.year, p.month, p.day, p.hour, parts.minute)
      }
    } else if (parts.frequency === 'daily' || parts.frequency === 'weekdays') {
      for (let i = 0; i < 16 && runs.length < count; i += 1) {
        const p = zonedParts(new Date(now + i * 86_400_000), timeZone)
        if (parts.frequency === 'weekdays' && (p.weekday === 0 || p.weekday === 6)) continue
        consider(p.year, p.month, p.day, parts.hour, parts.minute)
      }
    } else if (parts.frequency === 'weekly') {
      for (let i = 0; i < 60 && runs.length < count; i += 1) {
        const p = zonedParts(new Date(now + i * 86_400_000), timeZone)
        if (p.weekday !== parts.weekday) continue
        consider(p.year, p.month, p.day, parts.hour, parts.minute)
      }
    } else {
      const start = zonedParts(from, timeZone)
      let year = start.year
      let month = start.month
      for (let i = 0; i < 24 && runs.length < count; i += 1) {
        consider(year, month, parts.dayOfMonth, parts.hour, parts.minute)
        month += 1
        if (month > 12) {
          month = 1
          year += 1
        }
      }
    }

    return runs
      .sort((a, b) => a - b)
      .slice(0, count)
      .map((ts) => new Date(ts))
  } catch {
    return []
  }
}

/** Format a run instant in the schedule's timezone, e.g. "Mon, Sep 22, 9:00 AM". */
export function formatScheduleRun(date: Date, timeZone: string): string {
  try {
    return new Intl.DateTimeFormat(undefined, {
      timeZone,
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    }).format(date)
  } catch {
    return date.toISOString()
  }
}

/** Every IANA timezone the browser knows, UTC first. */
export const AGENT_TIMEZONES: string[] = (() => {
  try {
    const zones = Intl.supportedValuesOf('timeZone')
    return ['UTC', ...zones.filter((zone) => zone !== 'UTC')]
  } catch {
    return ['UTC', 'America/New_York', 'America/Los_Angeles', 'Europe/London', 'Asia/Kolkata']
  }
})()

export const BUILTIN_AGENT_SERVERS = [
  { id: 'code-interpreter', name: 'Code Interpreter' },
  { id: 'web-search', name: 'Web Search' },
] as const

export function agentModelLabel(model: string | null | undefined): string {
  return AGENT_MODELS.find((entry) => entry.id === model)?.label ?? model ?? 'Model'
}

// --- graph helpers -----------------------------------------------------------

const NODE_TITLES: Record<AgentNodeKind, string> = {
  input: 'Input',
  agent: 'Agent',
  knowledge: 'Knowledge',
  skills: 'Skills',
  tools: 'MCP tools',
  output: 'Output',
  schedule: 'Schedule',
}

export function defaultNodeData(kind: AgentNodeKind): AgentNodeData {
  switch (kind) {
    case 'agent':
      return {
        kind,
        title: NODE_TITLES.agent,
        prompt: '',
        model: DEFAULT_AGENT_MODEL,
        reasoning: 'medium',
        memoryEnabled: false,
      }
    case 'output':
      return {
        kind,
        title: NODE_TITLES.output,
        outputFormat: 'markdown',
        outputInstructions: '',
      }
    case 'knowledge':
      return { kind, title: NODE_TITLES.knowledge, knowledgeBaseIds: [], rerank: false }
    case 'skills':
      return { kind, title: NODE_TITLES.skills, skillIds: [] }
    case 'tools':
      return { kind, title: NODE_TITLES.tools, servers: [] }
    case 'schedule':
      return { kind, title: NODE_TITLES.schedule, schedule: { ...DEFAULT_AGENT_SCHEDULE } }
    case 'input':
    default:
      return { kind, title: NODE_TITLES.input, input: '', defaultQuestions: [] }
  }
}

export function createNode(
  kind: AgentNodeKind,
  position: { x: number; y: number },
  data?: Partial<AgentNodeData>,
): AgentGraphNode {
  return {
    id: `${kind}-${Math.random().toString(36).slice(2, 8)}`,
    type: kind,
    position,
    data: { ...defaultNodeData(kind), ...data },
  }
}

/**
 * Default canvas positions — input on top, output on the bottom, schedule on
 * the left, and knowledge / MCP tools / skills stacked down the right, with the
 * agent in the middle.
 */
// The agent sits in the exact middle of the layout, with the same gap (156px)
// on its left to the schedule and on its right to the knowledge/tools/skills
// column, so the whole graph is balanced.
const DEFAULT_POSITIONS: Record<AgentNodeKind, { x: number; y: number }> = {
  input: { x: 420, y: 0 },
  agent: { x: 420, y: 170 },
  output: { x: 420, y: 340 },
  schedule: { x: 0, y: 170 },
  knowledge: { x: 840, y: 0 },
  tools: { x: 840, y: 170 },
  skills: { x: 840, y: 340 },
}

const ALL_NODE_KINDS: AgentNodeKind[] = [
  'input',
  'agent',
  'knowledge',
  'skills',
  'tools',
  'schedule',
  'output',
]

// Every connection is the same quiet dotted link: no arrowhead and no motion,
// so nothing reads as "data flowing" in a particular direction.
const LINK_EDGE = {
  // "default" is React Flow's bezier edge type.
  type: 'default',
  style: {
    stroke: 'var(--app-accent)',
    strokeWidth: 1.5,
    strokeDasharray: '2 6',
    strokeLinecap: 'round',
  },
}

function makeEdge(
  source: AgentGraphNode,
  target: AgentGraphNode,
  sourceHandle?: string,
  targetHandle?: string,
): AgentGraphEdge {
  return {
    id: `e-${source.id}-${target.id}`,
    source: source.id,
    target: target.id,
    ...(sourceHandle ? { sourceHandle } : {}),
    ...(targetHandle ? { targetHandle } : {}),
    ...LINK_EDGE,
    data: { mode: 'always' },
  }
}

/**
 * The canonical wiring: input (top) and schedule (left) connect to the agent;
 * the agent connects to knowledge, MCP tools and skills (right) and the output
 * (bottom).
 */
export function canonicalEdges(nodes: AgentGraphNode[]): AgentGraphEdge[] {
  const byKind = (kind: AgentNodeKind) => nodes.find((node) => node.type === kind)
  const agent = byKind('agent')
  if (!agent) return []

  const edges: AgentGraphEdge[] = []
  const input = byKind('input')
  const schedule = byKind('schedule')
  const output = byKind('output')
  if (input) edges.push(makeEdge(input, agent, undefined, 'top'))
  if (schedule) edges.push(makeEdge(schedule, agent, undefined, 'left'))
  ;(['knowledge', 'tools', 'skills'] as AgentNodeKind[]).forEach((kind) => {
    const node = byKind(kind)
    if (node) edges.push(makeEdge(agent, node, 'right'))
  })
  if (output) edges.push(makeEdge(agent, output, 'bottom'))
  return edges
}

/** The default canvas: all element cards are added up front. */
export function defaultAgentGraph(): AgentGraph {
  const nodes = ALL_NODE_KINDS.map((kind) => createNode(kind, DEFAULT_POSITIONS[kind]))
  return { nodes, edges: canonicalEdges(nodes) }
}

/** Guarantee every single-instance card exists (older graphs may lack some). */
export function ensureAllNodes(graph: AgentGraph): AgentGraph {
  const present = new Set(graph.nodes.map((node) => node.type))
  const missing = ALL_NODE_KINDS.filter((kind) => !present.has(kind))
  if (missing.length === 0) return graph
  const nodes = [...graph.nodes]
  missing.forEach((kind) => nodes.push(createNode(kind, DEFAULT_POSITIONS[kind])))
  return { nodes, edges: graph.edges }
}

/** Rebuild the canvas from a saved config at the canonical layout. */
export function graphFromConfig(config: AgentConfig): AgentGraph {
  const saved = config.graph
  const savedNodes = saved && saved.nodes.length > 0 ? saved.nodes : null

  const base = savedNodes
    ? savedNodes.map((node) => ({
        ...node,
        // Cards always live at their specified spot; only content is restored.
        position: DEFAULT_POSITIONS[node.type] ?? node.position,
        // Titles are fixed per kind (e.g. the input card is always "Input").
        data: {
          ...defaultNodeData(node.type),
          ...node.data,
          kind: node.type,
          title: NODE_TITLES[node.type],
        },
      }))
    : defaultAgentGraph().nodes

  const nodes = ensureAllNodes({ nodes: base, edges: [] }).nodes

  // The flat top-level config is canonical; the graph is rebuilt from it so a
  // config saved by any app renders identically in the builder.
  const populated = nodes.map((node) => {
    switch (node.type) {
      case 'agent':
        return {
          ...node,
          data: {
            ...node.data,
            prompt: config.prompt,
            model: resolveAgentModel(config.model),
            reasoning: config.reasoning,
            memoryEnabled: config.memory?.enabled ?? false,
          },
        }
      case 'input':
        return {
          ...node,
          data: {
            ...node.data,
            input: config.input?.query ?? '',
            inputFileIds: config.input?.fileIds ?? [],
            defaultQuestions: config.defaultQuestions ?? [],
          },
        }
      case 'output':
        return {
          ...node,
          data: {
            ...node.data,
            outputFormat: config.output?.format ?? config.outputFormat,
            outputInstructions: config.output?.instructions ?? '',
          },
        }
      case 'knowledge':
        return {
          ...node,
          data: {
            ...node.data,
            knowledgeBaseIds: config.knowledgeBaseIds ?? [],
            rerank: config.knowledgeRerank ?? false,
          },
        }
      case 'skills':
        return { ...node, data: { ...node.data, skillIds: config.skillIds ?? [] } }
      case 'tools':
        return { ...node, data: { ...node.data, servers: config.servers ?? [] } }
      case 'schedule':
        return { ...node, data: { ...node.data, schedule: config.schedule } }
      default:
        return node
    }
  })

  return { nodes: populated, edges: canonicalEdges(populated) }
}

/** Derive the persistable config from the canvas (single source of truth). */
export function configFromGraph(
  nodes: AgentGraphNode[],
  edges: AgentGraphEdge[],
): AgentConfig {
  const byKind = (kind: AgentNodeKind) => nodes.find((node) => node.type === kind)
  const agent = byKind('agent')
  const input = byKind('input')
  const output = byKind('output')
  const knowledge = byKind('knowledge')
  const skills = byKind('skills')
  const tools = byKind('tools')
  const schedule = byKind('schedule')

  const outputFormat = output?.data.outputFormat ?? agent?.data.outputFormat ?? 'markdown'

  return {
    version: AGENT_CONFIG_VERSION,
    prompt: agent?.data.prompt ?? '',
    model: agent?.data.model ?? DEFAULT_AGENT_MODEL,
    reasoning: agent?.data.reasoning ?? 'medium',
    outputFormat,
    input: {
      query: input?.data.input ?? '',
      fileIds: input?.data.inputFileIds ?? [],
    },
    defaultQuestions: input?.data.defaultQuestions ?? [],
    output: {
      format: outputFormat,
      instructions: output?.data.outputInstructions ?? '',
    },
    knowledgeBaseIds: knowledge?.data.knowledgeBaseIds ?? [],
    knowledgeRerank: knowledge?.data.rerank ?? false,
    skillIds: skills?.data.skillIds ?? [],
    servers: tools?.data.servers ?? [],
    memory: { enabled: agent?.data.memoryEnabled ?? false },
    schedule: schedule?.data.schedule ?? { ...DEFAULT_AGENT_SCHEDULE },
    graph: {
      nodes: nodes.map((node) => ({
        id: node.id,
        type: node.type,
        position: node.position,
        data: node.data,
      })),
      edges: edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        sourceHandle: edge.sourceHandle ?? undefined,
        targetHandle: edge.targetHandle ?? undefined,
        data: edge.data,
      })),
    },
  }
}

export function emptyAgentConfig(): AgentConfig {
  return configFromGraph(defaultAgentGraph().nodes, defaultAgentGraph().edges)
}

// --- event log ---------------------------------------------------------------

export type AgentEventKind = 'info' | 'success' | 'warning' | 'error' | 'tool'

export type AgentEventInput = {
  kind: AgentEventKind
  title: string
  detail?: string
  /** Run/test lifecycle events (test run, publish, load) — the History tab. */
  scope?: 'milestone'
}

export type AgentEvent = AgentEventInput & { id: string; at: string }

/** Returns a human-readable error, or null when the name is valid. */
export function validateAgentName(value: string): string | null {
  const name = value.trim()
  if (!name) return 'Name is required'
  if (name.length > AGENT_NAME_MAX) return `Name must be at most ${AGENT_NAME_MAX} characters`
  if (!/^[a-z0-9-]+$/.test(name)) {
    return 'Only lowercase letters, numbers and hyphens (no spaces or special characters)'
  }
  if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(name)) {
    return 'Must start and end with a letter or number'
  }
  return null
}

/** Returns a human-readable error, or null when the description is valid. */
export function validateAgentDescription(value: string): string | null {
  const description = value.trim()
  if (!description) return 'Description is required'
  if (description.length > AGENT_DESCRIPTION_MAX) {
    return `Description must be at most ${AGENT_DESCRIPTION_MAX} characters`
  }
  return null
}

// --- draft persistence (localStorage) ---------------------------------------

// Bump the version whenever the default canvas layout changes, so a stale
// draft from an older layout is not restored instead of the new one.
function draftKey(agentId: string | null): string {
  return `agent-builder-draft:v2:${agentId ?? 'new'}`
}

export function saveAgentDraft(agentId: string | null, draft: AgentDraft): void {
  try {
    localStorage.setItem(draftKey(agentId), JSON.stringify(draft))
  } catch {
    // Storage may be unavailable (private mode); autosave is best-effort.
  }
}

export function loadAgentDraft(agentId: string | null): AgentDraft | null {
  try {
    const raw = localStorage.getItem(draftKey(agentId))
    if (!raw) return null
    return JSON.parse(raw) as AgentDraft
  } catch {
    return null
  }
}

export function clearAgentDraft(agentId: string | null): void {
  try {
    localStorage.removeItem(draftKey(agentId))
  } catch {
    // ignore
  }
}

// --- API calls ---------------------------------------------------------------

export async function createAgent(api: ApiClient, payload: AgentPayload): Promise<AgentDetail> {
  return api.post<AgentDetail>('/v1/agents', payload)
}

export async function fetchAgent(api: ApiClient, id: string): Promise<AgentDetail> {
  return api.get<AgentDetail>(`/v1/agents/${id}`)
}

export async function updateAgent(
  api: ApiClient,
  id: string,
  payload: AgentPayload,
): Promise<AgentDetail> {
  return api.put<AgentDetail>(`/v1/agents/${id}`, payload)
}

export async function deleteAgent(api: ApiClient, id: string): Promise<void> {
  await api.delete(`/v1/agents/${id}`)
}

export async function verifyAgent(api: ApiClient, id: string): Promise<AgentVerifyResult> {
  return api.post<AgentVerifyResult>(`/v1/agents/${id}/verify`)
}

export async function publishAgent(api: ApiClient, id: string): Promise<AgentDetail> {
  return api.post<AgentDetail>(`/v1/agents/${id}/publish`)
}

export async function unpublishAgent(api: ApiClient, id: string): Promise<AgentDetail> {
  return api.post<AgentDetail>(`/v1/agents/${id}/unpublish`)
}

export async function installAgent(api: ApiClient, id: string): Promise<AgentDetail> {
  return api.post<AgentDetail>(`/v1/agents/library/${id}/install`)
}

// --- hooks -------------------------------------------------------------------

export function useAgents() {
  const api = useApiClient()
  return usePageQuery(
    AGENTS_QUERY_KEY,
    () => api.get<AgentList>('/v1/agents'),
    { refetchOnMount: true },
  )
}

export function invalidateAgents(): void {
  invalidateQuery(AGENTS_QUERY_KEY)
  invalidateQuery(AGENT_LIBRARY_QUERY_KEY)
}

export function useAgentLibrary() {
  const api = useApiClient()
  return usePageQuery(
    AGENT_LIBRARY_QUERY_KEY,
    () => api.get<AgentLibraryList>('/v1/agents/library'),
    { refetchOnMount: true },
  )
}

/** MCP connections the tools node can attach (id + name only). */
export function useMcpConnectionOptions() {
  const api = useApiClient()
  return useQuery('agent-builder-mcp-connections', async () => {
    const response = await api.get<{
      connections: { id: string; name: string; status: string; enabled: boolean; toolCount: number }[]
    }>('/v1/mcp/connections')
    return response.connections
  })
}

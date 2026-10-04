import { useApiClient, type ApiClient } from './api'
import { invalidateQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'
import {
  AGENT_MODELS,
  DEFAULT_AGENT_MODEL,
  DEFAULT_AGENT_SCHEDULE,
  agentModelLabel,
  resolveAgentModel,
  type Agent,
  type AgentGuardrail,
  type AgentOutputFormat,
  type AgentReasoning,
  type AgentSchedule,
  type AgentServerSelection,
} from './agents'

export const WORKFLOWS_QUERY_KEY = 'workflows'

// Keep these in sync with backend/services/apis/user-api/handler.py.
export const MAX_WORKFLOWS_PER_USER = 50
export const MAX_WORKFLOW_AGENTS = 10
export const WORKFLOW_NAME_MAX = 64
export const WORKFLOW_DESCRIPTION_MAX = 1000
export const WORKFLOW_CONFIG_VERSION = 1

export type WorkflowMode = 'graph' | 'swarm'
export type WorkflowStatus = 'draft' | 'verified'
export type WorkflowNodeKind = 'input' | 'agent' | 'output' | 'schedule'

/** Per-workflow overrides for a referenced agent (only changed fields). */
export type WorkflowOverrides = {
  model?: string
  prompt?: string
  reasoning?: AgentReasoning
  servers?: AgentServerSelection[]
  skillIds?: string[]
}

export type WorkflowNodeData = {
  kind: WorkflowNodeKind
  /** Input/host node: the starting query. */
  query?: string
  /** Input/host node: the workflow's system prompt. */
  prompt?: string
  /** Input/host node: the host's model. */
  model?: string
  /** Input/host node: the workflow's guardrail (host + fallback for members). */
  guardrailEnabled?: boolean
  guardrailId?: string
  /** Agent node: the referenced saved agent + per-workflow overrides. */
  agentId?: string
  agentName?: string
  overrides?: WorkflowOverrides
  /** Output node: how the final answer is shaped. */
  format?: AgentOutputFormat
  instructions?: string
  /** Schedule node: stored on the workflow (attached to the host). */
  schedule?: AgentSchedule
}

export type WorkflowGraphNode = {
  id: string
  type: WorkflowNodeKind
  position: { x: number; y: number }
  data: WorkflowNodeData
  /** Structural cards (query/schedule/output) are pinned in place. */
  draggable?: boolean
}

export type WorkflowGraphEdge = {
  id: string
  source: string
  target: string
  sourceHandle?: string | null
  targetHandle?: string | null
}

/**
 * Handle ids. The host (input) has three: schedule in on the left, agents out
 * on the right and output out at the bottom. Every other card has one in/out.
 */
export const WORKFLOW_HANDLE = {
  hostScheduleIn: 'schedule-in',
  hostAgentsOut: 'agents-out',
  hostOutputOut: 'output-out',
  nodeIn: 'in',
  nodeOut: 'out',
} as const

function edgeHandles(
  sourceType: WorkflowNodeKind,
  targetType: WorkflowNodeKind,
): { sourceHandle: string; targetHandle: string } {
  const sourceHandle =
    sourceType === 'input'
      ? targetType === 'output'
        ? WORKFLOW_HANDLE.hostOutputOut
        : WORKFLOW_HANDLE.hostAgentsOut
      : WORKFLOW_HANDLE.nodeOut
  const targetHandle =
    targetType === 'input' ? WORKFLOW_HANDLE.hostScheduleIn : WORKFLOW_HANDLE.nodeIn
  return { sourceHandle, targetHandle }
}

export type WorkflowConfig = {
  version: number
  mode: WorkflowMode
  /** The input card is the host agent: its query, system prompt and model. */
  input: { query: string; prompt: string; model: string }
  output: { format: AgentOutputFormat; instructions: string }
  /** Stored on the workflow; the schedule node is attached to the host. */
  schedule: AgentSchedule
  /** The workflow's guardrail: applied to the host, inherited by members. */
  guardrail: AgentGuardrail
  nodes: WorkflowGraphNode[]
  edges: WorkflowGraphEdge[]
}

export type Workflow = {
  id: string
  name: string
  description: string
  status: WorkflowStatus
  mode: WorkflowMode
  version: number
  agentCount: number
  agentIds: string[]
  nodeCount: number
  schedule: AgentSchedule | null
  verifiedAt: string | null
  lastRunAt: string | null
  createdAt: string
  updatedAt: string
}

export type WorkflowDetail = Workflow & { config: WorkflowConfig }
export type WorkflowList = {
  workflows: Workflow[]
  usage: { workflows: number; limits: { workflows: number } }
}
export type WorkflowVerifyResult = {
  valid: boolean
  errors: string[]
  warnings: string[]
  workflow: WorkflowDetail
}
export type WorkflowPayload = {
  name: string
  description: string
  config: WorkflowConfig
}
export type WorkflowDraft = WorkflowPayload

export const WORKFLOW_MODES: { value: WorkflowMode; label: string; blurb: string }[] = [
  {
    value: 'graph',
    label: 'Graph',
    blurb: 'Deterministic. Agents run in the order you wire them; each output flows to the next.',
  },
  {
    value: 'swarm',
    label: 'Swarm',
    blurb: 'Dynamic. A host agent decides which teammate to hand off to at each step.',
  },
]

export function workflowModeLabel(mode: WorkflowMode): string {
  return WORKFLOW_MODES.find((entry) => entry.value === mode)?.label ?? mode
}

export function workflowModeBlurb(mode: WorkflowMode): string {
  return WORKFLOW_MODES.find((entry) => entry.value === mode)?.blurb ?? ''
}

// --- layout ------------------------------------------------------------------

export const WORKFLOW_NODE_WIDTH = 220
export const WORKFLOW_NODE_HEIGHT = 68

/**
 * Default positions: a tight vertical stack on the left of the canvas — the
 * schedule sits on top of the query, with the output below it — and the created
 * agents stack to the right.
 */
export const WORKFLOW_LAYOUT = {
  schedule: { x: 0, y: -96 },
  input: { x: 0, y: 0 },
  output: { x: 0, y: 96 },
  // The agent column starts high enough that a full set of ten agents is
  // vertically centred on the query card.
  firstAgent: { x: 300, y: -351 },
  agentGapX: 0,
  agentGapY: 78,
  perRow: 1,
}

export function nextAgentPosition(count: number): { x: number; y: number } {
  const column = count % WORKFLOW_LAYOUT.perRow
  const row = Math.floor(count / WORKFLOW_LAYOUT.perRow)
  return {
    x: WORKFLOW_LAYOUT.firstAgent.x + column * WORKFLOW_LAYOUT.agentGapX,
    y: WORKFLOW_LAYOUT.firstAgent.y + row * WORKFLOW_LAYOUT.agentGapY,
  }
}

/** Where the `index`-th of `count` agents sits in the centred column. */
export function agentColumnPosition(
  index: number,
  count: number,
): { x: number; y: number } {
  const gap = WORKFLOW_LAYOUT.agentGapY
  const total = Math.max(1, count) * gap - (gap - WORKFLOW_NODE_HEIGHT)
  const center = WORKFLOW_LAYOUT.input.y + WORKFLOW_NODE_HEIGHT / 2
  const start = center - total / 2
  return { x: WORKFLOW_LAYOUT.firstAgent.x, y: Math.round(start + index * gap) }
}

/**
 * Lay every agent node out in a single column vertically centred on the query
 * card, so a full set of ten agents stays perfectly aligned.
 */
export function arrangeAgentColumn(nodes: WorkflowGraphNode[]): WorkflowGraphNode[] {
  const agents = nodes.filter((node) => node.type === 'agent')
  if (agents.length === 0) return nodes
  const positions = new Map(
    agents.map((node, index) => [node.id, agentColumnPosition(index, agents.length)]),
  )
  return nodes.map((node) => {
    const position = positions.get(node.id)
    return position ? { ...node, position } : node
  })
}

/**
 * The 1-based execution order of the agent nodes in graph mode.
 *
 * A topological sort over the agent→agent edges; agents with no edges (or ties)
 * are ordered by their canvas position so the numbering matches the layout.
 */
export function topologicalAgentOrder(
  nodes: WorkflowGraphNode[],
  edges: WorkflowGraphEdge[],
): Record<string, number> {
  const agentIds = nodes.filter((node) => node.type === 'agent').map((node) => node.id)
  const position = new Map(nodes.map((node) => [node.id, node.position]))
  const byPosition = (a: string, b: string) => {
    const pa = position.get(a)
    const pb = position.get(b)
    if (!pa || !pb) return 0
    return pa.y - pb.y || pa.x - pb.x
  }

  const indegree = new Map(agentIds.map((id) => [id, 0]))
  const outgoing = new Map<string, string[]>(agentIds.map((id) => [id, []]))
  for (const edge of edges) {
    if (!indegree.has(edge.source) || !indegree.has(edge.target)) continue
    outgoing.get(edge.source)?.push(edge.target)
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1)
  }

  const ready = agentIds.filter((id) => indegree.get(id) === 0).sort(byPosition)
  const ordered: string[] = []
  while (ready.length > 0) {
    const id = ready.shift() as string
    ordered.push(id)
    for (const next of outgoing.get(id) ?? []) {
      indegree.set(next, (indegree.get(next) ?? 0) - 1)
      if (indegree.get(next) === 0) {
        ready.push(next)
        ready.sort(byPosition)
      }
    }
  }
  // Cycles leave nodes unordered; append them in layout order.
  for (const id of agentIds) {
    if (!ordered.includes(id)) ordered.push(id)
  }

  const order: Record<string, number> = {}
  ordered.forEach((id, index) => {
    order[id] = index + 1
  })
  return order
}

/** A unique, readable node id derived from the agent name. */
export function agentNodeId(agent: Agent, existing: string[]): string {
  const base =
    agent.name
      .toLowerCase()
      .replace(/[^a-z0-9-]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'agent'
  if (!existing.includes(base)) return base
  let index = 2
  while (existing.includes(`${base}-${index}`)) index += 1
  return `${base}-${index}`
}

export function createAgentNode(agent: Agent, position: { x: number; y: number }): WorkflowGraphNode {
  return {
    id: agentNodeId(agent, []),
    type: 'agent',
    position,
    data: { kind: 'agent', agentId: agent.id, agentName: agent.name, overrides: {} },
  }
}

export function structuralNode(
  kind: 'input' | 'output' | 'schedule',
  position: { x: number; y: number },
): WorkflowGraphNode {
  const data: WorkflowNodeData =
    kind === 'input'
      ? { kind, query: '', prompt: '', model: DEFAULT_AGENT_MODEL, guardrailEnabled: true, guardrailId: '' }
      : kind === 'schedule'
        ? { kind, schedule: { ...DEFAULT_AGENT_SCHEDULE } }
        : { kind, format: 'markdown', instructions: '' }
  // Structural cards are fixed: the user cannot drag them around.
  return { id: kind, type: kind, position, data, draggable: false }
}

/** The schedule is attached to the left of the host. */
export function scheduleHostEdge(): WorkflowGraphEdge {
  return {
    id: 'e-schedule-input',
    source: 'schedule',
    target: 'input',
    sourceHandle: WORKFLOW_HANDLE.nodeOut,
    targetHandle: WORKFLOW_HANDLE.hostScheduleIn,
  }
}

/** The host connects to the output below it. */
export function hostOutputEdge(): WorkflowGraphEdge {
  return {
    id: 'e-input-output',
    source: 'input',
    target: 'output',
    sourceHandle: WORKFLOW_HANDLE.hostOutputOut,
    targetHandle: WORKFLOW_HANDLE.nodeIn,
  }
}

/** The host connects to every agent on its right. */
export function hostAgentEdge(agentNodeId: string): WorkflowGraphEdge {
  return {
    id: `e-input-${agentNodeId}`,
    source: 'input',
    target: agentNodeId,
    sourceHandle: WORKFLOW_HANDLE.hostAgentsOut,
    targetHandle: WORKFLOW_HANDLE.nodeIn,
  }
}

export function defaultWorkflowGraph(): WorkflowConfig {
  return {
    version: WORKFLOW_CONFIG_VERSION,
    mode: 'graph',
    input: { query: '', prompt: '', model: DEFAULT_AGENT_MODEL },
    output: { format: 'markdown', instructions: '' },
    schedule: { ...DEFAULT_AGENT_SCHEDULE },
    guardrail: { enabled: true, id: '' },
    // A new workflow starts with just the query (host) and the output.
    nodes: [
      structuralNode('input', WORKFLOW_LAYOUT.input),
      structuralNode('output', WORKFLOW_LAYOUT.output),
    ],
    edges: [hostOutputEdge()],
  }
}

function structuralPosition(kind: WorkflowNodeKind): { x: number; y: number } | null {
  if (kind === 'input') return WORKFLOW_LAYOUT.input
  if (kind === 'output') return WORKFLOW_LAYOUT.output
  if (kind === 'schedule') return WORKFLOW_LAYOUT.schedule
  return null
}

function positionFor(
  node: WorkflowGraphNode,
  index: number,
): { x: number; y: number } {
  if (node.position && Number.isFinite(node.position.x) && Number.isFinite(node.position.y)) {
    return node.position
  }
  return structuralPosition(node.type) ?? nextAgentPosition(index)
}

/** Rebuild the canvas from a saved config, filling in missing positions. */
export function graphFromConfig(config: WorkflowConfig): WorkflowConfig {
  const nodes: WorkflowGraphNode[] = (config.nodes ?? []).map((node, index) => ({
    ...node,
    // The host, output and schedule are fixed structural cards: they always
    // live at their canonical spots (query left, schedule above, output below),
    // even for configs saved under an older layout.
    position: structuralPosition(node.type) ?? positionFor(node, index),
    // The run question is never persisted, so the host card starts blank.
    data: {
      ...node.data,
      kind: node.type,
      ...(node.type === 'input'
        ? {
            query: '',
            guardrailEnabled: config.guardrail?.enabled ?? node.data.guardrailEnabled ?? true,
            guardrailId: config.guardrail?.id ?? node.data.guardrailId ?? '',
          }
        : {}),
    },
  }))
  const hasInput = nodes.some((node) => node.type === 'input')
  const hasOutput = nodes.some((node) => node.type === 'output')
  const hasSchedule = nodes.some((node) => node.type === 'schedule')
  if (!hasInput) nodes.unshift(structuralNode('input', WORKFLOW_LAYOUT.input))
  if (!hasOutput) nodes.push(structuralNode('output', WORKFLOW_LAYOUT.output))

  const typeById = new Map(nodes.map((node) => [node.id, node.type]))
  const edges: WorkflowGraphEdge[] = (config.edges ?? []).map((edge) => {
    const handles = edgeHandles(
      typeById.get(edge.source) ?? 'agent',
      typeById.get(edge.target) ?? 'agent',
    )
    return {
      id: edge.id || `e-${edge.source}-${edge.target}`,
      source: edge.source,
      target: edge.target,
      ...handles,
    }
  })
  // The output link is always present; the schedule link only when a schedule
  // node exists (it is added on demand, not by default).
  if (hasSchedule && !edges.some((edge) => edge.source === 'schedule' && edge.target === 'input')) {
    edges.push(scheduleHostEdge())
  }
  if (!edges.some((edge) => edge.source === 'input' && edge.target === 'output')) {
    edges.push(hostOutputEdge())
  }

  return {
    version: config.version ?? WORKFLOW_CONFIG_VERSION,
    mode: config.mode ?? 'graph',
    input: {
      query: '',
      prompt: config.input?.prompt ?? '',
      model: config.input?.model ?? DEFAULT_AGENT_MODEL,
    },
    output: config.output ?? { format: 'markdown', instructions: '' },
    schedule: config.schedule ?? { ...DEFAULT_AGENT_SCHEDULE },
    guardrail: config.guardrail ?? { enabled: true, id: '' },
    nodes: arrangeAgentColumn(nodes),
    edges,
  }
}

/** Derive the persistable config from the canvas. */
export function configFromGraph(
  nodes: WorkflowGraphNode[],
  edges: WorkflowGraphEdge[],
  mode: WorkflowMode,
): WorkflowConfig {
  const inputNode = nodes.find((node) => node.type === 'input')
  const outputNode = nodes.find((node) => node.type === 'output')
  const scheduleNode = nodes.find((node) => node.type === 'schedule')
  return {
    version: WORKFLOW_CONFIG_VERSION,
    mode,
    // The question is asked at run time (Run tab) and never persisted.
    input: {
      query: '',
      prompt: inputNode?.data.prompt ?? '',
      model: inputNode?.data.model ?? DEFAULT_AGENT_MODEL,
    },
    output: {
      format: outputNode?.data.format ?? 'markdown',
      instructions: outputNode?.data.instructions ?? '',
    },
    schedule: scheduleNode?.data.schedule ?? { ...DEFAULT_AGENT_SCHEDULE },
    guardrail: {
      enabled: inputNode?.data.guardrailEnabled ?? true,
      id: inputNode?.data.guardrailId ?? '',
    },
    nodes: nodes.map((node) => ({
      id: node.id,
      type: node.type,
      position: node.position,
      data:
        node.type === 'input'
          ? { ...node.data, query: '' }
          : node.data,
    })),
    edges: edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
    })),
  }
}

/** Agent nodes that have no outgoing edge (the ones whose output is final). */
export function sinkNodeIds(config: WorkflowConfig): string[] {
  const agentIds = new Set(
    config.nodes.filter((node) => node.type === 'agent').map((node) => node.id),
  )
  const withOut = new Set<string>()
  for (const edge of config.edges) {
    if (agentIds.has(edge.source) && agentIds.has(edge.target)) withOut.add(edge.source)
  }
  return [...agentIds].filter((id) => !withOut.has(id))
}

export function effectiveModel(
  node: WorkflowGraphNode,
  agents: Agent[],
): string {
  if (node.data.overrides?.model) return node.data.overrides.model
  const agent = agents.find((entry) => entry.id === node.data.agentId)
  return resolveAgentModel(agent?.model)
}

export function effectiveModelLabel(
  node: WorkflowGraphNode,
  agents: Agent[],
): string {
  return agentModelLabel(effectiveModel(node, agents))
}

export function agentForNode(node: WorkflowGraphNode, agents: Agent[]): Agent | null {
  return agents.find((entry) => entry.id === node.data.agentId) ?? null
}

// --- validation --------------------------------------------------------------

export function validateWorkflowName(value: string): string | null {
  const name = value.trim()
  if (!name) return 'Name is required'
  if (name.length > WORKFLOW_NAME_MAX) return `Name must be at most ${WORKFLOW_NAME_MAX} characters`
  if (!/^[a-z0-9-]+$/.test(name)) {
    return 'Only lowercase letters, numbers and hyphens (no spaces or special characters)'
  }
  if (!/^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/.test(name)) {
    return 'Must start and end with a letter or number'
  }
  return null
}

export function validateWorkflowDescription(value: string): string | null {
  const description = value.trim()
  if (!description) return 'Description is required'
  if (description.length > WORKFLOW_DESCRIPTION_MAX) {
    return `Description must be at most ${WORKFLOW_DESCRIPTION_MAX} characters`
  }
  return null
}

// --- draft persistence (localStorage) ---------------------------------------

// Bump the version whenever the default layout changes, so a stale draft from
// an older layout is not restored instead of the new one.
function draftKey(workflowId: string | null): string {
  return `workflow-builder-draft:v2:${workflowId ?? 'new'}`
}

export function saveWorkflowDraft(workflowId: string | null, draft: WorkflowDraft): void {
  try {
    localStorage.setItem(draftKey(workflowId), JSON.stringify(draft))
  } catch {
    // Storage may be unavailable; autosave is best-effort.
  }
}

export function loadWorkflowDraft(workflowId: string | null): WorkflowDraft | null {
  try {
    const raw = localStorage.getItem(draftKey(workflowId))
    return raw ? (JSON.parse(raw) as WorkflowDraft) : null
  } catch {
    return null
  }
}

export function clearWorkflowDraft(workflowId: string | null): void {
  try {
    localStorage.removeItem(draftKey(workflowId))
  } catch {
    // ignore
  }
}

// --- API calls ---------------------------------------------------------------

export async function createWorkflow(api: ApiClient, payload: WorkflowPayload): Promise<WorkflowDetail> {
  return api.post<WorkflowDetail>('/v1/workflows', payload)
}

export async function fetchWorkflow(api: ApiClient, id: string): Promise<WorkflowDetail> {
  return api.get<WorkflowDetail>(`/v1/workflows/${id}`)
}

export async function updateWorkflow(
  api: ApiClient,
  id: string,
  payload: WorkflowPayload,
): Promise<WorkflowDetail> {
  return api.put<WorkflowDetail>(`/v1/workflows/${id}`, payload)
}

export async function deleteWorkflow(api: ApiClient, id: string): Promise<void> {
  await api.delete(`/v1/workflows/${id}`)
}

export async function verifyWorkflow(api: ApiClient, id: string): Promise<WorkflowVerifyResult> {
  return api.post<WorkflowVerifyResult>(`/v1/workflows/${id}/verify`)
}

// --- hooks -------------------------------------------------------------------

export function useWorkflows() {
  const api = useApiClient()
  return usePageQuery(
    WORKFLOWS_QUERY_KEY,
    () => api.get<WorkflowList>('/v1/workflows'),
    { refetchOnMount: true },
  )
}

export function invalidateWorkflows(): void {
  invalidateQuery(WORKFLOWS_QUERY_KEY)
}

/** Re-exported so the composer/inspector share one model catalogue. */
export { AGENT_MODELS, DEFAULT_AGENT_MODEL }

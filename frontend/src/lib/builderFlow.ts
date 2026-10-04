/**
 * Live execution flow for the agent and workflow builders.
 *
 * Both builders render a React Flow canvas of cards (input → agent →
 * knowledge/tools/skills → output, plus a schedule trigger). While a run
 * streams, this module turns the run state into a per-card status and a
 * per-edge status so the canvas can highlight the card that is executing and
 * animate the connections carrying data — the same reducer state that powers
 * the timeline panel.
 *
 * Statuses are intentionally coarse: `active` (executing now), `done`
 * (finished), `error` (failed) and `idle` (not involved in this run).
 */

import type { RunFields } from './runState'
import type { WorkflowNodeRun, WorkflowRunFields } from './workflowRun'

export type FlowStatus = 'idle' | 'active' | 'done' | 'error'

export type NodeStatusMap = Record<string, FlowStatus>

export type FlowNode = { id: string; type: string }
export type FlowEdge = { id: string; source: string; target: string }

export type BuilderFlow = {
  nodeStatus: NodeStatusMap
  edgeStatus: Record<string, FlowStatus>
}

/**
 * An edge carries data when its destination is live. A not-yet-started agent
 * still lights up while its source is dispatching into it; resource cards
 * (knowledge/tools/skills) and the output stay dark until they are actually used.
 */
function edgeStatus(
  targetType: string,
  source: FlowStatus,
  target: FlowStatus,
): FlowStatus {
  if (source === 'error' || target === 'error') return 'error'
  if (target === 'active') return 'active'
  if (target === 'done') return 'done'
  if (targetType === 'agent' && source === 'active') return 'active'
  return 'idle'
}

function combine(
  nodes: FlowNode[],
  edges: FlowEdge[],
  byId: NodeStatusMap,
): BuilderFlow {
  const nodeStatus: NodeStatusMap = {}
  const typeById: Record<string, string> = {}
  for (const node of nodes) {
    nodeStatus[node.id] = byId[node.id] ?? 'idle'
    typeById[node.id] = node.type
  }
  const edgeStatusMap: Record<string, FlowStatus> = {}
  for (const edge of edges) {
    edgeStatusMap[edge.id] = edgeStatus(
      typeById[edge.target] ?? '',
      nodeStatus[edge.source] ?? 'idle',
      nodeStatus[edge.target] ?? 'idle',
    )
  }
  return { nodeStatus, edgeStatus: edgeStatusMap }
}

/** Styles a React Flow edge from its flow status. */
export function edgeVisual(status: FlowStatus): {
  animated: boolean
  className?: string
  style?: Record<string, string | number>
} {
  switch (status) {
    case 'active':
      return {
        animated: true,
        className: 'builder-edge-active',
        style: { stroke: 'var(--app-accent)', strokeWidth: 2 },
      }
    case 'done':
      return {
        animated: false,
        className: 'builder-edge-done',
        style: { stroke: 'var(--app-success)', strokeWidth: 2 },
      }
    case 'error':
      return {
        animated: false,
        className: 'builder-edge-error',
        style: { stroke: 'var(--app-accent)', strokeWidth: 2 },
      }
    default:
      return { animated: false }
  }
}

// --- agent builder -----------------------------------------------------------

/** Knowledge-base MCP tools are the only ones that map to the knowledge card. */
const KNOWLEDGE_TOOL = /knowledge/i

function agentToolKind(name: string): 'knowledge' | 'tools' {
  return KNOWLEDGE_TOOL.test(name) ? 'knowledge' : 'tools'
}

export type AgentFlowOptions = {
  nodes: FlowNode[]
  edges: FlowEdge[]
  run: RunFields | null
  /** The agent has a schedule attached (its trigger card participates). */
  scheduleEnabled?: boolean
}

/**
 * Derive the agent builder's flow. The graph has at most one card per kind, so
 * the run state (planning → tools → answer) is mapped by card kind.
 */
export function computeAgentFlow({
  nodes,
  edges,
  run,
  scheduleEnabled = false,
}: AgentFlowOptions): BuilderFlow | null {
  if (!run) return null

  // The human-in-the-loop question is a synthetic history entry, not a tool.
  const tools = run.tools.filter((tool) => tool.name !== 'Question')
  const knowledge = tools.filter((tool) => agentToolKind(tool.name) === 'knowledge')
  const other = tools.filter((tool) => agentToolKind(tool.name) === 'tools')

  const streaming = run.status === 'streaming'
  const done = run.status === 'done'
  const stopped = run.status === 'stopped'
  const errored = run.status === 'error'

  const groupStatus = (group: typeof tools): FlowStatus => {
    if (group.length === 0) return 'idle'
    if (group.some((tool) => tool.status === 'error')) return 'error'
    // A stopped run leaves its in-flight tool settled, not forever spinning.
    if (stopped) return 'done'
    if (group.some((tool) => tool.status === 'running')) return 'active'
    return 'done'
  }

  const kindStatus: NodeStatusMap = {
    // The question flows into the agent while it plans, then is done.
    input: run.planning ? 'active' : errored && tools.length === 0 ? 'error' : 'done',
    // The agent is the executor: active for most of the run.
    agent: errored ? 'error' : done || stopped ? 'done' : 'active',
    // Skills are folded into the prompt up front.
    skills:
      run.skills.length === 0
        ? 'idle'
        : run.planning || (streaming && tools.length === 0)
          ? 'active'
          : 'done',
    knowledge: groupStatus(knowledge),
    tools: groupStatus(other),
    output: run.answer
      ? done || stopped
        ? 'done'
        : 'active'
      : done
        ? 'done'
        : 'idle',
    // A configured schedule is the run's trigger: active at the start, then set.
    schedule: scheduleEnabled ? (run.planning ? 'active' : 'done') : 'idle',
  }

  const byId: NodeStatusMap = {}
  for (const node of nodes) byId[node.id] = kindStatus[node.type] ?? 'idle'
  return combine(nodes, edges, byId)
}

// --- workflow builder --------------------------------------------------------

export type WorkflowFlowOptions = {
  nodes: FlowNode[]
  edges: FlowEdge[]
  run: WorkflowRunFields | null
  scheduleEnabled?: boolean
}

function workflowNodeStatus(status: WorkflowNodeRun['status'] | undefined): FlowStatus {
  if (status === 'running') return 'active'
  if (status === 'done') return 'done'
  if (status === 'error') return 'error'
  return 'idle'
}

/**
 * Derive the workflow builder's flow. Agent cards match their runtime node id;
 * the reserved host cards (the swarm host, the graph dispatcher and the graph
 * synthesizer) all light up the single `input`/Query card, and the output card
 * follows the streamed final answer.
 */
export function computeWorkflowFlow({
  nodes,
  edges,
  run,
  scheduleEnabled = false,
}: WorkflowFlowOptions): BuilderFlow | null {
  if (!run) return null

  const byRunId = new Map(run.nodes.map((node) => [node.id, node]))
  const hostNodes = run.nodes.filter(
    (node) =>
      node.role === 'host' ||
      node.stage === 'dispatch' ||
      node.stage === 'synthesis' ||
      node.id === 'host' ||
      node.id === 'host-synth',
  )

  let host: FlowStatus = 'idle'
  if (hostNodes.some((node) => node.status === 'running')) host = 'active'
  else if (hostNodes.some((node) => node.status === 'error')) host = 'error'
  else if (run.status === 'error') host = 'error'
  else if (run.status === 'streaming') host = 'done'
  else if (run.status === 'done' || run.status === 'stopped') host = 'done'
  // Before the `workflow` frame lands there are no node metas yet: the host is
  // already working.
  if (host === 'idle' && run.nodes.length === 0) host = 'active'

  const output: FlowStatus =
    run.status === 'done' || run.status === 'stopped'
      ? 'done'
      : run.answer
        ? 'active'
        : run.status === 'error'
          ? 'error'
          : 'idle'

  const noNodeStarted = run.nodes.every((node) => node.status === 'pending')

  const byId: NodeStatusMap = {}
  for (const node of nodes) {
    if (node.type === 'input') byId[node.id] = host
    else if (node.type === 'output') byId[node.id] = output
    else if (node.type === 'schedule') {
      byId[node.id] = scheduleEnabled ? (noNodeStarted ? 'active' : 'done') : 'idle'
    } else if (node.type === 'agent') {
      byId[node.id] = workflowNodeStatus(byRunId.get(node.id)?.status)
    } else {
      byId[node.id] = 'idle'
    }
  }

  return combine(nodes, edges, byId)
}

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent,
} from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Background,
  BackgroundVariant,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Edge,
  type Connection,
  type OnConnect,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { useAuth0 } from '@auth0/auth0-react'
import { toast } from 'sonner'
import {
  ArrowLeft,
  ArrowUpRight,
  FileText,
  Loader2,
  Pencil,
  Play,
  Save,
  Square,
  Trash2,
  Workflow as WorkflowIcon,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { Dialog } from '../components/ui/Dialog'
import { Segmented } from '../components/ui/Segmented'
import { Spinner } from '../components/ui/Spinner'
import { AgentPalette, AGENT_DND_TYPE } from '../components/workflow-builder/AgentPalette'
import { WorkflowNodeView, type WorkflowFlowNode } from '../components/workflow-builder/WorkflowNode'
import {
  WorkflowBuilderProvider,
  type WorkflowBuilderContextValue,
} from '../components/workflow-builder/WorkflowBuilderContext'
import { WorkflowInspector } from '../components/workflow-builder/WorkflowInspector'
import { WorkflowRunTimeline } from '../components/workflow-builder/WorkflowRunTimeline'
import { WorkflowHistory } from '../components/workflow-builder/WorkflowHistory'
import { useApiClient, ApiError } from '../lib/api'
import { useDemoMode } from '../auth/useDemoMode'
import { IDS } from '../lib/demo/shared'
import { streamDemoWorkflowRun } from '../lib/demo/demoRun'
import { agentRunConfigured } from '../lib/agentRun'
import { computeWorkflowFlow, edgeVisual } from '../lib/builderFlow'
import { runWorkflowStream, type WorkflowRunEvent, type WorkflowRunFields } from '../lib/workflowRun'
import {
  createWorkflowRunFields,
  markWorkflowError,
  markWorkflowStopped,
  reduceWorkflowEvent,
} from '../lib/workflowRunState'
import { useAgents, type Agent } from '../lib/agents'
import { useAgentSkills } from '../lib/agentSkills'
import { useKnowledgeBases } from '../lib/knowledgeBases'
import {
  agentNodeId,
  clearWorkflowDraft,
  configFromGraph,
  createAgentNode,
  defaultWorkflowGraph,
  deleteWorkflow,
  fetchWorkflow,
  graphFromConfig,
  hostAgentEdge,
  hostOutputEdge,
  invalidateWorkflows,
  loadWorkflowDraft,
  MAX_WORKFLOW_AGENTS,
  arrangeAgentColumn,
  saveWorkflowDraft,
  scheduleHostEdge,
  structuralNode,
  topologicalAgentOrder,
  updateWorkflow,
  createWorkflow,
  validateWorkflowDescription,
  validateWorkflowName,
  WORKFLOW_LAYOUT,
  WORKFLOW_MODES,
  WORKFLOW_NODE_HEIGHT,
  WORKFLOW_NODE_WIDTH,
  type WorkflowDetail,
  type WorkflowGraphEdge,
  type WorkflowGraphNode,
  type WorkflowMode,
  type WorkflowNodeData,
} from '../lib/workflows'
import type { Conversation } from '../lib/conversations'

const nodeTypes = {
  input: WorkflowNodeView,
  agent: WorkflowNodeView,
  output: WorkflowNodeView,
  schedule: WorkflowNodeView,
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong'
}

/** Map saved workflow edges to React Flow edges, preserving handle ids. */
function toFlowEdges(edges: WorkflowGraphEdge[]): Edge[] {
  return edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    sourceHandle: edge.sourceHandle ?? undefined,
    targetHandle: edge.targetHandle ?? undefined,
    type: 'default',
  }))
}

// --- canvas ------------------------------------------------------------------

function WorkflowCanvas({
  nodes,
  edges,
  onNodesChange,
  onEdgesChange,
  onConnect,
  onDropAgent,
  onNodeClick,
  onPaneClick,
  containerRef,
}: {
  nodes: WorkflowFlowNode[]
  edges: Edge[]
  onNodesChange: ReturnType<typeof useNodesState<WorkflowFlowNode>>[2]
  onEdgesChange: ReturnType<typeof useEdgesState<Edge>>[2]
  onConnect: OnConnect
  onDropAgent: (agentId: string) => void
  onNodeClick: (id: string) => void
  onPaneClick: () => void
  containerRef: React.RefObject<HTMLDivElement | null>
}) {
  const { setViewport } = useReactFlow()
  const fitKeyRef = useRef('')

  // Fit the whole workflow into the canvas (anchored left, biased toward the
  // top) whenever nodes are added or removed, so all agents stay visible and
  // aligned. Position edits and drags do not re-fit.
  useEffect(() => {
    const key = nodes.map((node) => node.id).join('|')
    if (fitKeyRef.current === key) return
    const frame = requestAnimationFrame(() => {
      const element = containerRef.current
      if (!element) return
      const height = element.clientHeight
      const width = element.clientWidth
      if (!height || !width) return
      fitKeyRef.current = key

      let minX = Infinity
      let minY = Infinity
      let maxX = -Infinity
      let maxY = -Infinity
      for (const node of nodes) {
        minX = Math.min(minX, node.position.x)
        minY = Math.min(minY, node.position.y)
        maxX = Math.max(maxX, node.position.x + WORKFLOW_NODE_WIDTH)
        maxY = Math.max(maxY, node.position.y + WORKFLOW_NODE_HEIGHT)
      }
      if (!Number.isFinite(minY)) return

      const padding = 48
      const contentW = Math.max(1, maxX - minX)
      const contentH = Math.max(1, maxY - minY)
      const zoom = Math.min(
        1,
        (width - padding * 2) / contentW,
        (height - padding * 2) / contentH,
      )
      const slackY = height - contentH * zoom
      const y = (slackY > padding * 2 ? slackY * 0.5 : padding) - minY * zoom
      const x = padding - minX * zoom
      void setViewport({ x, y, zoom })
    })
    return () => cancelAnimationFrame(frame)
  }, [nodes, containerRef, setViewport])

  const handleDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()
      const agentId = event.dataTransfer.getData(AGENT_DND_TYPE)
      if (!agentId) return
      onDropAgent(agentId)
    },
    [onDropAgent],
  )

  return (
    <div ref={containerRef} className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_55%_at_50%_0%,var(--app-raised),transparent_75%)]" />
      <div className="absolute inset-0">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_event, node) => onNodeClick(node.id)}
          onPaneClick={onPaneClick}
          onDrop={handleDrop}
          onDragOver={(event) => {
            event.preventDefault()
            event.dataTransfer.dropEffect = 'copy'
          }}
          deleteKeyCode={null}
          nodesDraggable={false}
          nodesConnectable
          minZoom={0.3}
          maxZoom={2}
          defaultEdgeOptions={{ type: 'default' }}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="var(--app-border)" />
        </ReactFlow>
      </div>
    </div>
  )
}

// --- page --------------------------------------------------------------------

export function WorkflowBuilderPage() {
  const api = useApiClient()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const demo = useDemoMode()
  // In the read-only demo, open a configured multi-agent workflow so the canvas,
  // inspector (knowledge / MCP / skills per node) and History are populated.
  const workflowId =
    searchParams.get('workflow') ?? (demo ? IDS.workflowVendorDiligence : null)

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [mode, setMode] = useState<WorkflowMode>('graph')
  const [nodes, setNodes, onNodesChange] = useNodesState<WorkflowFlowNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [tab, setTab] = useState<'inspect' | 'run' | 'history'>('inspect')
  // The demo replays a scripted run, so no run URL is required.
  const configured = demo || agentRunConfigured()

  const [loading, setLoading] = useState(Boolean(workflowId))
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [draftName, setDraftName] = useState('')
  const [draftDescription, setDraftDescription] = useState('')

  const [run, setRun] = useState<WorkflowRunFields | null>(null)
  const [runDraft, setRunDraft] = useState('')
  const [runConversationId, setRunConversationId] = useState('')
  const [running, setRunning] = useState(false)
  const runAbortRef = useRef<AbortController | null>(null)
  const { getAccessTokenSilently } = useAuth0()

  const hydratedRef = useRef(false)
  const loadedIdRef = useRef<string | null>(null)
  const snapshotRef = useRef('')
  const containerRef = useRef<HTMLDivElement>(null)

  const agentsQuery = useAgents()
  const skillsQuery = useAgentSkills()
  const kbsQuery = useKnowledgeBases()

  const agents = useMemo(() => agentsQuery.data?.agents ?? [], [agentsQuery.data])
  const skillList = useMemo(
    () => (skillsQuery.data?.skills ?? []).map((skill) => ({ id: skill.id, name: skill.name })),
    [skillsQuery.data],
  )
  const knowledgeBases = useMemo(
    () =>
      (kbsQuery.data?.knowledgeBases ?? []).map((kb) => ({ id: kb.id, name: kb.name })),
    [kbsQuery.data],
  )

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  )

  const config = useMemo(
    () =>
      configFromGraph(
        nodes as unknown as WorkflowGraphNode[],
        edges as unknown as WorkflowGraphEdge[],
        mode,
      ),
    [nodes, edges, mode],
  )

  const serialized = useMemo(
    () => JSON.stringify({ name, description, config }),
    [name, description, config],
  )

  // Live run flow: which agent card is executing and which connections are
  // carrying the handoff/dispatch. Derived from the run panel's state.
  const scheduleEnabled = useMemo(
    () =>
      nodes.some(
        (node) => node.type === 'schedule' && (node.data.schedule?.enabled ?? false),
      ),
    [nodes],
  )

  const flow = useMemo(
    () =>
      computeWorkflowFlow({
        nodes: nodes.map((node) => ({ id: node.id, type: node.type ?? '' })),
        edges: edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target })),
        run,
        scheduleEnabled,
      }),
    [nodes, edges, run, scheduleEnabled],
  )

  const displayEdges = useMemo(
    () =>
      flow
        ? edges.map((edge) => ({ ...edge, ...edgeVisual(flow.edgeStatus[edge.id] ?? 'idle') }))
        : edges,
    [edges, flow],
  )

  const nameError = validateWorkflowName(name)
  const descriptionError = validateWorkflowDescription(description)
  const canSave = !nameError && !descriptionError

  // --- load ------------------------------------------------------------------

  const applyDetail = useCallback(
    (detail: WorkflowDetail) => {
      loadedIdRef.current = detail.id
      setName(detail.name)
      setDescription(detail.description ?? '')
      setMode(detail.config.mode ?? 'graph')
      const graph = graphFromConfig(detail.config)
      setNodes(graph.nodes as unknown as WorkflowFlowNode[])
      setEdges(toFlowEdges(graph.edges))
      snapshotRef.current = JSON.stringify({
        name: detail.name,
        description: detail.description ?? '',
        config: detail.config,
      })
      setDirty(false)
    },
    [setEdges, setNodes],
  )

  useEffect(() => {
    if (workflowId && loadedIdRef.current === workflowId) return
    let active = true
    hydratedRef.current = false
    setLoading(Boolean(workflowId))

    async function load() {
      if (workflowId) {
        try {
          const detail = await fetchWorkflow(api, workflowId)
          if (!active) return
          applyDetail(detail)
          // The demo is read-only and must always show the canonical saved
          // workflow — never a stale local draft that overrides its wiring.
          if (demo) {
            clearWorkflowDraft(workflowId)
            clearWorkflowDraft(null)
          }
          const draft = demo ? null : loadWorkflowDraft(workflowId)
          if (draft) {
            setName(draft.name)
            setDescription(draft.description)
            setMode(draft.config.mode)
            const graph = graphFromConfig(draft.config)
            setNodes(graph.nodes as unknown as WorkflowFlowNode[])
            setEdges(toFlowEdges(graph.edges))
            setDirty(true)
          }
        } catch (error) {
          if (active) {
            toast.error(errorMessage(error))
            navigate('/workflow-store')
          }
        } finally {
          if (active) {
            setLoading(false)
            hydratedRef.current = true
          }
        }
        return
      }

      const draft = demo ? null : loadWorkflowDraft(null)
      const graph = draft ? graphFromConfig(draft.config) : defaultWorkflowGraph()
      setName(draft?.name ?? '')
      setDescription(draft?.description ?? '')
      setMode(draft?.config.mode ?? 'graph')
      setNodes(graph.nodes as unknown as WorkflowFlowNode[])
      setEdges(toFlowEdges(graph.edges))
      setLoading(false)
      hydratedRef.current = true
    }

    void load()
    return () => {
      active = false
    }
  }, [api, applyDetail, demo, navigate, setEdges, setNodes, workflowId])

  // --- autosave (localStorage) ----------------------------------------------

  useEffect(() => {
    if (!hydratedRef.current) return
    const isDirty = serialized !== snapshotRef.current
    setDirty(isDirty)
    // The demo never persists drafts, so its wiring can't be shadowed later.
    if (!isDirty || demo) return
    const timer = window.setTimeout(() => {
      saveWorkflowDraft(workflowId, { name, description, config })
    }, 500)
    return () => window.clearTimeout(timer)
  }, [serialized, workflowId, name, description, config, demo])

  // --- graph editing ---------------------------------------------------------

  const updateNodeData = useCallback(
    (id: string, patch: Partial<WorkflowNodeData>) => {
      setNodes((current) =>
        current.map((node) =>
          node.id === id ? { ...node, data: { ...node.data, ...patch } } : node,
        ),
      )
    },
    [setNodes],
  )

  const removeNode = useCallback(
    (id: string) => {
      setNodes((current) => {
        const next = current.filter((node) => node.id !== id)
        return arrangeAgentColumn(
          next as unknown as WorkflowGraphNode[],
        ) as unknown as WorkflowFlowNode[]
      })
      setEdges((current) => current.filter((edge) => edge.source !== id && edge.target !== id))
      setSelectedNodeId((current) => (current === id ? null : current))
    },
    [setEdges, setNodes],
  )

  const addAgentNode = useCallback(
    (agent: Agent) => {
      if (nodes.filter((node) => node.type === 'agent').length >= MAX_WORKFLOW_AGENTS) {
        toast.error(`A workflow supports up to ${MAX_WORKFLOW_AGENTS} agents`)
        return
      }
      const id = agentNodeId(
        agent,
        nodes.map((node) => node.id),
      )
      setNodes((current) => {
        if (current.some((node) => node.id === id)) return current
        const node = { ...createAgentNode(agent, { x: 0, y: 0 }), id }
        const next = [...current, node] as unknown as WorkflowGraphNode[]
        return arrangeAgentColumn(next) as unknown as WorkflowFlowNode[]
      })
      // Every agent connects to the host, so the workflow always has a path.
      setEdges((current) => {
        let next = current.some((edge) => edge.source === 'input' && edge.target === 'output')
          ? current
          : [...current, { ...hostOutputEdge(), type: 'default' } as Edge]
        if (!next.some((edge) => edge.target === id)) {
          next = [...next, { ...hostAgentEdge(id), type: 'default' } as Edge]
        }
        return next
      })
    },
    [nodes, setEdges, setNodes],
  )

  const handleDropAgent = useCallback(
    (agentId: string) => {
      const agent = agents.find((entry) => entry.id === agentId)
      if (agent) addAgentNode(agent)
    },
    [addAgentNode, agents],
  )

  const hasSchedule = useMemo(
    () => nodes.some((node) => node.type === 'schedule'),
    [nodes],
  )

  const addSchedule = useCallback(() => {
    setNodes((current) => {
      if (current.some((node) => node.type === 'schedule')) return current
      return [
        ...current,
        structuralNode('schedule', WORKFLOW_LAYOUT.schedule) as unknown as WorkflowFlowNode,
      ]
    })
    setEdges((current) =>
      current.some((edge) => edge.source === 'schedule' && edge.target === 'input')
        ? current
        : [...current, { ...scheduleHostEdge(), type: 'default' } as Edge],
    )
    setSelectedNodeId('schedule')
    setTab('inspect')
  }, [setEdges, setNodes])

  const onConnect: OnConnect = useCallback(
    (connection: Connection) =>
      setEdges((current) => {
        const id = `e-${connection.source}-${connection.target}`
        if (current.some((edge) => edge.id === id)) return current
        return [
          ...current,
          {
            id,
            source: connection.source,
            target: connection.target,
            sourceHandle: connection.sourceHandle ?? undefined,
            targetHandle: connection.targetHandle ?? undefined,
            type: 'default',
          } as Edge,
        ]
      }),
    [setEdges],
  )

  const order = useMemo(
    () =>
      mode === 'graph'
        ? topologicalAgentOrder(
            nodes as unknown as WorkflowGraphNode[],
            edges as unknown as WorkflowGraphEdge[],
          )
        : {},
    [mode, nodes, edges],
  )

  const builderContext = useMemo<WorkflowBuilderContextValue>(
    () => ({
      agents,
      mode,
      order,
      selectedNodeId,
      updateNodeData,
      removeNode,
      openNode: (id) => {
        setSelectedNodeId(id)
        setTab('inspect')
      },
      nodeStatus: flow?.nodeStatus ?? {},
    }),
    [agents, mode, order, selectedNodeId, updateNodeData, removeNode, flow],
  )

  // --- actions ---------------------------------------------------------------

  const handleSave = useCallback(async (): Promise<WorkflowDetail | null> => {
    if (!canSave) {
      setDraftName(name)
      setDraftDescription(description)
      setDetailsOpen(true)
      return null
    }
    setSaving(true)
    try {
      const payload = { name, description, config }
      const saved = workflowId
        ? await updateWorkflow(api, workflowId, payload)
        : await createWorkflow(api, payload)
      clearWorkflowDraft(workflowId)
      clearWorkflowDraft(null)
      invalidateWorkflows()
      loadedIdRef.current = saved.id
      snapshotRef.current = JSON.stringify({
        name: saved.name,
        description: saved.description ?? '',
        config: saved.config,
      })
      setDirty(false)
      if (!workflowId) {
        navigate(`/workflow-builder?workflow=${saved.id}`, { replace: true })
      }
      toast.success('Workflow saved')
      return saved
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        toast.error(error.message)
      } else {
        toast.error(errorMessage(error))
      }
      return null
    } finally {
      setSaving(false)
    }
  }, [api, canSave, config, description, name, navigate, workflowId])

  const handleStopRun = useCallback(() => {
    runAbortRef.current?.abort()
    runAbortRef.current = null
    setRunning(false)
    setRun((current) => (current ? markWorkflowStopped(current) : current))
  }, [])

  const handleRun = useCallback(
    async (question: string) => {
      if (!demo && !agentRunConfigured()) {
        toast.error('Agent run URL is not configured (VITE_AGENT_RUN_URL)')
        return
      }
      const query = question.trim()
      if (!query) {
        toast.error('Enter a question to run')
        return
      }
      let id = workflowId
      if (!demo && (!id || dirty)) {
        const saved = await handleSave()
        if (!saved) return
        id = saved.id
      }
      if (!id) return

    const controller = new AbortController()
    runAbortRef.current = controller
    setRunning(true)
    setTab('run')
    setRun(createWorkflowRunFields(mode))
    setRunConversationId('')

    // The demo is read-only: the run is scripted and nothing is persisted.
    let conversationId: string = crypto.randomUUID()
    if (!demo) {
      try {
        const created = await api.post<Conversation>('/v1/conversations', {
          agentId: id,
          targetType: 'workflow',
          kind: 'run',
          title: query,
        })
        conversationId = String(created.conversationId)
        setRunConversationId(conversationId)
      } catch {
        // Persistence is best-effort; the run still executes.
      }
    }

    try {
      const onEvent = (event: WorkflowRunEvent) =>
        setRun((current) => (current ? reduceWorkflowEvent(current, event) : current))
      if (demo) {
        await streamDemoWorkflowRun(name, onEvent, controller.signal)
      } else {
        const token = await getAccessTokenSilently()
        await runWorkflowStream({
          token,
          workflowId: id,
          input: query,
          conversationId,
          signal: controller.signal,
          onEvent,
        })
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = errorMessage(error)
        toast.error(message)
        setRun((current) => (current ? markWorkflowError(current, message) : current))
      }
    } finally {
      if (runAbortRef.current === controller) runAbortRef.current = null
      setRunning(false)
    }
  }, [api, demo, dirty, getAccessTokenSilently, handleSave, mode, name, workflowId])

  const handleDelete = useCallback(async () => {
    if (!workflowId) return
    try {
      await deleteWorkflow(api, workflowId)
      clearWorkflowDraft(workflowId)
      invalidateWorkflows()
      toast.success('Workflow deleted')
      navigate('/workflow-store')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setConfirmDelete(false)
    }
  }, [api, navigate, workflowId])

  // --- render ----------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner size="lg" label="Loading workflow…" />
      </div>
    )
  }

  const agentCount = nodes.filter((node) => node.type === 'agent').length

  return (
    <WorkflowBuilderProvider value={builderContext}>
      <div className="flex min-h-0 flex-1 flex-col">
        <header className="relative flex min-h-[64px] shrink-0 items-center justify-between gap-4 border-b border-border bg-surface/80 px-4 py-2 backdrop-blur-md lg:px-5">
          <span className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-linear-to-r from-accent/70 via-border-strong to-transparent" />

          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => navigate('/workflow-store')}
              title="Back to workflows"
              className="flex size-8 shrink-0 items-center justify-center rounded-lg text-subtle transition-colors hover:bg-raised hover:text-foreground"
            >
              <ArrowLeft className="size-4" />
            </button>
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent shadow-control ring-1 ring-inset ring-accent/25">
              <WorkflowIcon className="size-5" strokeWidth={1.9} />
            </span>
            <div className="flex min-w-0 flex-col">
              <button
                type="button"
                onClick={() => {
                  setDraftName(name)
                  setDraftDescription(description)
                  setDetailsOpen(true)
                }}
                className="group/details -ml-1.5 flex min-w-0 items-center gap-2 rounded-lg px-1.5 py-1 text-left transition-colors hover:bg-raised/60"
              >
                <span
                  className={`max-w-[240px] truncate text-[15px] font-semibold tracking-tight ${
                    name ? 'text-foreground' : 'text-subtle'
                  }`}
                >
                  {name || 'Untitled workflow'}
                </span>
                <Pencil className="size-3 shrink-0 text-subtle group-hover/details:text-foreground" />
                <Badge variant="info">{agentCount} agents</Badge>
              </button>
              <span className="mt-0.5 max-w-[380px] truncate text-[11.5px] text-muted">
                {description || 'Add a short description…'}
              </span>
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2">
            <Segmented
              options={WORKFLOW_MODES.map((entry) => entry.value)}
              value={mode}
              onChange={(value) => setMode(value as WorkflowMode)}
            />
            {workflowId ? (
              <>
                <span className="h-6 w-px bg-border" />
                <button
                  type="button"
                  onClick={() => setConfirmDelete(true)}
                  title="Delete workflow"
                  className="flex size-8 items-center justify-center rounded-lg border border-transparent text-subtle transition-colors hover:border-border hover:bg-raised hover:text-accent"
                >
                  <Trash2 className="size-4" />
                </button>
              </>
            ) : null}

            <span className="relative inline-flex">
              <Button
                variant="secondary"
                size="sm"
                icon={saving ? <Loader2 className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
                onClick={handleSave}
                disabled={saving}
              >
                Save
              </Button>
              {dirty && !saving ? (
                <span className="pointer-events-none absolute -top-1 -right-1 size-2.5 rounded-full bg-accent ring-2 ring-surface" />
              ) : null}
            </span>
          </div>
        </header>

        <div className="flex min-h-0 flex-1">
          <AgentPalette agents={agents} loading={agentsQuery.isPending} onAdd={addAgentNode} />

          <ReactFlowProvider>
            <WorkflowCanvas
              nodes={nodes}
              edges={displayEdges}
              onNodesChange={onNodesChange}
              onEdgesChange={onEdgesChange}
              onConnect={onConnect}
              onDropAgent={handleDropAgent}
              onNodeClick={(id) => {
                setSelectedNodeId(id)
                setTab('inspect')
              }}
              onPaneClick={() => setSelectedNodeId(null)}
              containerRef={containerRef}
            />
          </ReactFlowProvider>

          <aside className="flex w-[340px] shrink-0 flex-col border-l border-border bg-surface/40">
            <div className="flex h-11 shrink-0 items-center gap-1 border-b border-border px-2">
              {(['inspect', 'run', 'history'] as const).map((value) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setTab(value)}
                  className={`rounded-md px-2.5 py-1 text-[12px] font-medium capitalize transition-colors ${
                    tab === value
                      ? 'bg-raised text-foreground'
                      : 'text-subtle hover:text-foreground'
                  }`}
                >
                  {value === 'inspect' ? 'Inspect' : value === 'run' ? 'Run' : 'History'}
                </button>
              ))}
            </div>

            {tab === 'inspect' ? (
              <WorkflowInspector
                node={selectedNode}
                agents={agents}
                skills={skillList}
                knowledgeBases={knowledgeBases}
                hasSchedule={hasSchedule}
                onAddSchedule={addSchedule}
              />
            ) : tab === 'run' ? (
              <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-4">
                <div className="space-y-3">
                  <div className="rounded-lg border border-border bg-canvas/40 p-3">
                    <textarea
                      value={runDraft}
                      onChange={(event) => setRunDraft(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' && !event.shiftKey) {
                          event.preventDefault()
                          if (!running && runDraft.trim()) void handleRun(runDraft)
                        }
                      }}
                      rows={2}
                      placeholder="Ask this workflow…"
                      disabled={running}
                      className="scrollbar-thin w-full resize-y rounded-md border border-border bg-surface px-2.5 py-2 text-[12.5px] leading-relaxed text-foreground outline-none placeholder:text-subtle focus-visible:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/20 disabled:opacity-60"
                    />
                    <div className="mt-2 flex items-center justify-between gap-2">
                      <Button
                        variant={running ? 'outline' : 'primary'}
                        size="sm"
                        icon={running ? <Square className="size-3.5" /> : <Play className="size-3.5" />}
                        onClick={running ? handleStopRun : () => void handleRun(runDraft)}
                        disabled={!running && (!configured || !runDraft.trim())}
                      >
                        {running ? 'Stop' : 'Run'}
                      </Button>
                      <span className="text-[10.5px] text-subtle">Asked each run — not saved</span>
                    </div>
                  </div>
                  {run ? (
                    <div className="space-y-3">
                      <WorkflowRunTimeline run={run} />
                      {run.answer && run.status !== 'streaming' && runConversationId ? (
                        <Link
                          to={`/chat/conversation/${runConversationId}?workflow=${encodeURIComponent(name)}`}
                          className="flex items-center gap-2.5 rounded-lg border border-border bg-canvas/40 px-3 py-2.5 no-underline transition-colors hover:bg-raised/60"
                        >
                          <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-accent-soft text-accent">
                            <FileText className="size-3.5" strokeWidth={1.9} />
                          </span>
                          <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground">
                            View final answer
                          </span>
                          <ArrowUpRight className="size-3.5 shrink-0 text-subtle" />
                        </Link>
                      ) : null}
                    </div>
                  ) : (
                    <p className="mt-8 text-center text-[12px] text-subtle">
                      Run the workflow to see each agent&apos;s steps here.
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
                <WorkflowHistory
                  workflowId={workflowId ?? ''}
                  workflowName={name}
                  refreshKey={runConversationId ? 1 : 0}
                />
              </div>
            )}
          </aside>
        </div>

        <Dialog
          open={detailsOpen}
          onOpenChange={setDetailsOpen}
          title={workflowId ? 'Workflow details' : 'New workflow'}
          description="A name and description shown in your workflow list."
          size="md"
          footer={
            <>
              <Button variant="ghost" size="sm" onClick={() => setDetailsOpen(false)}>
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={() => {
                  setName(draftName)
                  setDescription(draftDescription)
                  setDetailsOpen(false)
                }}
              >
                Apply
              </Button>
            </>
          }
        >
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-[11px] font-medium tracking-wide text-subtle uppercase">
                Name
              </label>
              <input
                value={draftName}
                onChange={(event) => setDraftName(event.target.value)}
                placeholder="research-pipeline"
                className="w-full rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] text-foreground outline-none placeholder:text-subtle focus-visible:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/25"
              />
              {validateWorkflowName(draftName) ? (
                <p className="mt-1 text-[11px] text-accent">{validateWorkflowName(draftName)}</p>
              ) : null}
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-medium tracking-wide text-subtle uppercase">
                Description
              </label>
              <textarea
                value={draftDescription}
                onChange={(event) => setDraftDescription(event.target.value)}
                rows={3}
                placeholder="What does this workflow do?"
                className="w-full resize-y rounded-md border border-border-strong bg-canvas px-3 py-2 text-[13px] leading-relaxed text-foreground outline-none placeholder:text-subtle focus-visible:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/25"
              />
              {validateWorkflowDescription(draftDescription) ? (
                <p className="mt-1 text-[11px] text-accent">
                  {validateWorkflowDescription(draftDescription)}
                </p>
              ) : null}
            </div>
          </div>
        </Dialog>

        <ConfirmDialog
          open={confirmDelete}
          onOpenChange={setConfirmDelete}
          title="Delete this workflow?"
          description="This permanently removes the workflow. Your agents are not affected."
          confirmLabel="Delete"
          destructive
          onConfirm={handleDelete}
        />
      </div>
    </WorkflowBuilderProvider>
  )
}

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type MouseEvent as ReactMouseEvent,
  type RefObject,
} from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import {
  addEdge,
  Background,
  BackgroundVariant,
  ReactFlow,
  useEdgesState,
  useNodesInitialized,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type OnConnect,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import {
  Bot,
  Loader2,
  Pencil,
  Save,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { useAuth0 } from '@auth0/auth0-react'
import { toast } from 'sonner'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { Spinner } from '../components/ui/Spinner'
import { AgentNodeView, type AgentFlowNode } from '../components/agent-builder/AgentNode'
import {
  AgentEdgeDialog,
  AgentNodeDialog,
} from '../components/agent-builder/AgentNodeDialog'
import { AgentBuilderProvider } from '../components/agent-builder/AgentBuilderContext'
import { AgentDetailsDialog } from '../components/agent-builder/AgentDetailsDialog'
import { AgentEventsPanel } from '../components/agent-builder/AgentEventsPanel'
import { useApiClient, ApiError } from '../lib/api'
import { useDemoMode } from '../auth/useDemoMode'
import { IDS } from '../lib/demo/shared'
import { streamDemoAgentRun } from '../lib/demo/demoRun'
import { agentRunConfigured, runAgentStream } from '../lib/agentRun'
import { createRunFields, markRunError, reduceRunEvent, type RunFields } from '../lib/runState'
import type { Conversation } from '../lib/conversations'
import { useKnowledgeBases } from '../lib/knowledgeBases'
import { useAgentSkills } from '../lib/agentSkills'
import { fetchMcpTools } from '../lib/mcp'
import { useCustomServerOptions } from '../lib/customTools'
import {
  BUILTIN_AGENT_SERVERS,
  clearAgentDraft,
  configFromGraph,
  createAgent,
  createNode,
  defaultAgentGraph,
  deleteAgent,
  fetchAgent,
  graphFromConfig,
  invalidateAgents,
  loadAgentDraft,
  publishAgent,
  saveAgentDraft,
  unpublishAgent,
  updateAgent,
  useAgents,
  useMcpConnectionOptions,
  validateAgentDescription,
  validateAgentName,
  type AgentDetail,
  type AgentEvent,
  type AgentEventInput,
  type AgentGraphEdge,
  type AgentGraphNode,
  type AgentNodeData,
  type AgentServerSelection,
  type AgentStatus,
  type AgentVisibility,
  type ConnectionOption,
} from '../lib/agents'

const nodeTypes = {
  input: AgentNodeView,
  agent: AgentNodeView,
  knowledge: AgentNodeView,
  skills: AgentNodeView,
  tools: AgentNodeView,
  output: AgentNodeView,
  schedule: AgentNodeView,
}

/**
 * Keeps the graph fitted to the canvas that sits left of the events panel.
 *
 * The `fitView` prop runs before custom nodes report their measured size, so it
 * silently no-ops and the graph stays at zoom 1 and spills to the right. This
 * waits for `useNodesInitialized`, then also re-fits whenever the container is
 * resized (window, sidebar toggle, etc.).
 */
function FitController({ containerRef }: { containerRef: RefObject<HTMLDivElement | null> }) {
  const { fitView } = useReactFlow()
  const initialized = useNodesInitialized()
  const fitted = useRef(false)

  const fit = useCallback(() => {
    void fitView({ padding: 0.08, maxZoom: 1, duration: 0 })
  }, [fitView])

  useEffect(() => {
    if (!initialized || fitted.current) return
    fitted.current = true
    fit()
  }, [initialized, fit])

  useEffect(() => {
    const element = containerRef.current
    if (!element) return
    let raf = 0
    const observer = new ResizeObserver(() => {
      if (!fitted.current) return
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(fit)
    })
    observer.observe(element)
    return () => {
      observer.disconnect()
      cancelAnimationFrame(raf)
    }
  }, [containerRef, fit])

  return null
}

const STATUS_PILL: Record<AgentStatus, { wrap: string; dot: string }> = {
  draft: { wrap: 'border-border bg-raised text-muted', dot: 'bg-subtle' },
  verified: { wrap: 'border-info/25 bg-info-soft text-info', dot: 'bg-info' },
  published: { wrap: 'border-success/25 bg-success-soft text-success', dot: 'bg-success' },
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong'
}

export function AgentBuilderPage() {
  const api = useApiClient()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const demo = useDemoMode()
  // In the read-only demo, open a fully-configured saved agent instead of an
  // empty draft, so the knowledge / tools / skills cards and History are visible.
  const agentId = searchParams.get('agent') ?? (demo ? IDS.agentResearch : null)
  // The demo replays a scripted run, so no run URL is required.
  const configured = demo || agentRunConfigured()

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [nodes, setNodes, onNodesChange] = useNodesState<AgentFlowNode>([])
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([])
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null)
  const [editingEdgeId, setEditingEdgeId] = useState<string | null>(null)

  const [status, setStatus] = useState<AgentStatus>('draft')
  const [visibility, setVisibility] = useState<AgentVisibility>('private')
  const [, setPublishedAt] = useState<string | null>(null)

  const [loading, setLoading] = useState(Boolean(agentId))
  const [saving, setSaving] = useState(false)
  const [publishing, setPublishing] = useState(false)
  const [dirty, setDirty] = useState(false)
  const [confirmPublish, setConfirmPublish] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [detailsOpen, setDetailsOpen] = useState(false)
  const [detailsErrorRequest, setDetailsErrorRequest] = useState(false)
  const [serverNameError, setServerNameError] = useState<string | null>(null)

  const [events, setEvents] = useState<AgentEvent[]>([])
  const [run, setRun] = useState<RunFields | null>(null)
  const [running, setRunning] = useState(false)
  const [runConversationId, setRunConversationId] = useState('')
  const [historyKey, setHistoryKey] = useState(0)
  const runAbortRef = useRef<AbortController | null>(null)
  const { getAccessTokenSilently } = useAuth0()

  const hydratedRef = useRef(false)
  const loadedIdRef = useRef<string | null>(null)
  const snapshotRef = useRef('')
  const canvasRef = useRef<HTMLDivElement>(null)
  const nodesRef = useRef(nodes)
  const edgesRef = useRef(edges)
  useEffect(() => {
    nodesRef.current = nodes
  }, [nodes])
  useEffect(() => {
    edgesRef.current = edges
  }, [edges])

  const kbs = useKnowledgeBases()
  const skills = useAgentSkills()
  const connectionsQuery = useMcpConnectionOptions()
  const customToolsQuery = useCustomServerOptions()
  const agentsQuery = useAgents()

  const knowledgeBases = useMemo(() => kbs.data?.knowledgeBases ?? [], [kbs.data])
  const skillList = useMemo(() => skills.data?.skills ?? [], [skills.data])
  const connections = useMemo<ConnectionOption[]>(
    () => connectionsQuery.data ?? [],
    [connectionsQuery.data],
  )
  const customServers = useMemo(
    () => customToolsQuery.servers,
    [customToolsQuery.servers],
  )

  const pushEvents = useCallback((inputs: AgentEventInput[]) => {
    if (inputs.length === 0) return
    const at = new Date().toISOString()
    setEvents((current) =>
      [
        ...inputs.map((input, index) => ({
          ...input,
          id: `${at}-${index}-${Math.random().toString(36).slice(2, 6)}`,
          at,
        })),
        ...current,
      ].slice(0, 120),
    )
  }, [])

  const editingNode = useMemo(
    () => nodes.find((node) => node.id === editingNodeId) ?? null,
    [nodes, editingNodeId],
  )
  const editingEdge = useMemo(
    () => edges.find((edge) => edge.id === editingEdgeId) ?? null,
    [edges, editingEdgeId],
  )

  const config = useMemo(
    () =>
      configFromGraph(
        nodes as unknown as AgentGraphNode[],
        edges as unknown as AgentGraphEdge[],
      ),
    [nodes, edges],
  )

  const serialized = useMemo(
    () => JSON.stringify({ name, description, config }),
    [name, description, config],
  )

  const nameError = validateAgentName(name)
  const descriptionError = validateAgentDescription(description)

  // Names are unique per user; check the cached list before hitting the API.
  const duplicateNameError = useMemo(() => {
    const trimmed = name.trim()
    if (!trimmed || nameError) return null
    const clash = (agentsQuery.data?.agents ?? []).some(
      (agent) => agent.id !== agentId && agent.name === trimmed,
    )
    return clash ? `An agent named "${trimmed}" already exists` : null
  }, [agentsQuery.data, agentId, name, nameError])

  const nameErrorShown = nameError ?? duplicateNameError ?? serverNameError
  const canSave = !nameErrorShown && !descriptionError

  const otherAgentNames = useMemo(
    () =>
      (agentsQuery.data?.agents ?? [])
        .filter((agent) => agent.id !== agentId)
        .map((agent) => agent.name),
    [agentsQuery.data, agentId],
  )

  // --- load ------------------------------------------------------------------

  const applyDetail = useCallback(
    (detail: AgentDetail) => {
      loadedIdRef.current = detail.id
      setName(detail.name)
      setDescription(detail.description ?? '')
      const graph = graphFromConfig(detail.config)
      setNodes(graph.nodes as unknown as AgentFlowNode[])
      setEdges(graph.edges as unknown as Edge[])
      setStatus(detail.status)
      setVisibility(detail.visibility)
      setPublishedAt(detail.publishedAt)
      snapshotRef.current = JSON.stringify({
        name: detail.name,
        description: detail.description ?? '',
        config: detail.config,
      })
      setEvents([])
      pushEvents([{ kind: 'info', title: 'Agent loaded', scope: 'milestone' }])
    },
    [pushEvents, setEdges, setNodes],
  )

  useEffect(() => {
    if (agentId && loadedIdRef.current === agentId) return
    let active = true
    hydratedRef.current = false
    setLoading(Boolean(agentId))

    async function load() {
      if (agentId) {
        try {
          const detail = await fetchAgent(api, agentId)
          if (!active) return
          applyDetail(detail)
          // The demo is read-only and must always show the canonical saved
          // agent — never a stale local draft that overrides its cards.
          if (demo) {
            clearAgentDraft(agentId)
            clearAgentDraft(null)
          }
          const draft = demo ? null : loadAgentDraft(agentId)
          if (draft) {
            setName(draft.name)
            setDescription(draft.description)
            const graph = graphFromConfig(draft.config)
            setNodes(graph.nodes as unknown as AgentFlowNode[])
            setEdges(graph.edges as unknown as Edge[])
            pushEvents([{ kind: 'info', title: 'Restored unsaved local draft', scope: 'milestone' }])
            setDirty(true)
          }
        } catch (error) {
          if (active) {
            toast.error(errorMessage(error))
            navigate('/agent-store')
          }
        } finally {
          if (active) {
            setLoading(false)
            hydratedRef.current = true
          }
        }
        return
      }

      const draft = demo ? null : loadAgentDraft(null)
      const graph = draft ? graphFromConfig(draft.config) : defaultAgentGraph()
      setName(draft?.name ?? '')
      setDescription(draft?.description ?? '')
      setNodes(graph.nodes as unknown as AgentFlowNode[])
      setEdges(graph.edges as unknown as Edge[])
      setStatus('draft')
      setVisibility('private')
      setPublishedAt(null)
      setEvents([])
      pushEvents([{ kind: 'info', title: draft ? 'Restored unsaved local draft' : 'New agent', scope: 'milestone' }])
      setLoading(false)
      hydratedRef.current = true
    }

    void load()
    return () => {
      active = false
    }
  }, [agentId, api, applyDetail, demo, navigate, pushEvents, setEdges, setNodes])

  // --- autosave (localStorage) ----------------------------------------------

  useEffect(() => {
    if (!hydratedRef.current) return
    const isDirty = serialized !== snapshotRef.current
    setDirty(isDirty)
    // The demo never persists drafts, so its cards can't be shadowed later.
    if (!isDirty || demo) return
    const timer = window.setTimeout(() => {
      saveAgentDraft(agentId, { name, description, config })
    }, 500)
    return () => window.clearTimeout(timer)
  }, [serialized, agentId, name, description, config, demo])

  // --- graph editing ---------------------------------------------------------

  const updateNodeData = useCallback(
    (id: string, patch: Partial<AgentNodeData>) => {
      setNodes((current) =>
        current.map((node) =>
          node.id === id ? { ...node, data: { ...node.data, ...patch } } : node,
        ),
      )
    },
    [setNodes],
  )

  const updateEdgeData = useCallback(
    (id: string, patch: { mode?: 'always' | 'on_demand'; label?: string }) => {
      setEdges((current) =>
        current.map((edge) =>
          edge.id === id ? { ...edge, data: { ...edge.data, ...patch } } : edge,
        ),
      )
    },
    [setEdges],
  )

  const deleteEdge = useCallback(
    (id: string) => {
      setEdges((current) => current.filter((edge) => edge.id !== id))
      setEditingEdgeId((current) => (current === id ? null : current))
    },
    [setEdges],
  )

  const openNodeEditor = useCallback((id: string) => {
    setEditingEdgeId(null)
    setEditingNodeId(id)
  }, [])

  const handleSkillsChange = useCallback(
    (skillIds: string[]) => {
      const current = nodesRef.current
      const currentEdges = edgesRef.current
      let nextNodes = current.map((node) =>
        node.type === 'skills' ? { ...node, data: { ...node.data, skillIds } } : node,
      )

      const required = new Set<string>()
      skillIds.forEach((id) => {
        const skill = skillList.find((entry) => entry.id === id)
        skill?.allowedTools.forEach((tool) => required.add(tool))
      })

      if (required.size > 0) {
        const toolsNode = nextNodes.find((node) => node.type === 'tools')
        const existing = toolsNode?.data.servers ?? []
        const additions: AgentServerSelection[] = []
        required.forEach((token) => {
          if (existing.some((server) => server.id === token || slugify(server.name) === token)) {
            return
          }
          const builtin = BUILTIN_AGENT_SERVERS.find((server) => server.id === token)
          if (builtin) {
            additions.push({
              id: builtin.id,
              name: builtin.name,
              source: 'builtin',
              tools: null,
            })
            return
          }
          const connection = connections.find((entry) => slugify(entry.name) === token)
          if (connection) {
            additions.push({
              id: connection.id,
              name: connection.name,
              source: 'mcp',
              tools: null,
            })
          }
        })

        if (additions.length > 0) {
          if (toolsNode) {
            nextNodes = nextNodes.map((node) =>
              node.id === toolsNode.id
                ? { ...node, data: { ...node.data, servers: [...existing, ...additions] } }
                : node,
            )
          } else {
            const toolsNodeNew = createNode(
              'tools',
              { x: 140 + (nextNodes.length % 4) * 240, y: 440 },
              { servers: additions },
            )
            nextNodes = [...nextNodes, toolsNodeNew as unknown as AgentFlowNode]
            const agentNode = nextNodes.find((node) => node.type === 'agent')
            if (agentNode) {
              setEdges([
                ...currentEdges,
                {
                  id: `e-${agentNode.id}-${toolsNodeNew.id}`,
                  source: agentNode.id,
                  target: toolsNodeNew.id,
                  data: { mode: 'always' },
                },
              ])
            }
          }
        }
      }

      setNodes(nextNodes)
    },
    [connections, setEdges, setNodes, skillList],
  )

  const onConnect: OnConnect = useCallback(
    (connection: Connection) =>
      setEdges((current) =>
        addEdge({ ...connection, id: `e-${connection.source}-${connection.target}` }, current),
      ),
    [setEdges],
  )

  const loadTools = useCallback((id: string) => fetchMcpTools(api, id), [api])

  const handleEdgeClick = useCallback((_event: ReactMouseEvent, edge: Edge) => {
    setEditingNodeId(null)
    setEditingEdgeId(edge.id)
  }, [])

  const defaultEdgeOptions = useMemo(
    () => ({ type: 'default', data: { mode: 'always' } }),
    [],
  )


  const builderContext = useMemo(
    () => ({
      knowledgeBases,
      skills: skillList,
      connections,
      customServers,
      updateNodeData,
      onSkillsChange: handleSkillsChange,
      openNodeEditor,
    }),
    [
      knowledgeBases,
      skillList,
      connections,
      customServers,
      updateNodeData,
      handleSkillsChange,
      openNodeEditor,
    ],
  )

  // --- actions ---------------------------------------------------------------

  const handleSave = useCallback(async (): Promise<AgentDetail | null> => {
    if (!canSave) {
      // Open the details dialog with the offending fields highlighted.
      setDetailsErrorRequest(true)
      setDetailsOpen(true)
      return null
    }
    setSaving(true)
    setServerNameError(null)
    try {
      const payload = { name, description, config }
      const saved = agentId
        ? await updateAgent(api, agentId, payload)
        : await createAgent(api, payload)
      clearAgentDraft(agentId)
      clearAgentDraft(null)
      invalidateAgents()
      loadedIdRef.current = saved.id
      snapshotRef.current = JSON.stringify({
        name: saved.name,
        description: saved.description ?? '',
        config: saved.config,
      })
      setStatus(saved.status)
      setVisibility(saved.visibility)
      setPublishedAt(saved.publishedAt)
      setDetailsErrorRequest(false)
      setDirty(false)
      if (!agentId) {
        navigate(`/agent-builder?agent=${saved.id}`, { replace: true })
      }
      toast.success('Agent saved')
      pushEvents([
        {
          kind: 'success',
          title: 'Agent saved', scope: 'milestone',
          detail: agentId ? 'Configuration updated' : 'Agent created',
        },
      ])
      return saved
    } catch (error) {
      // A name clash is a field error, not a transient failure.
      if (error instanceof ApiError && error.status === 409) {
        setServerNameError(error.message)
        setDetailsErrorRequest(true)
        setDetailsOpen(true)
        return null
      }
      toast.error(errorMessage(error))
      return null
    } finally {
      setSaving(false)
    }
  }, [agentId, api, canSave, config, description, name, navigate, pushEvents])

  const handleStopRun = useCallback(() => {
    runAbortRef.current?.abort()
    runAbortRef.current = null
    setRunning(false)
    pushEvents([{ kind: 'warning', title: 'Run stopped', scope: 'milestone' }])
  }, [pushEvents])

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
      let id = agentId
      if (!demo && (!id || dirty)) {
        const saved = await handleSave()
        if (!saved) return
        id = saved.id
      }
      if (!id) return

    const controller = new AbortController()
    runAbortRef.current = controller
    setRunning(true)
    setRun(createRunFields())
    setRunConversationId('')
    pushEvents([{ kind: 'info', title: 'Run started', scope: 'milestone' }])

    // Each test run is its own conversation (no continuation). Create it first
    // so the run is persisted and shows up in the History tab. The demo is
    // read-only: the run is scripted and nothing is persisted.
    let runConversationId: string = crypto.randomUUID()
    if (!demo) {
      try {
        const created = await api.post<Conversation>('/v1/conversations', {
          agentId: id,
          kind: 'run',
          title: query,
        })
        runConversationId = String(created.conversationId)
        setRunConversationId(runConversationId)
      } catch {
        // Persistence is best-effort: the run still executes with a local id.
      }
    }

    const onEvent = (event: Parameters<typeof reduceRunEvent>[1]) => {
      setRun((current) => (current ? reduceRunEvent(current, event) : current))
      switch (event.type) {
        case 'tool.start':
          pushEvents([
            {
              kind: 'tool',
              title: `Tool · ${event.name}`,
              detail: event.input ? JSON.stringify(event.input) : undefined,
            },
          ])
          break
        case 'run.completed':
          pushEvents([{ kind: 'success', title: 'Run completed', scope: 'milestone' }])
          break
        case 'run.error':
          pushEvents([{ kind: 'error', title: 'Run failed', detail: event.message }])
          break
        default:
          break
      }
    }

    try {
      if (demo) {
        await streamDemoAgentRun(name, onEvent, controller.signal)
      } else {
        const token = await getAccessTokenSilently()
        await runAgentStream({
          token,
          agentId: id,
          input: query,
          conversationId: runConversationId,
          signal: controller.signal,
          onEvent,
        })
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const message = errorMessage(error)
        toast.error(message)
        setRun((current) => (current ? markRunError(current, message) : current))
        pushEvents([{ kind: 'error', title: 'Run failed', detail: message }])
      }
    } finally {
      if (runAbortRef.current === controller) runAbortRef.current = null
      setRunning(false)
      setHistoryKey((key) => key + 1)
    }
    },
    [agentId, api, demo, dirty, getAccessTokenSilently, handleSave, name, pushEvents],
  )

  const handlePublish = useCallback(async () => {
    let id = agentId
    if (!id || dirty) {
      const saved = await handleSave()
      if (!saved) return
      id = saved.id
    }
    setPublishing(true)
    try {
      const updated = await publishAgent(api, id)
      setStatus(updated.status)
      setVisibility(updated.visibility)
      setPublishedAt(updated.publishedAt)
      invalidateAgents()
      toast.success('Agent published to the library')
      pushEvents([{ kind: 'success', title: 'Published to the library', scope: 'milestone' }])
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setPublishing(false)
      setConfirmPublish(false)
    }
  }, [agentId, api, dirty, handleSave, pushEvents])

  const handleUnpublish = useCallback(async () => {
    if (!agentId) return
    setPublishing(true)
    try {
      const updated = await unpublishAgent(api, agentId)
      setStatus(updated.status)
      setVisibility(updated.visibility)
      setPublishedAt(updated.publishedAt)
      invalidateAgents()
      toast.success('Agent removed from the library')
      pushEvents([{ kind: 'info', title: 'Removed from the library', scope: 'milestone' }])
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setPublishing(false)
    }
  }, [agentId, api, pushEvents])

  const handleDelete = useCallback(async () => {
    if (!agentId) return
    try {
      await deleteAgent(api, agentId)
      clearAgentDraft(agentId)
      invalidateAgents()
      toast.success('Agent deleted')
      navigate('/agent-store')
    } catch (error) {
      toast.error(errorMessage(error))
    } finally {
      setConfirmDelete(false)
    }
  }, [agentId, api, navigate])

  // --- render ----------------------------------------------------------------

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <Spinner size="lg" label="Loading agent…" />
      </div>
    )
  }

  return (
    <AgentBuilderProvider value={builderContext}>
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="relative flex min-h-[72px] shrink-0 items-center justify-between gap-4 border-b border-border bg-surface/80 px-4 py-2.5 backdrop-blur-md lg:px-5">
        <span className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-linear-to-r from-accent/70 via-border-strong to-transparent" />

        <div className="flex min-w-0 items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent shadow-control ring-1 ring-inset ring-accent/25">
            <Bot className="size-5" strokeWidth={1.9} />
          </span>

          <div className="flex min-w-0 flex-col">
            <button
              type="button"
              onClick={() => {
                setServerNameError(null)
                setDetailsOpen(true)
              }}
              title="Edit agent name and description"
              aria-label="Edit agent name and description"
              className="group/details -ml-1.5 flex min-w-0 flex-col items-start rounded-lg px-1.5 py-1 text-left transition-colors hover:bg-raised/60 focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span
                  className={`max-w-[280px] truncate text-[15px] font-semibold tracking-tight ${
                    name ? 'text-foreground' : 'text-subtle'
                  }`}
                >
                  {name || 'Untitled agent'}
                </span>
                <Pencil className="size-3 shrink-0 text-subtle transition-colors group-hover/details:text-foreground" />

                <span
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-medium capitalize ${STATUS_PILL[status].wrap}`}
                >
                  <span className={`size-1.5 rounded-full ${STATUS_PILL[status].dot}`} />
                  {status}
                </span>

                {visibility === 'public' ? <Badge variant="success">public</Badge> : null}
              </span>

              <span className="mt-0.5 max-w-[380px] truncate text-[12px] text-muted">
                {description || 'Add a short description…'}
              </span>
            </button>
          </div>
        </div>

        <div className="flex shrink-0 items-center gap-2">
          {agentId ? (
            <>
              <button
                type="button"
                onClick={() => setConfirmDelete(true)}
                title="Delete agent"
                aria-label="Delete agent"
                className="flex size-8 shrink-0 items-center justify-center rounded-lg border border-transparent text-subtle transition-colors hover:border-border hover:bg-raised hover:text-accent"
              >
                <Trash2 className="size-4" />
              </button>
              <span className="h-6 w-px bg-border" />
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
              <span className="pointer-events-none absolute -right-1 -top-1 size-2.5 rounded-full bg-accent ring-2 ring-surface" />
            ) : null}
          </span>

          {visibility === 'public' ? (
            <Button
              variant="outline"
              size="sm"
              icon={publishing ? <Loader2 className="size-3.5 animate-spin" /> : undefined}
              onClick={handleUnpublish}
              disabled={publishing}
            >
              Unpublish
            </Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              icon={<UploadCloud className="size-3.5" />}
              onClick={() => setConfirmPublish(true)}
              disabled={publishing}
            >
              Publish
            </Button>
          )}
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <div ref={canvasRef} className="relative min-h-0 min-w-0 flex-1 overflow-hidden">
        {/* Soft radial wash so the canvas is not a flat void in dark mode. */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(70%_55%_at_50%_0%,var(--app-raised),transparent_75%)]" />
        {/* React Flow needs a definite parent height; the flex parent resolves
            its height but leaves `height:auto`, so an absolute wrapper gives the
            graph a concrete box to fill. */}
        <div className="absolute inset-0">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_event, node) => openNodeEditor(node.id)}
            onEdgeClick={handleEdgeClick}
            defaultEdgeOptions={defaultEdgeOptions}
            deleteKeyCode={null}
            nodesDraggable={false}
            nodesConnectable={false}
            panOnDrag={false}
            panOnScroll={false}
            zoomOnScroll={false}
            zoomOnPinch={false}
            zoomOnDoubleClick={false}
            minZoom={0.3}
            maxZoom={2}
          >
            <Background
              variant={BackgroundVariant.Dots}
              gap={24}
              size={1}
              color="var(--app-border)"
            />
            <FitController containerRef={canvasRef} />
          </ReactFlow>
        </div>
        </div>

        <AgentEventsPanel
          events={events}
          run={run}
          running={running}
          onRun={handleRun}
          onStop={handleStopRun}
          configured={configured}
          agentId={agentId ?? ''}
          agentName={name}
          conversationId={runConversationId}
          refreshKey={historyKey}
        />
      </div>

      <AgentDetailsDialog
        open={detailsOpen}
        onOpenChange={(open) => {
          setDetailsOpen(open)
          if (!open) setDetailsErrorRequest(false)
        }}
        name={name}
        description={description}
        otherNames={otherAgentNames}
        serverNameError={serverNameError}
        showErrorsOnOpen={detailsErrorRequest}
        onClearServerNameError={() => setServerNameError(null)}
        onSave={(nextName, nextDescription) => {
          setName(nextName)
          setDescription(nextDescription)
          setServerNameError(null)
          setDetailsErrorRequest(false)
          setDetailsOpen(false)
        }}
      />

      <AgentNodeDialog
        node={editingNode ? (editingNode as unknown as AgentGraphNode) : null}
        onUpdateNode={updateNodeData}
        onSkillsChange={handleSkillsChange}
        loadTools={loadTools}
        onClose={() => setEditingNodeId(null)}
      />

      <AgentEdgeDialog
        edge={editingEdge ? (editingEdge as unknown as AgentGraphEdge) : null}
        onUpdate={updateEdgeData}
        onDelete={deleteEdge}
        onClose={() => setEditingEdgeId(null)}
      />

      <ConfirmDialog
        open={confirmPublish}
        onOpenChange={setConfirmPublish}
        title="Publish this agent?"
        description="Anyone on the workspace can find it in the Agents library and add a copy to their workspace."
        confirmLabel="Publish"
        loading={publishing}
        onConfirm={handlePublish}
      />

      <ConfirmDialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Delete this agent?"
        description="This permanently removes the agent. Published copies already added by others are not affected."
        confirmLabel="Delete"
        destructive
        onConfirm={handleDelete}
      />
    </div>
    </AgentBuilderProvider>
  )
}

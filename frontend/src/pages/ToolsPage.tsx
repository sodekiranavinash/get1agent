import { useEffect, useState, type ReactNode } from 'react'
import { motion } from 'framer-motion'
import {
  AlertCircle,
  Code2,
  ExternalLink,
  Globe,
  KeyRound,
  Loader2,
  Plug,
  Plus,
  RefreshCw,
  Search,
  Server,
  Settings2,
  Store,
  Trash2,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Dialog } from '../components/ui/Dialog'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Segmented } from '../components/ui/Segmented'
import { Skeleton } from '../components/ui/Skeleton'
import { Switch } from '../components/ui/Switch'
import { useApiClient } from '../lib/api'
import { usePageQuery } from '../hooks/usePageQuery'
import {
  authorizeMcpConnection,
  deleteMcpConnection,
  fetchMcpTools,
  openMcpOAuthPopup,
  refreshMcpConnection,
  searchMcpRegistry,
  setMcpApiKey,
  setMcpConnectionEnabled,
  setMcpToolEnabled,
  startMcpConnection,
  type McpCatalogServer,
  type McpConnection,
  type McpConnectionStatus,
  type McpRegistryServer,
  type McpServerOrigin,
  type McpTool,
  type StartConnectionResult,
} from '../lib/mcp'
import { fadeUp, stagger } from '../lib/motion'

const TOOLS_QUERY_KEY = 'tools'

// Accent-tinted pill used for the section call-to-action buttons.
const sectionCta =
  'rounded-full border-accent/30 bg-accent-soft/60 text-accent hover:border-accent/60 hover:bg-accent-soft hover:text-accent'

type BuiltInTool = {
  name: string
  description: string
  icon: LucideIcon
  tone: string
}

const builtInTools: BuiltInTool[] = [
  {
    name: 'Web Search Tool',
    description: 'Search the web for real-time information and citations.',
    icon: Search,
    tone: 'text-accent',
  },
  {
    name: 'Code Interpreter Tool',
    description: 'Run Python in a sandbox for data analysis and file processing.',
    icon: Code2,
    tone: 'text-success',
  },
]

const statusMeta: Record<
  McpConnectionStatus,
  { label: string; variant: 'default' | 'accent' | 'success' | 'warning' | 'info' }
> = {
  connected: { label: 'Connected', variant: 'success' },
  pending: { label: 'Setup', variant: 'info' },
  reauth_required: { label: 'Reconnect', variant: 'warning' },
  error: { label: 'Error', variant: 'warning' },
}

const originMeta: Record<
  McpServerOrigin,
  { label: string; variant: 'default' | 'accent' | 'success' | 'warning' | 'info'; icon: LucideIcon }
> = {
  builtin: { label: 'Built-in', variant: 'accent', icon: Code2 },
  remote: { label: 'Remote', variant: 'info', icon: Plug },
  marketplace: { label: 'Marketplace', variant: 'warning', icon: Store },
  public: { label: 'Public', variant: 'success', icon: Globe },
  registry: { label: 'MCP Registry', variant: 'default', icon: Server },
}

type CatalogTab = 'All' | 'One Agent Marketplace' | 'MCP Registry'
const CATALOG_TABS = ['All', 'One Agent Marketplace', 'MCP Registry'] as const

type AuthFilter = 'All' | 'OAuth' | 'No sign-in'
const AUTH_FILTERS = ['All', 'OAuth', 'No sign-in'] as const
const AUTH_FILTER_PARAM: Record<AuthFilter, 'oauth' | 'none' | undefined> = {
  All: undefined,
  OAuth: 'oauth',
  'No sign-in': 'none',
}

const authMeta: Record<
  string,
  { label: string; variant: 'default' | 'accent' | 'success' | 'warning' | 'info' }
> = {
  oauth: { label: 'OAuth', variant: 'info' },
  none: { label: 'No sign-in', variant: 'success' },
  apikey: { label: 'API key', variant: 'warning' },
  unknown: { label: 'Auth?', variant: 'default' },
}

function AuthTag({ auth }: { auth?: string | null }) {
  if (!auth) return null
  const meta = authMeta[auth] ?? authMeta.unknown
  return <Badge variant={meta.variant}>{meta.label}</Badge>
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong. Please try again.'
}

function SectionLabel({
  title,
  count,
  hint,
  action,
}: {
  title: string
  count?: number
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="mb-2 flex items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <h2 className="text-xs font-semibold text-foreground">{title}</h2>
        {typeof count === 'number' ? (
          <span className="rounded-md bg-raised px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-muted">
            {count}
          </span>
        ) : null}
      </div>
      {action ? (
        action
      ) : hint ? (
        <p className="hidden text-[11px] text-subtle sm:block">{hint}</p>
      ) : null}
    </div>
  )
}

function SubHeading({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="mb-2 flex items-baseline justify-between gap-3">
      <p className="text-[11px] font-semibold tracking-wide text-subtle uppercase">
        {title}
      </p>
      {hint ? <p className="truncate text-[11px] text-subtle">{hint}</p> : null}
    </div>
  )
}

function ToolsSkeleton() {
  return (
    <div className="space-y-5">
      <section>
        <Skeleton className="mb-2 h-4 w-40" />
        <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[96px] rounded-lg" />
          ))}
        </div>
      </section>
      <section>
        <Skeleton className="mb-2 h-4 w-48" />
        <Skeleton className="mb-3 h-7 w-72 rounded-md" />
        <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-[104px] rounded-lg" />
          ))}
        </div>
      </section>
    </div>
  )
}

function OriginTag({ origin }: { origin: McpServerOrigin }) {
  const meta = originMeta[origin]
  const Icon = meta.icon
  return (
    <Badge variant={meta.variant}>
      <Icon className="size-3" strokeWidth={2} />
      {meta.label}
    </Badge>
  )
}

function BuiltInCard({ tool }: { tool: BuiltInTool }) {
  const Icon = tool.icon
  return (
    <div className="flex h-full items-center gap-3 rounded-lg border border-border bg-surface px-3 py-2.5 transition-colors duration-200 hover:border-accent/30">
      <span
        className={`flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised ${tool.tone}`}
      >
        <Icon className="size-3.5" strokeWidth={1.75} />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-1.5">
          <h3 className="truncate text-[13px] font-semibold text-foreground">
            {tool.name}
          </h3>
          <OriginTag origin="builtin" />
        </div>
        <p className="mt-0.5 truncate text-xs text-muted">{tool.description}</p>
      </div>
    </div>
  )
}

type ConnectionCardProps = {
  connection: McpConnection
  busy: boolean
  onToggle: (connection: McpConnection, enabled: boolean) => void
  onManage: (connection: McpConnection) => void
  onReconnect: (connection: McpConnection) => void
  onRefresh: (connection: McpConnection) => void
  onAddKey: (connection: McpConnection) => void
  onDisconnect: (connection: McpConnection) => void
}

function ConnectionCard({
  connection,
  busy,
  onToggle,
  onManage,
  onReconnect,
  onRefresh,
  onAddKey,
  onDisconnect,
}: ConnectionCardProps) {
  const meta = statusMeta[connection.status] ?? statusMeta.error
  const enabled = connection.enabled !== false
  const needsAuth =
    connection.status === 'reauth_required' || connection.status === 'pending'
  const needsKey = connection.authType === 'apikey' && connection.status !== 'connected'

  return (
    <div
      className={`flex h-full flex-col gap-3 rounded-lg border border-border bg-surface p-3 transition-colors duration-200 hover:border-accent/30 ${
        enabled ? '' : 'opacity-60'
      }`}
    >
      <div className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-warning">
          {connection.authType === 'apikey' ? (
            <KeyRound className="size-3.5" strokeWidth={1.75} />
          ) : (
            <Plug className="size-3.5" strokeWidth={1.75} />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <h3 className="truncate text-[13px] font-semibold text-foreground">
              {connection.name}
            </h3>
            {connection.catalogId ? (
              <Badge variant="default">1agent</Badge>
            ) : (
              <OriginTag origin="registry" />
            )}
            <Badge variant={meta.variant} dot>
              {meta.label}
            </Badge>
          </div>
          {connection.description ? (
            <p className="mt-0.5 line-clamp-2 text-xs text-muted">
              {connection.description}
            </p>
          ) : null}
          <p className="mt-0.5 truncate text-[11px] text-subtle">{connection.serverUrl}</p>
          {connection.status === 'connected' && connection.toolCount > 0 ? (
            <p className="mt-0.5 text-[11px] text-subtle">
              {connection.toolCount} tools
            </p>
          ) : null}
          {connection.lastError && connection.status !== 'connected' ? (
            <p className="mt-0.5 line-clamp-2 text-[11px] text-warning">
              {connection.lastError}
            </p>
          ) : null}
        </div>
        <Switch
          checked={enabled}
          onChange={(next) => onToggle(connection, next)}
          disabled={busy}
          label={`${enabled ? 'Disable' : 'Enable'} ${connection.name}`}
        />
      </div>
      <div className="mt-auto flex items-center justify-between gap-2">
        <AuthTag auth={connection.authType} />
        <div className="flex items-center gap-1.5">
          {connection.status === 'connected' ? (
            <Button
              variant="outline"
              size="sm"
              icon={<Settings2 className="size-3.5" />}
              disabled={busy}
              onClick={() => onManage(connection)}
            >
              Manage
            </Button>
          ) : null}
          {needsKey ? (
            <Button variant="outline" size="sm" disabled={busy} onClick={() => onAddKey(connection)}>
              Add key
            </Button>
          ) : null}
          {needsAuth ? (
            <Button variant="outline" size="sm" disabled={busy} onClick={() => onReconnect(connection)}>
              Reconnect
            </Button>
          ) : null}
          {connection.status === 'error' ? (
            <Button
              variant="outline"
              size="sm"
              icon={<RefreshCw className="size-3.5" />}
              disabled={busy}
              onClick={() => onRefresh(connection)}
            >
              Retry
            </Button>
          ) : null}
          <Button
            variant="ghost"
            size="sm"
            icon={<Trash2 className="size-3.5" />}
            disabled={busy}
            onClick={() => onDisconnect(connection)}
          >
            Remove
          </Button>
        </div>
      </div>
    </div>
  )
}

type CatalogItem = {
  id: string
  name: string
  description: string
  docsUrl: string | null
  serverUrl: string
  source: string
  owner?: string | null
  origin?: McpServerOrigin
  auth?: string | null
}

type CatalogCardProps = {
  item: CatalogItem
  connected: boolean
  busy: boolean
  onConnect: (item: CatalogItem) => void
}

function CatalogCard({ item, connected, busy, onConnect }: CatalogCardProps) {
  return (
    <div className="flex h-full flex-col justify-between gap-3 rounded-lg border border-border bg-surface p-3 transition-colors duration-200 hover:border-accent/30">
      <div className="flex items-start gap-3">
        <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
          <Globe className="size-3.5" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <h3 className="truncate text-[13px] font-semibold text-foreground">
              {item.name}
            </h3>
            {item.owner ? (
              <Badge variant="default">{item.owner}</Badge>
            ) : (
              <OriginTag origin={item.origin ?? (item.source === 'marketplace' ? 'marketplace' : 'public')} />
            )}
          </div>
          <p className="mt-0.5 line-clamp-2 text-xs text-muted">{item.description}</p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AuthTag auth={item.auth} />
          {item.docsUrl ? (
            <a
              href={item.docsUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 text-[11px] text-subtle transition-colors hover:text-foreground"
            >
              Docs
              <ExternalLink className="size-3" />
            </a>
          ) : null}
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={connected || busy}
          onClick={() => onConnect(item)}
        >
          {connected ? 'Connected' : 'Connect'}
        </Button>
      </div>
    </div>
  )
}

function ManageToolsDialog({
  connection,
  onClose,
}: {
  connection: McpConnection | null
  onClose: () => void
}) {
  const api = useApiClient()
  const [tools, setTools] = useState<McpTool[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyTool, setBusyTool] = useState<string | null>(null)

  useEffect(() => {
    if (!connection) return
    let cancelled = false
    setTools(null)
    setError(null)
    setLoading(true)
    fetchMcpTools(api, connection.id)
      .then((result) => {
        if (!cancelled) setTools(result)
      })
      .catch((err) => {
        if (!cancelled) setError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, connection])

  const toggle = async (tool: McpTool, enabled: boolean) => {
    if (!connection) return
    setBusyTool(tool.name)
    try {
      const updated = await setMcpToolEnabled(api, connection.id, tool.name, enabled)
      setTools(updated)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusyTool(null)
    }
  }

  const enabledCount = tools?.filter((tool) => tool.enabled).length ?? 0

  return (
    <Dialog
      open={connection !== null}
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      title={connection ? `${connection.name} tools` : 'Tools'}
      description="Only enabled tools are exposed to your agents, skills and workflows."
      size="lg"
      footer={
        <Button variant="ghost" onClick={onClose}>
          Done
        </Button>
      }
    >
      {loading ? (
        <div className="space-y-3">
          {[0, 1, 2].map((i) => (
            <Skeleton key={i} className="h-12 rounded-md" />
          ))}
        </div>
      ) : error ? (
        <div className="flex items-start gap-2.5 rounded-md border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <p className="text-sm text-foreground">{error}</p>
        </div>
      ) : tools && tools.length > 0 ? (
        <div className="space-y-3">
          <p className="text-[11px] text-subtle">
            {enabledCount} of {tools.length} tools enabled
          </p>
          <div className="divide-y divide-border rounded-lg border border-border">
            {tools.map((tool) => (
              <div key={tool.name} className="flex items-start gap-3 px-3.5 py-3">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs font-medium text-foreground">
                    {tool.name}
                  </p>
                  {tool.description ? (
                    <p className="mt-0.5 line-clamp-2 text-xs text-muted">
                      {tool.description}
                    </p>
                  ) : null}
                </div>
                <Switch
                  checked={tool.enabled}
                  onChange={(next) => toggle(tool, next)}
                  disabled={busyTool === tool.name}
                  label={`${tool.enabled ? 'Disable' : 'Enable'} ${tool.name}`}
                />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="py-6 text-center text-[13px] text-muted">
          <Settings2 className="mx-auto mb-2 size-4 text-subtle" strokeWidth={1.5} />
          This server has not reported any tools yet.
        </p>
      )}
    </Dialog>
  )
}

export function ToolsPage() {
  const api = useApiClient()
  const { data, isPending, error, refetch } = usePageQuery(
    TOOLS_QUERY_KEY,
    async () => {
      const [connections, catalog] = await Promise.all([
        api.get<{ connections: McpConnection[] }>('/v1/mcp/connections'),
        api.get<{ servers: McpCatalogServer[] }>('/v1/mcp/catalog'),
      ])
      return { connections: connections.connections, catalog: catalog.servers }
    },
    { refetchOnMount: true },
  )

  const [addOpen, setAddOpen] = useState(false)
  const [name, setName] = useState('')
  const [url, setUrl] = useState('')
  const [description, setDescription] = useState('')
  const [formError, setFormError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [keyFor, setKeyFor] = useState<McpConnection | null>(null)
  const [apiKey, setApiKey] = useState('')
  const [manageFor, setManageFor] = useState<McpConnection | null>(null)
  const [tab, setTab] = useState<CatalogTab>('All')
  const [registryQuery, setRegistryQuery] = useState('')
  const [registrySearch, setRegistrySearch] = useState('')
  const [registryServers, setRegistryServers] = useState<McpRegistryServer[]>([])
  const [registryCursor, setRegistryCursor] = useState<string | null>(null)
  const [registryPending, setRegistryPending] = useState(false)
  const [registryMore, setRegistryMore] = useState(false)
  const [registryError, setRegistryError] = useState<string | null>(null)
  const [authFilter, setAuthFilter] = useState<AuthFilter>('All')

  const connections = data?.connections ?? []
  const catalog = data?.catalog ?? []
  const connectedUrls = new Set(
    connections
      .filter((connection) => connection.status === 'connected')
      .map((connection) => connection.serverUrl),
  )
  const marketplaceServers: CatalogItem[] = catalog.map((server) => ({
    ...server,
    owner: '1agent',
    auth: server.authType,
  }))
  const showRegistry = tab !== 'One Agent Marketplace'

  useEffect(() => {
    const handle = setTimeout(() => setRegistrySearch(registryQuery.trim()), 400)
    return () => clearTimeout(handle)
  }, [registryQuery])

  useEffect(() => {
    if (tab === 'One Agent Marketplace') return
    let cancelled = false
    setRegistryPending(true)
    setRegistryError(null)
    searchMcpRegistry(api, {
      search: registrySearch || undefined,
      auth: AUTH_FILTER_PARAM[authFilter],
    })
      .then((result) => {
        if (cancelled) return
        setRegistryServers(result.servers)
        setRegistryCursor(result.nextCursor)
      })
      .catch((err) => {
        if (!cancelled) setRegistryError(errorMessage(err))
      })
      .finally(() => {
        if (!cancelled) setRegistryPending(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, registrySearch, tab, authFilter])

  const loadMoreRegistry = async () => {
    if (!registryCursor) return
    setRegistryMore(true)
    try {
      const result = await searchMcpRegistry(api, {
        search: registrySearch || undefined,
        cursor: registryCursor,
        auth: AUTH_FILTER_PARAM[authFilter],
      })
      setRegistryServers((prev) => [...prev, ...result.servers])
      setRegistryCursor(result.nextCursor)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setRegistryMore(false)
    }
  }

  const connectRegistry = async (server: CatalogItem) => {
    setBusyId(server.id)
    try {
      const result = await startMcpConnection(api, {
        name: server.name,
        url: server.serverUrl,
        description: server.description || undefined,
      })
      await runOAuth(result)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const runOAuth = async (result: StartConnectionResult) => {
    if (result.authorizationUrl) {
      const ok = await openMcpOAuthPopup(result.authorizationUrl)
      if (!ok) toast.error('Authorization was not completed')
    }
    refetch()
  }

  const openAdd = () => {
    setName('')
    setUrl('')
    setDescription('')
    setFormError(null)
    setAddOpen(true)
  }

  const createServer = () => {
    toast.info('Creating and publishing your own MCP server is coming soon')
  }

  const submitCustom = async () => {
    setFormError(null)
    if (!name.trim()) {
      setFormError('Give the server a name')
      return
    }
    let parsed: URL
    try {
      parsed = new URL(url.trim())
    } catch {
      setFormError('Enter a valid server URL')
      return
    }
    if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
      setFormError('Server URL must start with https://')
      return
    }
    setSubmitting(true)
    try {
      const result = await startMcpConnection(api, {
        name: name.trim(),
        url: parsed.toString(),
        description: description.trim() || undefined,
      })
      setAddOpen(false)
      await runOAuth(result)
    } catch (err) {
      setFormError(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  const connectCatalog = async (item: CatalogItem) => {
    setBusyId(item.id)
    try {
      const result = await startMcpConnection(api, { catalogId: item.id })
      await runOAuth(result)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const handleToggle = async (connection: McpConnection, enabled: boolean) => {
    setBusyId(connection.id)
    try {
      await setMcpConnectionEnabled(api, connection.id, enabled)
      toast.success(`${connection.name} ${enabled ? 'enabled' : 'disabled'}`)
      refetch()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const handleReconnect = async (connection: McpConnection) => {
    setBusyId(connection.id)
    try {
      const result = await authorizeMcpConnection(api, connection.id)
      await runOAuth(result)
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const handleRefresh = async (connection: McpConnection) => {
    setBusyId(connection.id)
    try {
      await refreshMcpConnection(api, connection.id)
      toast.success(`${connection.name} refreshed`)
      refetch()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const handleDisconnect = async (connection: McpConnection) => {
    setBusyId(connection.id)
    try {
      await deleteMcpConnection(api, connection.id)
      toast.success(`${connection.name} removed`)
      refetch()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setBusyId(null)
    }
  }

  const submitApiKey = async () => {
    if (!keyFor) return
    if (!apiKey.trim()) {
      toast.error('Enter the API key')
      return
    }
    setSubmitting(true)
    try {
      await setMcpApiKey(api, keyFor.id, apiKey.trim())
      setKeyFor(null)
      setApiKey('')
      toast.success(`${keyFor.name} connected`)
      refetch()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="MCP Tools"
        description="Built-in, remote, marketplace and public MCP servers your agents can use."
        badge="Build"
      />

      {isPending ? (
        <ToolsSkeleton />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-6">
          <section>
            <SectionLabel
              title="Your MCP Servers"
              count={builtInTools.length + connections.length}
              action={
                <Button
                  variant="outline"
                  size="md"
                  icon={<Plus className="size-3.5" />}
                  className={sectionCta}
                  onClick={createServer}
                >
                  Create MCP Server
                </Button>
              }
            />
            <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
              {builtInTools.map((tool) => (
                <motion.div key={tool.name} variants={fadeUp}>
                  <BuiltInCard tool={tool} />
                </motion.div>
              ))}
              {connections.map((connection) => (
                <motion.div key={connection.id} variants={fadeUp}>
                  <ConnectionCard
                    connection={connection}
                    busy={busyId === connection.id}
                    onToggle={handleToggle}
                    onManage={setManageFor}
                    onReconnect={handleReconnect}
                    onRefresh={handleRefresh}
                    onAddKey={setKeyFor}
                    onDisconnect={handleDisconnect}
                  />
                </motion.div>
              ))}
            </div>
          </section>

          <section>
            <SectionLabel
              title="Available MCP Servers"
              action={
                <Button
                  variant="outline"
                  size="md"
                  icon={<Plus className="size-3.5" />}
                  className={sectionCta}
                  onClick={openAdd}
                >
                  Remote MCP Server
                </Button>
              }
            />
            <div className="mb-4 w-full lg:w-[30rem]">
              <Segmented options={CATALOG_TABS} value={tab} onChange={setTab} size="sm" />
            </div>

            <div className="space-y-6">
              {tab === 'All' || tab === 'One Agent Marketplace' ? (
                <div>
                  <SubHeading title="One Agent Marketplace" hint="Curated by us · published by users" />
                  {marketplaceServers.length > 0 ? (
                    <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                      {marketplaceServers.map((server) => (
                        <motion.div key={`marketplace-${server.id}`} variants={fadeUp}>
                          <CatalogCard
                            item={server}
                            connected={connectedUrls.has(server.serverUrl)}
                            busy={busyId === server.id}
                            onConnect={connectCatalog}
                          />
                        </motion.div>
                      ))}
                    </div>
                  ) : (
                    <Card padding="none" className="overflow-hidden">
                      <p className="px-4 py-6 text-center text-[13px] text-muted">
                        <Store className="mx-auto mb-2 size-4 text-subtle" strokeWidth={1.5} />
                        No published MCP servers yet. Servers users publish will appear here.
                      </p>
                    </Card>
                  )}
                </div>
              ) : null}

              {showRegistry ? (
                <div>
                  <div className="mb-2 flex items-baseline gap-2">
                    <p className="text-[11px] font-semibold tracking-wide text-subtle uppercase">
                      MCP Registry
                    </p>
                    <p className="truncate text-[11px] text-subtle">
                      {registrySearch
                        ? `Results for “${registrySearch}”`
                        : 'Live from the official registry'}
                    </p>
                  </div>
                  <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center">
                    <div className="relative w-full sm:w-80">
                      <Search
                        className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-subtle"
                        strokeWidth={2}
                      />
                      <input
                        value={registryQuery}
                        onChange={(event) => setRegistryQuery(event.target.value)}
                        placeholder="Search the MCP registry…"
                        className="h-9 w-full rounded-md border border-border bg-canvas pl-8 pr-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
                      />
                    </div>
                    <div className="w-full sm:w-60">
                      <Segmented
                        options={AUTH_FILTERS}
                        value={authFilter}
                        onChange={setAuthFilter}
                        size="sm"
                      />
                    </div>
                  </div>
                  {registryPending ? (
                    <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                      {[0, 1, 2].map((i) => (
                        <Skeleton key={i} className="h-[104px] rounded-lg" />
                      ))}
                    </div>
                  ) : registryError ? (
                    <Card padding="none" className="overflow-hidden">
                      <p className="px-4 py-6 text-center text-[13px] text-muted">
                        <AlertCircle className="mx-auto mb-2 size-4 text-warning" strokeWidth={1.5} />
                        Could not reach the MCP registry. Try again in a moment.
                      </p>
                    </Card>
                  ) : registryServers.length > 0 ? (
                    <>
                      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
                        {registryServers.map((server) => (
                          <motion.div key={server.id} variants={fadeUp}>
                            <CatalogCard
                              item={{ ...server, origin: 'registry', auth: server.auth }}
                              connected={connectedUrls.has(server.serverUrl)}
                              busy={busyId === server.id}
                              onConnect={connectRegistry}
                            />
                          </motion.div>
                        ))}
                      </div>
                      {registryCursor ? (
                        <div className="mt-3 flex justify-center">
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={registryMore}
                            icon={
                              registryMore ? (
                                <Loader2 className="size-3.5 animate-spin" />
                              ) : undefined
                            }
                            onClick={loadMoreRegistry}
                          >
                            {registryMore ? 'Loading…' : 'Load more'}
                          </Button>
                        </div>
                      ) : null}
                    </>
                  ) : (
                    <Card padding="none" className="overflow-hidden">
                      <p className="px-4 py-6 text-center text-[13px] text-muted">
                        <Globe className="mx-auto mb-2 size-4 text-subtle" strokeWidth={1.5} />
                        No remote MCP servers found.
                      </p>
                    </Card>
                  )}
                </div>
              ) : null}
            </div>
          </section>
        </motion.div>
      )}

      <Dialog
        open={addOpen}
        onOpenChange={setAddOpen}
        title="Add remote MCP server"
        description="Connect any hosted MCP endpoint — open or OAuth — and use its tools in your agents and skills."
        banner={
          formError ? (
            <div className="flex items-start gap-2.5 rounded-md border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
              <p className="text-sm text-foreground">{formError}</p>
            </div>
          ) : null
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setAddOpen(false)}>
              Cancel
            </Button>
            <Button onClick={submitCustom} disabled={submitting}>
              {submitting ? 'Connecting…' : 'Connect'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="flex items-start gap-2.5 rounded-md border border-border bg-raised/40 px-3.5 py-2.5">
            <Server className="mt-0.5 h-4 w-4 shrink-0 text-accent" strokeWidth={1.75} />
            <p className="text-[12px] leading-relaxed text-muted">
              A remote MCP server is any hosted endpoint that speaks the Model
              Context Protocol over HTTP. Paste its URL — we'll detect whether it
              is open or needs sign-in (OAuth) and guide you through it. Its tools
              then become available to your agents and skills.
            </p>
          </div>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              Name
            </span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. internal-tools"
              className="h-10 w-full rounded-md border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              Server URL
            </span>
            <input
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              placeholder="https://mcp.example.com/mcp"
              className="h-10 w-full rounded-md border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
            />
            <p className="mt-1.5 text-[11px] text-subtle">
              The MCP endpoint must be reachable over HTTPS. If it requires
              OAuth, you will be asked to authorize.
            </p>
          </label>
          <label className="block">
            <span className="mb-1.5 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted">
              <span>Description</span>
              <span className="normal-case text-subtle">optional</span>
            </span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What this server does, so you remember later"
              rows={2}
              className="min-h-[3.25rem] w-full resize-y rounded-md border border-border bg-canvas px-3 py-2 text-sm leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 scrollbar-thin"
            />
            <p className="mt-1.5 text-[11px] text-subtle">
              Shown on this server's card after you connect.
            </p>
          </label>
        </div>
      </Dialog>

      <ManageToolsDialog connection={manageFor} onClose={() => setManageFor(null)} />

      <Dialog
        open={keyFor !== null}
        onOpenChange={(open) => {
          if (!open) {
            setKeyFor(null)
            setApiKey('')
          }
        }}
        title={keyFor ? `Add API key for ${keyFor.name}` : 'Add API key'}
        description="The key is encrypted at rest and only used to call this server."
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setKeyFor(null)
                setApiKey('')
              }}
            >
              Cancel
            </Button>
            <Button onClick={submitApiKey} disabled={submitting}>
              {submitting ? 'Saving…' : 'Save'}
            </Button>
          </>
        }
      >
        <label className="block">
          <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
            API key
          </span>
          <input
            type="password"
            value={apiKey}
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="••••••••"
            className="h-10 w-full rounded-md border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50"
          />
        </label>
      </Dialog>
    </PageShell>
  )
}

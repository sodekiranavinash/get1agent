import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Bot, Download, Loader2, Pencil, Plus, Star } from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { Tabs, TabsList, TabsTrigger } from '../components/ui/tabs'
import { useApiClient } from '../lib/api'
import { fadeUp, stagger } from '../lib/motion'
import {
  agentModelLabel,
  installAgent,
  invalidateAgents,
  useAgentLibrary,
  useAgents,
  type Agent,
} from '../lib/agents'

const filters = ['all', 'mine', 'public'] as const
type Filter = (typeof filters)[number]

function statusVariant(status: Agent['status']) {
  return status === 'published' ? 'success' : status === 'verified' ? 'info' : 'default'
}

function AgentSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-start justify-between">
            <Skeleton className="size-10" />
            <Skeleton className="h-5 w-14" />
          </div>
          <Skeleton className="mt-3 h-4 w-32" />
          <Skeleton className="mt-2 h-3 w-full" />
          <Skeleton className="mt-4 h-7 w-full" />
        </div>
      ))}
    </div>
  )
}

export function AgentStorePage() {
  const api = useApiClient()
  const navigate = useNavigate()
  const [filter, setFilter] = useState<Filter>('all')
  const [installing, setInstalling] = useState<string | null>(null)

  const mine = useAgents()
  const library = useAgentLibrary()

  const myAgents = useMemo(() => mine.data?.agents ?? [], [mine.data])
  const publicAgents = useMemo(() => library.data?.agents ?? [], [library.data])
  const loading = mine.isPending && library.isPending

  const visible = useMemo(() => {
    if (filter === 'mine') return myAgents
    if (filter === 'public') return publicAgents
    const byId = new Map<string, Agent>()
    publicAgents.forEach((agent) => byId.set(agent.id, agent))
    myAgents.forEach((agent) => byId.set(agent.id, agent))
    return [...byId.values()]
  }, [filter, myAgents, publicAgents])

  async function handleInstall(id: string) {
    setInstalling(id)
    try {
      const created = await installAgent(api, id)
      invalidateAgents()
      toast.success('Agent added to your workspace')
      navigate(`/agent-builder?agent=${created.id}`)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not add the agent')
    } finally {
      setInstalling(null)
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Agents"
        description="Build custom agents and discover published agents you can add to your workspace."
        badge="Library"
        action={{
          label: 'New agent',
          icon: <Plus className="size-3.5" />,
          onClick: () => navigate('/agent-builder'),
        }}
      />

      <Tabs value={filter} onValueChange={(value) => setFilter(value as Filter)}>
        <TabsList>
          <TabsTrigger value="all">All</TabsTrigger>
          <TabsTrigger value="mine">My agents</TabsTrigger>
          <TabsTrigger value="public">Public</TabsTrigger>
        </TabsList>
      </Tabs>

      {loading ? (
        <div className="mt-3">
          <AgentSkeleton />
        </div>
      ) : visible.length === 0 ? (
        <div className="mt-3 flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface/50 px-6 py-16 text-center">
          <span className="flex size-10 items-center justify-center rounded-lg border border-border bg-raised text-muted">
            <Bot className="size-5" strokeWidth={1.75} />
          </span>
          <p className="mt-3 text-[13px] font-medium text-foreground">No agents yet</p>
          <p className="mt-1 max-w-sm text-xs text-muted">
            Use <span className="text-foreground">New agent</span> above to compose one from your
            knowledge bases, skills and MCP tools.
          </p>
        </div>
      ) : (
        <motion.div
          key={filter}
          variants={stagger}
          initial="hidden"
          animate="show"
          className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
        >
          {visible.map((agent) => {
            const isMine = agent.isMine ?? myAgents.some((entry) => entry.id === agent.id)
            const canInstall = !isMine && agent.visibility === 'public'
            return (
              <motion.div key={agent.id} variants={fadeUp}>
                <div className="group flex h-full flex-col rounded-lg border border-border bg-surface p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/30 hover:shadow-panel">
                  <div className="flex items-start justify-between gap-2">
                    <span className="flex size-10 items-center justify-center rounded-lg border border-border bg-raised text-accent">
                      <Bot className="size-5" strokeWidth={1.75} />
                    </span>
                    <Badge variant={statusVariant(agent.status)} dot>
                      {agent.status}
                    </Badge>
                  </div>

                  <h3 className="mt-3 truncate text-[13px] font-semibold text-foreground">
                    {agent.name}
                  </h3>
                  <p className="mt-0.5 line-clamp-2 min-h-[2rem] text-xs text-muted">
                    {agent.description || 'No description'}
                  </p>

                  <div className="mt-2 flex flex-wrap gap-1">
                    <span className="rounded border border-border bg-raised/50 px-1.5 py-0.5 text-[10px] text-subtle">
                      {agentModelLabel(agent.model)}
                    </span>
                    {agent.knowledgeBaseCount > 0 ? (
                      <span className="rounded border border-border bg-raised/50 px-1.5 py-0.5 text-[10px] text-subtle">
                        {agent.knowledgeBaseCount} KB
                      </span>
                    ) : null}
                    {agent.skillCount > 0 ? (
                      <span className="rounded border border-border bg-raised/50 px-1.5 py-0.5 text-[10px] text-subtle">
                        {agent.skillCount} skill
                      </span>
                    ) : null}
                    {agent.serverCount > 0 ? (
                      <span className="rounded border border-border bg-raised/50 px-1.5 py-0.5 text-[10px] text-subtle">
                        {agent.serverCount} server
                      </span>
                    ) : null}
                  </div>

                  <div className="mt-3 flex items-center gap-3 text-xs text-subtle">
                    <span className="truncate">{isMine ? 'You' : 'Community'}</span>
                    {agent.installCount > 0 ? (
                      <span className="flex items-center gap-1 text-warning">
                        <Star className="size-3 fill-current" />
                        {agent.installCount}
                      </span>
                    ) : null}
                  </div>

                  <div className="mt-auto pt-4">
                    {canInstall ? (
                      <Button
                        variant="primary"
                        size="sm"
                        className="w-full"
                        disabled={installing === agent.id}
                        icon={
                          installing === agent.id ? (
                            <Loader2 className="size-3.5 animate-spin" />
                          ) : (
                            <Download className="size-3.5" />
                          )
                        }
                        onClick={() => handleInstall(agent.id)}
                      >
                        Add to workspace
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        size="sm"
                        className="w-full"
                        icon={<Pencil className="size-3.5" />}
                        onClick={() => navigate(`/agent-builder?agent=${agent.id}`)}
                      >
                        Edit
                      </Button>
                    )}
                  </div>
                </div>
              </motion.div>
            )
          })}
        </motion.div>
      )}
    </PageShell>
  )
}

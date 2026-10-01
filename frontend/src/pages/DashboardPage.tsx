import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowRight,
  Bot,
  CalendarClock,
  Coins,
  Plus,
  Sparkles,
  Workflow,
  Zap,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { MiniBars } from '../components/ui/MiniBars'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { fadeUp, stagger } from '../lib/motion'
import { useDemoMode } from '../auth/useDemoMode'
import { agentModelLabel, type AgentList } from '../lib/agents'
import type { WorkflowList } from '../lib/workflows'
import type { Conversation } from '../lib/conversations'
import { formatRelative } from '../lib/knowledgeBases'
import { useApiClient, type ApiClient } from '../lib/api'
import { demoDashboard } from '../lib/demo/dashboard'

type Trend = 'up' | 'down' | 'neutral'

type DashboardKpi = {
  label: string
  value: string
  change?: string
  trend: Trend
  icon: LucideIcon
  iconColor?: string
  spark?: number[]
}

type DashboardView = {
  hero: { title: string; body: string }
  kpis: DashboardKpi[]
  agents: { id: string; name: string; model: string; status: string }[]
  runs: { label: string; value: number }[]
  activity: { action: string; detail: string; time: string }[]
}

const quickActions = [
  { label: 'New agent', to: '/agent-builder', icon: Bot },
  { label: 'New workflow', to: '/workflow-builder', icon: Workflow },
  { label: 'Open chat', to: '/chat', icon: Sparkles },
  { label: 'New schedule', to: '/scheduled-jobs', icon: CalendarClock },
]

// --- real data ---------------------------------------------------------------

type MetricsTotals = {
  traces: number
  tokens: number | null
}
type Metrics = {
  configured: boolean
  totals?: MetricsTotals
  series?: { date: string; count: number }[]
}
type Budget = {
  unlimited: boolean
  budgetCredits: number
  spentCredits: number
  remainingCredits: number | null
}
type KnowledgeUsage = { usage?: { knowledgeBases: number } }

type DashboardRaw = {
  agents: AgentList | null
  workflows: WorkflowList | null
  conversations: { conversations: Conversation[] } | null
  settings: { budget?: Budget } | null
  metrics: Metrics | null
  kbs: KnowledgeUsage | null
}

function safe<T>(promise: Promise<T>): Promise<T | null> {
  return promise.catch(() => null)
}

async function loadDashboard(api: ApiClient): Promise<DashboardRaw> {
  const [agents, workflows, conversations, settings, metrics, kbs] = await Promise.all([
    safe(api.get<AgentList>('/v1/agents')),
    safe(api.get<WorkflowList>('/v1/workflows')),
    safe(api.get<{ conversations: Conversation[] }>('/v1/conversations')),
    safe(api.get<{ budget?: Budget }>('/v1/user/settings')),
    safe(api.get<Metrics>('/v1/lab/metrics?days=30')),
    safe(api.get<KnowledgeUsage>('/v1/knowledge-bases')),
  ])
  return { agents, workflows, conversations, settings, metrics, kbs }
}

function formatCredits(value: number | null | undefined): string {
  if (value === null || value === undefined) return '0'
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

function formatTokens(tokens: number | null | undefined): string {
  if (tokens === null || tokens === undefined) return '—'
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`
  return String(Math.round(tokens))
}

function plural(count: number, noun: string): string {
  return `${count} ${noun}${count === 1 ? '' : 's'}`
}

function realView(raw: DashboardRaw): DashboardView {
  const agents = raw.agents?.agents ?? []
  const workflows = raw.workflows?.workflows ?? []
  const conversations = raw.conversations?.conversations ?? []
  const knowledgeBases = raw.kbs?.usage?.knowledgeBases ?? 0
  const metrics = raw.metrics
  const configured = Boolean(metrics) && metrics?.configured !== false
  const series = (metrics?.series ?? []).slice(-7)
  const budget = raw.settings?.budget

  const activeAgents = agents.filter((agent) => agent.status !== 'draft').length
  const byRecency = [...agents].sort(
    (a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt),
  )
  const swarm = workflows.filter((workflow) => workflow.mode === 'swarm').length
  const graph = workflows.filter((workflow) => workflow.mode === 'graph').length

  const creditValue = budget
    ? budget.unlimited
      ? '∞'
      : `${formatCredits(budget.remainingCredits)} left`
    : '—'
  const creditChange = budget
    ? budget.unlimited
      ? 'No application limit'
      : `${formatCredits(budget.spentCredits)} of ${formatCredits(budget.budgetCredits)} used`
    : 'No budget yet'

  const heroParts = [
    plural(agents.length, 'agent'),
    plural(workflows.length, 'workflow'),
    plural(knowledgeBases, 'knowledge base'),
  ]
  if (conversations.length) heroParts.push(plural(conversations.length, 'conversation'))

  return {
    hero: {
      title: agents.length ? 'Your workspace at a glance' : 'Set up your workspace',
      body: agents.length
        ? `${heroParts.join(' · ')}.`
        : 'Create your first agent, connect a knowledge base, and start asking questions.',
    },
    kpis: [
      {
        label: 'Agents',
        value: String(agents.length),
        change: `${activeAgents} active`,
        trend: 'neutral',
        icon: Bot,
      },
      {
        label: 'Workflows',
        value: String(workflows.length),
        change: workflows.length
          ? `${graph} graph · ${swarm} swarm`
          : 'None yet',
        trend: 'neutral',
        icon: Workflow,
        iconColor: 'text-info',
      },
      {
        label: 'Tokens · 30d',
        value: configured ? formatTokens(metrics?.totals?.tokens) : '—',
        change: configured
          ? `${metrics?.totals?.traces ?? 0} runs`
          : 'Analytics not configured',
        trend: 'neutral',
        icon: Zap,
        iconColor: 'text-warning',
      },
      {
        label: 'AI credits',
        value: creditValue,
        change: creditChange,
        trend: 'neutral',
        icon: Coins,
        iconColor: 'text-success',
      },
    ],
    agents: byRecency.slice(0, 3).map((agent) => ({
      id: agent.id,
      name: agent.name,
      model: agentModelLabel(agent.model),
      status: agent.status === 'draft' ? 'draft' : 'active',
    })),
    runs: series.map((row) => ({
      label: new Date(row.date).toLocaleDateString(undefined, { weekday: 'short' }),
      value: row.count,
    })),
    activity: conversations.slice(0, 6).map((conversation) => ({
      action:
        conversation.targetType === 'workflow' ? 'Workflow run' : 'Agent run',
      detail: `${conversation.agentName} · ${conversation.title}`,
      time: formatRelative(conversation.updatedAt),
    })),
  }
}

function demoView(): DashboardView {
  const d = demoDashboard
  return {
    hero: d.hero,
    kpis: [
      { label: 'Active agents', icon: Bot, ...d.kpis.agents },
      { label: 'Workflows', icon: Workflow, iconColor: 'text-info', ...d.kpis.workflows },
      { label: 'Tokens used', icon: Zap, iconColor: 'text-warning', ...d.kpis.tokens },
      { label: 'AI credits', icon: Coins, iconColor: 'text-success', ...d.kpis.credits },
    ],
    agents: d.agents.map((agent, index) => ({
      id: `demo-${index}`,
      name: agent.name,
      model: agentModelLabel(agent.model),
      status: agent.status,
    })),
    runs: d.runs,
    activity: d.activity,
  }
}

// --- rendering ---------------------------------------------------------------

function DashboardSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <Skeleton className="h-28 w-full rounded-lg" />
      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} className="h-24 w-full rounded-lg" />
        ))}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-3">
        <Skeleton className="h-64 w-full rounded-lg lg:col-span-2" />
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    </PageShell>
  )
}

function PanelHeader({
  title,
  action,
}: {
  title: string
  action?: { label: string; to: string }
}) {
  return (
    <div className="flex items-center justify-between border-b border-border px-4 py-2.5">
      <h2 className="text-[13px] font-semibold text-foreground">{title}</h2>
      {action ? (
        <Link
          to={action.to}
          className="inline-flex items-center gap-1 text-xs font-medium text-muted no-underline transition-colors hover:text-accent"
        >
          {action.label}
          <ArrowRight className="size-3" />
        </Link>
      ) : null}
    </div>
  )
}

function TitleCase({ children }: { children: string }) {
  return <>{children.charAt(0).toUpperCase() + children.slice(1)}</>
}

export function DashboardPage() {
  const demo = useDemoMode()
  const navigate = useNavigate()
  const api = useApiClient()
  const [data, setData] = useState<DashboardView | null>(null)
  const [loading, setLoading] = useState(!demo)

  useEffect(() => {
    if (demo) return
    let cancelled = false
    loadDashboard(api)
      .then((raw) => {
        if (!cancelled) setData(realView(raw))
      })
      .catch(() => {
        if (!cancelled) {
          setData(
            realView({
              agents: null,
              workflows: null,
              conversations: null,
              settings: null,
              metrics: null,
              kbs: null,
            }),
          )
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, demo])

  // Demo has no backend: derive its view from the canned workspace.
  const view = demo ? demoView() : data
  if (!view || loading) return <DashboardSkeleton />

  const { hero, kpis, agents, runs, activity } = view
  const maxRun = Math.max(1, ...runs.map((entry) => entry.value))

  return (
    <PageShell>
      <PageHeader
        title="Dashboard"
        description="Overview of your agents, workflows, usage, and recent activity."
        action={{
          label: 'Create agent',
          icon: <Plus className="size-3.5" />,
          onClick: () => navigate('/agent-builder'),
        }}
      />

      <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
        <motion.div variants={fadeUp}>
          <div className="relative overflow-hidden rounded-lg border border-border bg-surface p-5">
            <div
              className="pointer-events-none absolute -top-24 -right-16 size-64 rounded-full bg-accent/10 blur-3xl"
              aria-hidden="true"
            />
            <div className="relative">
              <div className="flex items-center gap-2">
                <Sparkles className="size-4 text-accent" />
                <span className="text-xs font-medium text-accent">Workspace overview</span>
              </div>
              <h2 className="mt-2 text-base font-semibold tracking-tight text-foreground">
                {hero.title}
              </h2>
              <p className="mt-1 max-w-xl text-[13px] text-muted">{hero.body}</p>
            </div>
          </div>
        </motion.div>

        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {kpis.map((kpi) => (
            <motion.div key={kpi.label} variants={fadeUp}>
              <StatCard {...kpi} />
            </motion.div>
          ))}
        </div>

        <div className="grid gap-3 lg:grid-cols-3">
          <motion.div variants={fadeUp} className="lg:col-span-2">
            {agents.length > 0 ? (
              <div className="grid h-full gap-3 sm:grid-cols-3">
                {agents.map((agent) => (
                  <Link
                    key={agent.id}
                    to="/agent-store"
                    className="group flex flex-col rounded-lg border border-border bg-surface p-4 no-underline transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/30"
                  >
                    <div className="flex items-start justify-between">
                      <span className="flex size-9 items-center justify-center rounded-md border border-border bg-raised text-accent">
                        <Bot className="size-4" strokeWidth={1.75} />
                      </span>
                      <Badge
                        variant={agent.status === 'active' ? 'success' : 'default'}
                        dot={agent.status === 'active'}
                      >
                        <TitleCase>{agent.status}</TitleCase>
                      </Badge>
                    </div>
                    <p className="mt-3 truncate text-[13px] font-semibold text-foreground">
                      {agent.name}
                    </p>
                    <p className="mt-0.5 truncate text-xs text-muted">{agent.model}</p>
                  </Link>
                ))}
              </div>
            ) : (
              <Card padding="none" className="flex h-full flex-col items-center justify-center gap-3 p-8 text-center">
                <span className="flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
                  <Bot className="size-5" strokeWidth={1.8} />
                </span>
                <div>
                  <p className="text-[13px] font-semibold text-foreground">No agents yet</p>
                  <p className="mt-0.5 text-xs text-muted">
                    Build your first agent to see it here.
                  </p>
                </div>
                <Link
                  to="/agent-builder"
                  className="inline-flex items-center gap-1.5 rounded-md border border-border bg-raised px-3 py-1.5 text-[12px] font-medium text-foreground no-underline transition-colors hover:border-accent/40"
                >
                  <Plus className="size-3.5" />
                  Create agent
                </Link>
              </Card>
            )}
          </motion.div>

          <motion.div variants={fadeUp}>
            <Card padding="none" className="h-full overflow-hidden">
              <PanelHeader title="Quick actions" />
              <div className="divide-y divide-border">
                {quickActions.map(({ label, to, icon: Icon }) => (
                  <Link
                    key={to}
                    to={to}
                    className="flex items-center gap-3 px-4 py-2.5 text-[13px] font-medium text-foreground no-underline transition-colors hover:bg-raised/40"
                  >
                    <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-muted">
                      <Icon className="size-3.5" strokeWidth={1.75} />
                    </span>
                    {label}
                    <ArrowRight className="ml-auto size-3.5 text-subtle" />
                  </Link>
                ))}
              </div>
            </Card>
          </motion.div>
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <motion.div variants={fadeUp}>
            <Card padding="none" className="h-full overflow-hidden">
              <PanelHeader title="Runs · last 7 days" />
              {runs.length > 0 ? (
                <div className="p-4">
                  <MiniBars
                    data={runs}
                    max={maxRun}
                    tone="bg-gradient-to-t from-info/50 to-info"
                  />
                </div>
              ) : (
                <p className="px-4 py-10 text-center text-[12.5px] text-muted">
                  No runs in the last 7 days.
                </p>
              )}
            </Card>
          </motion.div>

          <motion.div variants={fadeUp}>
            <Card padding="none" className="h-full overflow-hidden">
              <PanelHeader title="Recent activity" action={{ label: 'Chat', to: '/chat' }} />
              {activity.length > 0 ? (
                <div className="divide-y divide-border">
                  {activity.map((item, index) => (
                    <div
                      key={`${item.detail}-${index}`}
                      className="flex items-center gap-3 px-4 py-2.5"
                    >
                      <span className="size-1.5 shrink-0 rounded-full bg-accent" aria-hidden="true" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-[13px] font-medium text-foreground">
                          {item.action}
                        </p>
                        <p className="truncate text-xs text-muted">{item.detail}</p>
                      </div>
                      <span className="shrink-0 text-[11px] text-subtle">{item.time}</span>
                    </div>
                  ))}
                </div>
              ) : (
                <p className="px-4 py-10 text-center text-[12.5px] text-muted">
                  No conversations yet.
                </p>
              )}
            </Card>
          </motion.div>
        </div>
      </motion.div>
    </PageShell>
  )
}

import { motion } from 'framer-motion'
import { Link, useNavigate } from 'react-router-dom'
import {
  Activity,
  Bot,
  Coins,
  Database,
  FileStack,
  Gauge,
  HardDrive,
  KeyRound,
  Plug,
  Sparkles,
  Workflow,
  Zap,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Progress } from '../components/ui/progress'
import { Skeleton } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { useApiClient, type ApiClient } from '../lib/api'
import { usePageQuery } from '../hooks/usePageQuery'
import { fadeUp, stagger } from '../lib/motion'
import { formatRelative } from '../lib/knowledgeBases'
import { formatBytes } from '../lib/storage'
import { providerLabel, type VaultProvider, type VaultSecret } from '../lib/vault'

const MCP_LIMIT = 20

type UsageMetrics = {
  configured: boolean
  error?: string
  days?: number
  totals?: {
    traces: number
    avgLatency: number
    p95Latency: number
    cost: number
    tokens: number | null
  }
  series?: { date: string; count: number; p95Latency: number; cost: number }[]
  models?: { model: string; count: number; cost: number; tokens: number }[]
}

type VaultList = {
  secrets: VaultSecret[]
  usage: { secretCount: number; limit: number; providerCount: number; uses: number }
}

type StorageUsage = {
  fileCount: number
  storageBytes: number
  limits: { maxFiles: number; maxFileBytes: number; maxStorageBytes: number }
}

type BudgetInfo = {
  budgetUsd: number
  spentUsd: number
  remainingUsd: number | null
  unlimited: boolean
  creditsPerUsd: number
  budgetCredits: number
  spentCredits: number
  remainingCredits: number | null
}

function formatCredits(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1)
}

type SettingsUsage = {
  budget?: BudgetInfo
  pricing?: Record<string, { input: number; output: number }>
}

type UsageOverview = {
  metrics: UsageMetrics | null
  vault: VaultList | null
  providers: { providers: VaultProvider[] } | null
  settings: SettingsUsage | null
  storage: { usage: StorageUsage } | null
  kbs: {
    usage: {
      knowledgeBases: number
      files: number
      storageBytes: number
      limits: { knowledgeBases: number; files: number; storageBytes: number }
    }
  } | null
  agents: { usage?: { agents: number; limits: { agents: number } } } | null
  workflows: { usage?: { workflows: number; limits: { workflows: number } } } | null
  skills: { usage?: { skills: number; limits: { skills: number } } } | null
  mcp: { connections: unknown[] } | null
}

function safe<T>(promise: Promise<T>): Promise<T | null> {
  return promise.catch(() => null)
}

async function loadOverview(api: ApiClient): Promise<UsageOverview> {
  const [metrics, vault, providers, settings, storage, kbs, agents, workflows, skills, mcp] =
    await Promise.all([
      safe(api.get<UsageMetrics>('/v1/lab/metrics?days=30')),
      safe(api.get<VaultList>('/v1/vault/secrets')),
      safe(api.get<{ providers: VaultProvider[] }>('/v1/vault/providers')),
      safe(api.get<SettingsUsage>('/v1/user/settings')),
      safe(api.get<{ usage: StorageUsage }>('/v1/storage/files')),
      safe(api.get<UsageOverview['kbs']>('/v1/knowledge-bases')),
      safe(api.get<UsageOverview['agents']>('/v1/agents')),
      safe(api.get<UsageOverview['workflows']>('/v1/workflows')),
      safe(api.get<UsageOverview['skills']>('/v1/agent-skills')),
      safe(api.get<{ connections: unknown[] }>('/v1/mcp/connections')),
    ])
  return { metrics, vault, providers, settings, storage, kbs, agents, workflows, skills, mcp }
}

// --- formatting --------------------------------------------------------------

function formatLatency(ms: number | undefined): string {
  if (!ms) return '—'
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`
}

function formatCost(cost: number | null | undefined): string {
  if (!cost) return '$0.00'
  return cost >= 1 ? `$${cost.toFixed(2)}` : `$${cost.toFixed(4)}`
}

function formatTokens(tokens: number | null | undefined): string {
  if (tokens === null || tokens === undefined) return '—'
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`
  return String(Math.round(tokens))
}

function delta(values: number[]): { change?: string; trend: 'up' | 'down' | 'neutral' } {
  if (values.length < 2 || values[0] === 0) return { trend: 'neutral' }
  const pct = ((values[values.length - 1] - values[0]) / values[0]) * 100
  return {
    change: `${pct >= 0 ? '+' : ''}${pct.toFixed(0)}% vs window start`,
    trend: pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral',
  }
}

function pct(used: number, limit: number): number {
  if (!limit) return 0
  return Math.min(100, Math.round((used / limit) * 100))
}

// --- small building blocks ---------------------------------------------------

function ResourceRow({
  icon,
  label,
  value,
  used,
  limit,
}: {
  icon: React.ReactNode
  label: string
  value: string
  used: number
  limit: number
}) {
  const percent = pct(used, limit)
  const near = percent >= 80
  return (
    <div className="flex items-center gap-3 px-4 py-3">
      <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
        {icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <p className="text-[13px] font-medium text-foreground">{label}</p>
          <p className="text-xs tabular-nums text-muted">{value}</p>
        </div>
        <Progress
          value={percent}
          className={`mt-1.5 ${near ? '[&>[data-slot=progress-indicator]]:bg-warning' : ''}`}
        />
      </div>
    </div>
  )
}

function UsageSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-6 w-28" />
        <Skeleton className="h-4 w-96 max-w-full" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-24 w-full" />
        ))}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Skeleton className="h-56 w-full" />
        <Skeleton className="h-56 w-full" />
      </div>
    </PageShell>
  )
}

export function UsagePage() {
  const api = useApiClient()
  const navigate = useNavigate()
  const { data, isPending, error, refetch } = usePageQuery<UsageOverview>(
    'usage-overview',
    () => loadOverview(api),
    { refetchOnMount: true },
  )

  if (isPending) return <UsageSkeleton />

  if (error) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState title="Couldn't load usage" error={error} onRetry={() => refetch()} />
        </div>
      </PageShell>
    )
  }

  const metrics = data?.metrics ?? null
  const configured = metrics?.configured !== false
  const totals = metrics?.totals
  const series = metrics?.series ?? []
  const models = metrics?.models ?? []
  const secrets = data?.vault?.secrets ?? []
  const providers = data?.providers?.providers ?? []
  const budget = data?.settings?.budget ?? null
  const pricing = data?.settings?.pricing ?? null

  const counts = series.map((row) => row.count)
  const latencies = series.map((row) => row.p95Latency)
  const costs = series.map((row) => row.cost)
  const maxModelCost = Math.max(0.000001, ...models.map((model) => model.cost))

  const vaultUsage = data?.vault?.usage
  const storageUsage = data?.storage?.usage
  const kbUsage = data?.kbs?.usage

  const resources: {
    key: string
    icon: React.ReactNode
    label: string
    value: string
    used: number
    limit: number
  }[] = []
  if (kbUsage) {
    resources.push({
      key: 'kbs',
      icon: <FileStack className="size-3.5" strokeWidth={1.75} />,
      label: 'Knowledge bases',
      value: `${kbUsage.knowledgeBases} / ${kbUsage.limits.knowledgeBases}`,
      used: kbUsage.knowledgeBases,
      limit: kbUsage.limits.knowledgeBases,
    })
  }
  if (storageUsage) {
    resources.push({
      key: 'storage',
      icon: <HardDrive className="size-3.5" strokeWidth={1.75} />,
      label: 'Storage',
      value: `${formatBytes(storageUsage.storageBytes)} / ${formatBytes(storageUsage.limits.maxStorageBytes)}`,
      used: storageUsage.storageBytes,
      limit: storageUsage.limits.maxStorageBytes,
    })
    resources.push({
      key: 'files',
      icon: <FileStack className="size-3.5" strokeWidth={1.75} />,
      label: 'Stored files',
      value: `${storageUsage.fileCount} / ${storageUsage.limits.maxFiles}`,
      used: storageUsage.fileCount,
      limit: storageUsage.limits.maxFiles,
    })
  }
  if (data?.agents?.usage) {
    resources.push({
      key: 'agents',
      icon: <Bot className="size-3.5" strokeWidth={1.75} />,
      label: 'Agents',
      value: `${data.agents.usage.agents} / ${data.agents.usage.limits.agents}`,
      used: data.agents.usage.agents,
      limit: data.agents.usage.limits.agents,
    })
  }
  if (data?.workflows?.usage) {
    resources.push({
      key: 'workflows',
      icon: <Workflow className="size-3.5" strokeWidth={1.75} />,
      label: 'Workflows',
      value: `${data.workflows.usage.workflows} / ${data.workflows.usage.limits.workflows}`,
      used: data.workflows.usage.workflows,
      limit: data.workflows.usage.limits.workflows,
    })
  }
  if (data?.skills?.usage) {
    resources.push({
      key: 'skills',
      icon: <Sparkles className="size-3.5" strokeWidth={1.75} />,
      label: 'Skills',
      value: `${data.skills.usage.skills} / ${data.skills.usage.limits.skills}`,
      used: data.skills.usage.skills,
      limit: data.skills.usage.limits.skills,
    })
  }
  if (data?.mcp) {
    resources.push({
      key: 'mcp',
      icon: <Plug className="size-3.5" strokeWidth={1.75} />,
      label: 'MCP connections',
      value: `${data.mcp.connections.length} / ${MCP_LIMIT}`,
      used: data.mcp.connections.length,
      limit: MCP_LIMIT,
    })
  }
  if (vaultUsage) {
    resources.push({
      key: 'vault',
      icon: <KeyRound className="size-3.5" strokeWidth={1.75} />,
      label: 'Vault secrets',
      value: `${vaultUsage.secretCount} / ${vaultUsage.limit}`,
      used: vaultUsage.secretCount,
      limit: vaultUsage.limit,
    })
  }

  return (
    <PageShell>
      <PageHeader
        title="Usage"
        description="Live usage across your workspace — token and cost analytics, provider keys, and resource limits."
      />

      <Tabs defaultValue="overview">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="resources">Resources</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
            {budget ? (
              <motion.div variants={fadeUp}>
                <Card padding="none" className="overflow-hidden">
                  <div className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="flex items-center gap-3">
                      <span className="flex size-9 items-center justify-center rounded-md border border-border bg-raised text-warning">
                        <Coins className="size-4" strokeWidth={1.75} />
                      </span>
                      <div>
                        <p className="text-[13px] font-medium text-foreground">
                          {budget.unlimited
                            ? 'AI credits — unlimited'
                            : `AI credits — ${formatCredits(budget.spentCredits)} of ${formatCredits(budget.budgetCredits)} used`}
                        </p>
                        <p className="text-[11px] text-subtle">
                          {budget.unlimited
                            ? 'No application limit.'
                            : budget.remainingCredits != null && budget.remainingCredits > 0
                              ? `${formatCredits(budget.remainingCredits)} credits left for platform models (≈ $${budget.remainingUsd?.toFixed(2)}). Your own Vault keys are not counted.`
                              : 'Credits used up — add your own API key in the Vault to keep running, or ask an admin for more credits.'}
                        </p>
                      </div>
                    </div>
                    {!budget.unlimited ? (
                      <span className="shrink-0 text-xs tabular-nums text-muted">
                        {pct(budget.spentCredits, budget.budgetCredits)}%
                      </span>
                    ) : null}
                  </div>
                  {!budget.unlimited ? (
                    <Progress
                      value={pct(budget.spentCredits, budget.budgetCredits)}
                      className="mx-4 mb-3"
                    />
                  ) : null}
                </Card>
              </motion.div>
            ) : null}
            {!configured || metrics?.error ? (
              <Card className="px-4 py-3 text-[13px] text-muted">
                {!configured
                  ? 'Token and cost analytics need Langfuse. Add LANGFUSE_* keys to see live model usage.'
                  : `Could not load analytics: ${metrics?.error}`}
              </Card>
            ) : (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                <motion.div variants={fadeUp}>
                  <StatCard
                    label="Runs (30d)"
                    value={String(Math.round(totals?.traces ?? 0))}
                    icon={Gauge}
                    iconColor="text-accent"
                    spark={counts}
                    {...delta(counts)}
                  />
                </motion.div>
                <motion.div variants={fadeUp}>
                  <StatCard
                    label="Tokens (30d)"
                    value={formatTokens(totals?.tokens)}
                    icon={Zap}
                    iconColor="text-success"
                  />
                </motion.div>
                <motion.div variants={fadeUp}>
                  <StatCard
                    label="Cost (30d)"
                    value={formatCost(totals?.cost)}
                    icon={Coins}
                    iconColor="text-warning"
                    spark={costs}
                    {...delta(costs)}
                  />
                </motion.div>
                <motion.div variants={fadeUp}>
                  <StatCard
                    label="p95 latency"
                    value={formatLatency(totals?.p95Latency)}
                    icon={Activity}
                    iconColor="text-info"
                    spark={latencies}
                    {...delta(latencies)}
                  />
                </motion.div>
              </div>
            )}

            <div className="grid gap-3 lg:grid-cols-2">
              <motion.div variants={fadeUp}>
                <Card padding="none" className="h-full overflow-hidden">
                  <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <KeyRound className="size-3.5 text-accent" strokeWidth={1.75} />
                      <h2 className="text-[13px] font-semibold text-foreground">Provider keys</h2>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => navigate('/vault')}>
                      Manage
                    </Button>
                  </div>
                  {!data?.vault ? (
                    <p className="px-4 py-8 text-center text-[13px] text-subtle">
                      Vault unavailable.
                    </p>
                  ) : secrets.length === 0 ? (
                    <div className="px-4 py-8 text-center">
                      <p className="text-[13px] text-muted">No keys stored yet.</p>
                      <p className="mt-1 text-xs text-subtle">
                        Add provider keys in the{' '}
                        <Link to="/vault" className="text-accent hover:underline">
                          Vault
                        </Link>{' '}
                        to use them across agents and tools.
                      </p>
                    </div>
                  ) : (
                    <div className="divide-y divide-border">
                      {secrets.slice(0, 6).map((secret) => (
                        <div key={secret.id} className="flex items-center gap-3 px-4 py-3">
                          <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
                            <KeyRound className="size-3.5" strokeWidth={1.75} />
                          </span>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-[13px] font-medium text-foreground">
                              {secret.label}
                              {secret.kind === 'provider' ? (
                                <span className="ml-2 text-[11px] font-normal text-muted">
                                  {providerLabel(providers, secret.provider)}
                                </span>
                              ) : null}
                            </p>
                            <p className="mt-0.5 truncate text-[11px] text-subtle">
                              <span className="font-mono">{secret.preview}</span>
                              {secret.defaultModel ? ` · ${secret.defaultModel}` : ''}
                              {secret.usage.lastUsedAt
                                ? ` · used ${formatRelative(secret.usage.lastUsedAt)}`
                                : ''}
                            </p>
                          </div>
                          {secret.test.status ? (
                            <Badge variant={secret.test.status === 'ok' ? 'success' : 'warning'} dot>
                              {secret.test.status === 'ok' ? 'Verified' : 'Failed'}
                            </Badge>
                          ) : null}
                          <span className="shrink-0 text-[11px] tabular-nums text-subtle">
                            {secret.usage.runs > 0
                              ? `${secret.usage.runs} run${secret.usage.runs === 1 ? '' : 's'}${
                                  secret.usage.tokensTotal
                                    ? ` · ${formatTokens(secret.usage.tokensTotal)} tok`
                                    : ''
                                }`
                              : `${secret.usage.count} use${secret.usage.count === 1 ? '' : 's'}`}
                          </span>
                        </div>
                      ))}
                      {secrets.length > 6 ? (
                        <button
                          type="button"
                          className="block w-full px-4 py-2.5 text-left text-xs text-accent hover:bg-raised/40"
                          onClick={() => navigate('/vault')}
                        >
                          View all {secrets.length} keys in the Vault →
                        </button>
                      ) : null}
                    </div>
                  )}
                </Card>
              </motion.div>

              <motion.div variants={fadeUp}>
                <Card padding="none" className="h-full overflow-hidden">
                  <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
                    <Database className="size-3.5 text-info" strokeWidth={1.75} />
                    <h2 className="text-[13px] font-semibold text-foreground">
                      Usage by model · last 30 days
                    </h2>
                  </div>
                  {models.length === 0 ? (
                    <p className="px-4 py-8 text-center text-[13px] text-subtle">
                      {configured
                        ? 'No model usage recorded yet.'
                        : 'Model usage appears once Langfuse is configured.'}
                    </p>
                  ) : (
                    <div className="space-y-4 p-4">
                      {models.map((model) => (
                        <div key={model.model}>
                          <div className="mb-1.5 flex items-center justify-between gap-3 text-xs">
                            <span className="truncate font-medium text-foreground">
                              {model.model}
                            </span>
                            <span className="shrink-0 text-muted">
                              {formatCost(model.cost)}
                              {model.tokens ? ` · ${formatTokens(model.tokens)} tok` : ''}
                            </span>
                          </div>
                          <Progress value={pct(model.cost, maxModelCost)} />
                        </div>
                      ))}
                    </div>
                  )}
                </Card>
              </motion.div>
            </div>
          </motion.div>
        </TabsContent>

        <TabsContent value="resources">
          {resources.length === 0 ? (
            <Card className="px-4 py-8 text-center text-[13px] text-subtle">
              No resource data available.
            </Card>
          ) : (
            <Card padding="none" className="overflow-hidden">
              <div className="divide-y divide-border">
                {resources.map((resource) => (
                  <ResourceRow
                    key={resource.key}
                    icon={resource.icon}
                    label={resource.label}
                    value={resource.value}
                    used={resource.used}
                    limit={resource.limit}
                  />
                ))}
              </div>
            </Card>
          )}
          <p className="mt-3 text-xs text-subtle">
            Limits are per user. Last vault activity:{' '}
            {vaultUsage?.secretCount
              ? `${vaultUsage.secretCount} secret(s), ${vaultUsage.uses} resolution(s)`
              : 'none yet'}
            .
          </p>

          {pricing ? (
            <Card padding="none" className="mt-3 overflow-hidden">
              <div className="border-b border-border px-4 py-2.5">
                <h2 className="text-[13px] font-semibold text-foreground">
                  Model rates · USD per 1M tokens
                </h2>
                <p className="mt-0.5 text-xs text-muted">
                  Input / output rates used to price platform-model usage against your budget.
                </p>
              </div>
              <div className="divide-y divide-border">
                {Object.entries(pricing)
                  .filter(([model]) => model !== '__default__')
                  .map(([model, rate]) => (
                    <div
                      key={model}
                      className="flex items-center justify-between gap-3 px-4 py-2.5"
                    >
                      <span className="truncate font-mono text-[12px] text-foreground">
                        {model}
                      </span>
                      <span className="shrink-0 text-xs tabular-nums text-muted">
                        ${rate.input.toFixed(2)} · ${rate.output.toFixed(2)}
                      </span>
                    </div>
                  ))}
              </div>
            </Card>
          ) : null}
        </TabsContent>
      </Tabs>
    </PageShell>
  )
}

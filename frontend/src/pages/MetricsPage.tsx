import { motion } from 'framer-motion'
import { Activity, Coins, Gauge, Zap } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { MiniBars } from '../components/ui/MiniBars'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { StatCard } from '../components/ui/StatCard'
import { useApiClient } from '../lib/api'
import { usePageQuery } from '../hooks/usePageQuery'
import { fadeUp, stagger } from '../lib/motion'

type MetricsResponse = {
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
  scores?: { name: string; avg: number; count: number }[]
}

function formatLatency(ms: number | undefined): string {
  if (!ms) return '—'
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(2)} s`
}

function formatCost(cost: number | undefined): string {
  if (!cost) return '$0.00'
  return cost >= 1 ? `$${cost.toFixed(2)}` : `$${cost.toFixed(4)}`
}

function formatTokens(tokens: number | null | undefined): string {
  if (tokens === null || tokens === undefined) return '—'
  if (tokens >= 1_000_000) return `${(tokens / 1_000_000).toFixed(1)}M`
  if (tokens >= 1000) return `${(tokens / 1000).toFixed(1)}k`
  return String(Math.round(tokens))
}

function dayLabel(iso: string): string {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return `${date.getMonth() + 1}/${date.getDate()}`
}

function delta(values: number[]): { change?: string; trend: 'up' | 'down' | 'neutral' } {
  if (values.length < 2 || values[0] === 0) return { trend: 'neutral' }
  const pct = ((values[values.length - 1] - values[0]) / values[0]) * 100
  return {
    change: `${pct >= 0 ? '+' : ''}${pct.toFixed(0)}% vs window start`,
    trend: pct > 0 ? 'up' : pct < 0 ? 'down' : 'neutral',
  }
}

export function MetricsPage() {
  const api = useApiClient()
  const { data, isPending } = usePageQuery<MetricsResponse>('lab-metrics', () =>
    api.get<MetricsResponse>('/v1/lab/metrics?days=7'),
  )

  if (isPending) return <MetricsSkeleton />

  const configured = data?.configured !== false
  const totals = data?.totals
  const series = data?.series ?? []
  const scores = data?.scores ?? []
  const counts = series.map((row) => row.count)
  const latencies = series.map((row) => row.p95Latency)
  const costs = series.map((row) => row.cost)
  const maxCount = Math.max(1, ...counts)
  const maxLatency = Math.max(1, ...latencies)

  return (
    <PageShell>
      <PageHeader
        title="Metrics"
        description="Your traces, latency, cost, tokens and scores from the last 7 days."
        badge="Evaluate"
        badgeVariant="info"
      />

      {!configured || data?.error ? (
        <Card className="p-8 text-center text-[13px] text-muted">
          {!configured
            ? 'Langfuse isn’t configured for this environment yet.'
            : `Could not load metrics: ${data?.error}`}
        </Card>
      ) : (
        <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <motion.div variants={fadeUp}>
              <StatCard
                label="Runs (traces)"
                value={String(Math.round(totals?.traces ?? 0))}
                icon={Gauge}
                iconColor="text-accent"
                spark={counts}
                {...delta(counts)}
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
            <motion.div variants={fadeUp}>
              <StatCard
                label="Cost (7d)"
                value={formatCost(totals?.cost)}
                icon={Coins}
                iconColor="text-warning"
                spark={costs}
                {...delta(costs)}
              />
            </motion.div>
            <motion.div variants={fadeUp}>
              <StatCard
                label="Tokens"
                value={formatTokens(totals?.tokens)}
                icon={Zap}
                iconColor="text-success"
              />
            </motion.div>
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <motion.div variants={fadeUp}>
              <Card padding="none" className="h-full overflow-hidden">
                <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
                  <Gauge className="size-3.5 text-accent" strokeWidth={1.75} />
                  <h2 className="text-[13px] font-semibold text-foreground">
                    Daily volume · last 7 days
                  </h2>
                </div>
                <div className="p-4">
                  {series.length === 0 ? (
                    <p className="py-8 text-center text-[13px] text-subtle">No data yet.</p>
                  ) : (
                    <MiniBars
                      data={series.map((row) => ({ label: dayLabel(row.date), value: row.count }))}
                      max={maxCount}
                      tone="bg-gradient-to-t from-accent/50 to-accent"
                    />
                  )}
                </div>
              </Card>
            </motion.div>

            <motion.div variants={fadeUp}>
              <Card padding="none" className="h-full overflow-hidden">
                <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
                  <Activity className="size-3.5 text-info" strokeWidth={1.75} />
                  <h2 className="text-[13px] font-semibold text-foreground">
                    Daily p95 latency · last 7 days
                  </h2>
                </div>
                <div className="p-4">
                  {series.length === 0 ? (
                    <p className="py-8 text-center text-[13px] text-subtle">No data yet.</p>
                  ) : (
                    <MiniBars
                      data={series.map((row) => ({
                        label: dayLabel(row.date),
                        value: row.p95Latency,
                      }))}
                      max={maxLatency}
                      tone="bg-gradient-to-t from-info/50 to-info"
                    />
                  )}
                </div>
              </Card>
            </motion.div>
          </div>

          <motion.div variants={fadeUp}>
            <Card padding="none" className="overflow-hidden">
              <div className="border-b border-border px-4 py-2.5">
                <h2 className="text-[13px] font-semibold text-foreground">
                  Scores · last 7 days
                </h2>
              </div>
              {scores.length === 0 ? (
                <p className="px-4 py-8 text-center text-[13px] text-subtle">
                  No numeric scores yet. Add run feedback or run an evaluation.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[520px] text-left">
                    <thead>
                      <tr className="border-b border-border bg-raised/40">
                        {['Score', 'Average', 'Count'].map((header) => (
                          <th
                            key={header}
                            className="px-4 py-2.5 text-[11px] font-semibold text-muted"
                          >
                            {header}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {scores.map((score) => (
                        <tr key={score.name} className="transition-colors hover:bg-raised/40">
                          <td className="px-4 py-2.5 font-mono text-[12.5px] text-foreground">
                            {score.name}
                          </td>
                          <td className="px-4 py-2.5">
                            <Badge variant={score.avg >= 0.6 ? 'success' : 'warning'}>
                              {score.avg.toFixed(3)}
                            </Badge>
                          </td>
                          <td className="px-4 py-2.5 text-xs tabular-nums text-muted">
                            {Math.round(score.count)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </motion.div>
        </motion.div>
      )}
    </PageShell>
  )
}

function MetricsSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-6 w-28" />
        <Skeleton className="h-4 w-80" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, index) => (
          <Skeleton key={index} className="h-24 w-full" />
        ))}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-2">
        <Skeleton className="h-44 w-full" />
        <Skeleton className="h-44 w-full" />
      </div>
    </PageShell>
  )
}

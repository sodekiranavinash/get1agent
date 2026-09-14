import { motion } from 'framer-motion'
import { Activity, AlertTriangle, Coins, Gauge, Zap } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { MiniBars } from '../components/ui/MiniBars'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { StatCard } from '../components/ui/StatCard'
import { fadeUp, stagger } from '../lib/motion'

const kpis = [
  {
    label: 'p95 latency',
    value: '1.8s',
    change: '-120ms vs last week',
    trend: 'down' as const,
    icon: Activity,
    iconColor: 'text-info',
    spark: [2.4, 2.3, 2.2, 2.1, 2.0, 1.9, 1.8],
  },
  {
    label: 'Error rate',
    value: '0.7%',
    change: '-0.2% vs last week',
    trend: 'down' as const,
    icon: AlertTriangle,
    iconColor: 'text-warning',
    spark: [1.4, 1.2, 1.1, 1.0, 0.9, 0.8, 0.7],
  },
  {
    label: 'Throughput',
    value: '42 rps',
    change: '+8% vs last week',
    trend: 'up' as const,
    icon: Zap,
    iconColor: 'text-accent',
    spark: [30, 32, 34, 36, 38, 40, 42],
  },
  {
    label: 'Cost / 1k tokens',
    value: '$0.012',
    change: '-4% vs last week',
    trend: 'down' as const,
    icon: Coins,
    iconColor: 'text-success',
    spark: [0.016, 0.015, 0.014, 0.014, 0.013, 0.0125, 0.012],
  },
]

const latency = [
  { label: '00', value: 18 },
  { label: '04', value: 22 },
  { label: '08', value: 26 },
  { label: '12', value: 24 },
  { label: '16', value: 30 },
  { label: '20', value: 27 },
  { label: '24', value: 20 },
]

const throughput = [
  { label: 'Mon', value: 34 },
  { label: 'Tue', value: 38 },
  { label: 'Wed', value: 36 },
  { label: 'Thu', value: 41 },
  { label: 'Fri', value: 44 },
  { label: 'Sat', value: 30 },
  { label: 'Sun', value: 28 },
]

const models = [
  { model: 'Claude Sonnet 4', p50: '1.1s', p95: '2.4s', errors: '0.4%', cost: '$0.018' },
  { model: 'GPT-4o', p50: '0.9s', p95: '1.9s', errors: '0.6%', cost: '$0.014' },
  { model: 'Gemini 2.0 Pro', p50: '1.3s', p95: '2.8s', errors: '1.1%', cost: '$0.010' },
]

export function MetricsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Metrics"
        description="Operational telemetry across models, tools and knowledge retrieval."
        badge="Evaluate"
      />

      <motion.div variants={stagger} initial="hidden" animate="show" className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {kpis.map((kpi) => (
            <motion.div key={kpi.label} variants={fadeUp}>
              <StatCard {...kpi} />
            </motion.div>
          ))}
        </div>

        <div className="grid gap-3 lg:grid-cols-2">
          <motion.div variants={fadeUp}>
            <Card padding="none" className="h-full overflow-hidden">
              <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
                <Activity className="size-3.5 text-info" strokeWidth={1.75} />
                <h2 className="text-[13px] font-semibold text-foreground">
                  Request latency · today
                </h2>
              </div>
              <div className="p-4">
                <MiniBars
                  data={latency}
                  max={32}
                  tone="bg-gradient-to-t from-info/50 to-info"
                />
              </div>
            </Card>
          </motion.div>

          <motion.div variants={fadeUp}>
            <Card padding="none" className="h-full overflow-hidden">
              <div className="flex items-center gap-2 border-b border-border px-4 py-2.5">
                <Gauge className="size-3.5 text-accent" strokeWidth={1.75} />
                <h2 className="text-[13px] font-semibold text-foreground">
                  Throughput · last 7 days
                </h2>
              </div>
              <div className="p-4">
                <MiniBars
                  data={throughput}
                  max={48}
                  tone="bg-gradient-to-t from-accent/50 to-accent"
                />
              </div>
            </Card>
          </motion.div>
        </div>

        <motion.div variants={fadeUp}>
          <Card padding="none" className="overflow-hidden">
            <div className="border-b border-border px-4 py-2.5">
              <h2 className="text-[13px] font-semibold text-foreground">By model</h2>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[640px] text-left">
                <thead>
                  <tr className="border-b border-border bg-raised/40">
                    {['Model', 'p50', 'p95', 'Error rate', 'Cost / 1k'].map((header) => (
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
                  {models.map((row) => (
                    <tr key={row.model} className="transition-colors hover:bg-raised/40">
                      <td className="px-4 py-2.5 text-[13px] font-medium text-foreground">
                        {row.model}
                      </td>
                      <td className="px-4 py-2.5 text-xs tabular-nums text-muted">
                        {row.p50}
                      </td>
                      <td className="px-4 py-2.5 text-xs tabular-nums text-muted">
                        {row.p95}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge
                          variant={row.errors.startsWith('1') ? 'warning' : 'success'}
                        >
                          {row.errors}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 text-xs tabular-nums text-muted">
                        {row.cost}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </motion.div>
      </motion.div>
    </PageShell>
  )
}

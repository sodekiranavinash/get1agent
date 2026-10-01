import { motion } from 'framer-motion'
import { Bot, TrendingUp, Workflow, Zap } from 'lucide-react'
import { Card } from '../components/ui/Card'
import { MiniBars } from '../components/ui/MiniBars'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { StatCard } from '../components/ui/StatCard'
import { fadeUp, stagger } from '../lib/motion'
import { useDemoMode } from '../auth/useDemoMode'
import { demoDashboard } from '../lib/demo/dashboard'

const staticWeeklyTokens = [
  { label: 'Mon', value: 62 },
  { label: 'Tue', value: 74 },
  { label: 'Wed', value: 68 },
  { label: 'Thu', value: 91 },
  { label: 'Fri', value: 84 },
  { label: 'Sat', value: 96 },
  { label: 'Sun', value: 88 },
]

const staticWorkflowRuns = [
  { label: 'Mon', value: 12 },
  { label: 'Tue', value: 18 },
  { label: 'Wed', value: 15 },
  { label: 'Thu', value: 22 },
  { label: 'Fri', value: 19 },
  { label: 'Sat', value: 24 },
  { label: 'Sun', value: 21 },
]

const staticKpis = [
  {
    label: 'Avg. daily tokens',
    value: '118K',
    change: '+9% vs last week',
    trend: 'up' as const,
    icon: Zap,
    iconColor: 'text-warning',
    spark: [80, 92, 88, 104, 100, 118, 112],
  },
  {
    label: 'Workflow success rate',
    value: '94%',
    change: '+2% vs last week',
    trend: 'up' as const,
    icon: Workflow,
    iconColor: 'text-info',
    spark: [88, 89, 90, 91, 92, 93, 94],
  },
  {
    label: 'Active agents',
    value: '12',
    change: '3 ran today',
    trend: 'neutral' as const,
    icon: Bot,
    spark: [6, 7, 8, 9, 10, 11, 12],
  },
  {
    label: 'Cost trend',
    value: '$4.20/day',
    change: '-6% vs last week',
    trend: 'down' as const,
    icon: TrendingUp,
    iconColor: 'text-success',
    spark: [5.2, 5.0, 4.9, 4.6, 4.5, 4.3, 4.2],
  },
]

export function InsightsPage() {
  const demo = useDemoMode()
  const insights = demoDashboard.insights

  const kpis = demo
    ? [
        {
          ...staticKpis[0],
          value: insights.avgDailyTokens,
          change: '+9% vs last week',
          trend: 'up' as const,
          spark: insights.weeklyTokens.map((row) => row.value),
        },
        {
          ...staticKpis[1],
          value: insights.successRate,
          change: '+2% vs last week',
          trend: 'up' as const,
        },
        {
          ...staticKpis[2],
          value: insights.activeAgents,
          change: '3 ran today',
          trend: 'neutral' as const,
        },
        {
          ...staticKpis[3],
          value: `${insights.costPerDay}/day`,
          change: '-6% vs last week',
          trend: 'down' as const,
        },
      ]
    : staticKpis
  const weeklyTokens = demo ? insights.weeklyTokens : staticWeeklyTokens
  const workflowRuns = demo ? insights.weeklyRuns : staticWorkflowRuns

  return (
    <PageShell>
      <PageHeader
        title="Insights"
        description="Track usage trends, workflow performance, and agent activity over time."
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
              <div className="border-b border-border px-4 py-2.5">
                <h2 className="text-[13px] font-semibold text-foreground">
                  Token usage · last 7 days
                </h2>
              </div>
              <div className="p-4">
                <MiniBars
                  data={weeklyTokens}
                  max={Math.max(1, ...weeklyTokens.map((entry) => entry.value))}
                  tone="bg-gradient-to-t from-accent/50 to-accent"
                />
              </div>
            </Card>
          </motion.div>

          <motion.div variants={fadeUp}>
            <Card padding="none" className="h-full overflow-hidden">
              <div className="border-b border-border px-4 py-2.5">
                <h2 className="text-[13px] font-semibold text-foreground">
                  Workflow runs · last 7 days
                </h2>
              </div>
              <div className="p-4">
                <MiniBars
                  data={workflowRuns}
                  max={Math.max(1, ...workflowRuns.map((entry) => entry.value))}
                  tone="bg-gradient-to-t from-info/50 to-info"
                />
              </div>
            </Card>
          </motion.div>
        </div>
      </motion.div>
    </PageShell>
  )
}

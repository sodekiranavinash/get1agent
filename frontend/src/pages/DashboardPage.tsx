import { Link } from 'react-router-dom'
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
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { MiniBars } from '../components/ui/MiniBars'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { StatCard } from '../components/ui/StatCard'
import { fadeUp, stagger } from '../lib/motion'

const kpis = [
  {
    label: 'Active agents',
    value: '12',
    change: '+3 this week',
    trend: 'up' as const,
    icon: Bot,
    spark: [4, 5, 5, 7, 8, 10, 12],
  },
  {
    label: 'Workflows',
    value: '8',
    change: '2 running now',
    trend: 'neutral' as const,
    icon: Workflow,
    iconColor: 'text-info',
    spark: [3, 4, 4, 5, 6, 7, 8],
  },
  {
    label: 'Tokens used',
    value: '1.2M',
    change: '+18% vs last week',
    trend: 'up' as const,
    icon: Zap,
    iconColor: 'text-warning',
    spark: [40, 52, 48, 66, 60, 78, 92],
  },
  {
    label: 'AI credits',
    value: '$47.20',
    change: '$12.80 remaining',
    trend: 'down' as const,
    icon: Coins,
    iconColor: 'text-success',
    spark: [70, 66, 60, 58, 50, 44, 40],
  },
]

const agents = [
  { name: 'Research Assistant', model: 'Claude Sonnet', status: 'active' },
  { name: 'Code Reviewer', model: 'GPT-4o', status: 'active' },
  { name: 'Data Analyst', model: 'Gemini Pro', status: 'draft' },
]

const quickActions = [
  { label: 'New workflow', to: '/workflow-builder', icon: Workflow },
  { label: 'Open chat', to: '/chat', icon: Sparkles },
  { label: 'New schedule', to: '/scheduled-jobs', icon: CalendarClock },
]

const runs = [
  { label: 'Mon', value: 12 },
  { label: 'Tue', value: 18 },
  { label: 'Wed', value: 15 },
  { label: 'Thu', value: 22 },
  { label: 'Fri', value: 19 },
  { label: 'Sat', value: 24 },
  { label: 'Sun', value: 21 },
]

const activity = [
  { action: 'Workflow completed', detail: 'Daily Report Pipeline', time: '2m ago' },
  { action: 'Agent created', detail: 'Research Assistant', time: '1h ago' },
  { action: 'Scheduled run', detail: 'Customer Support Flow', time: '3h ago' },
  { action: 'Credits topped up', detail: '$25.00 added', time: 'Yesterday' },
]

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

export function DashboardPage() {
  return (
    <PageShell>
      <PageHeader
        title="Dashboard"
        description="Overview of your agents, workflows, usage, and recent activity."
        action={{ label: 'Create agent', icon: <Plus className="size-3.5" /> }}
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
                <span className="text-xs font-medium text-accent">
                  Workspace overview
                </span>
              </div>
              <h2 className="mt-2 text-base font-semibold tracking-tight text-foreground">
                Everything is running smoothly
              </h2>
              <p className="mt-1 max-w-xl text-[13px] text-muted">
                12 agents active, 2 workflows executing now, and no failed runs
                in the last 24 hours.
              </p>
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
            <div className="grid h-full gap-3 sm:grid-cols-3">
              {agents.map((agent) => (
                <Link
                  key={agent.name}
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
                      {agent.status}
                    </Badge>
                  </div>
                  <p className="mt-3 truncate text-[13px] font-semibold text-foreground">
                    {agent.name}
                  </p>
                  <p className="mt-0.5 truncate text-xs text-muted">{agent.model}</p>
                </Link>
              ))}
            </div>
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
              <PanelHeader title="Workflow runs · last 7 days" />
              <div className="p-4">
                <MiniBars data={runs} max={24} tone="bg-gradient-to-t from-info/50 to-info" />
              </div>
            </Card>
          </motion.div>

          <motion.div variants={fadeUp}>
            <Card padding="none" className="h-full overflow-hidden">
              <PanelHeader title="Activity" />
              <div className="divide-y divide-border">
                {activity.map((item, index) => (
                  <div key={`${item.action}-${index}`} className="flex items-center gap-3 px-4 py-2.5">
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
            </Card>
          </motion.div>
        </div>
      </motion.div>
    </PageShell>
  )
}

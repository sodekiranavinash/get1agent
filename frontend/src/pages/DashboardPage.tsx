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
import { Button } from '../components/ui/Button'
import { Card, CardDescription, CardHeader, CardTitle } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { StatCard } from '../components/ui/StatCard'

const recentAgents = [
  { name: 'Research Assistant', model: 'Claude Sonnet', status: 'active' },
  { name: 'Code Reviewer', model: 'GPT-4o', status: 'active' },
  { name: 'Data Analyst', model: 'Gemini Pro', status: 'draft' },
]

const recentWorkflows = [
  { name: 'Daily Report Pipeline', runs: 12, status: 'running' },
  { name: 'Customer Support Flow', runs: 48, status: 'idle' },
  { name: 'Content Generator', runs: 7, status: 'scheduled' },
]

const activity = [
  { action: 'Workflow completed', detail: 'Daily Report Pipeline', time: '2m ago' },
  { action: 'Agent created', detail: 'Research Assistant', time: '1h ago' },
  { action: 'Scheduled run', detail: 'Customer Support Flow', time: '3h ago' },
  { action: 'Credits topped up', detail: '$25.00 added', time: 'Yesterday' },
]

const quickActions = [
  { label: 'New Agent', to: '/agent-builder', icon: Bot },
  { label: 'New Workflow', to: '/workflow-builder', icon: Workflow },
  { label: 'Open Chat', to: '/chat', icon: Sparkles },
  { label: 'New Schedule', to: '/scheduled-jobs', icon: CalendarClock },
]

export function DashboardPage() {
  return (
    <PageShell>
      <PageHeader
        title="Dashboard"
        description="Overview of your agents, workflows, usage, and recent activity."
        badge="Workspace"
        action={{ label: 'Create Agent', icon: <Plus className="h-4 w-4" /> }}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Active Agents"
          value="12"
          change="+3 this week"
          trend="up"
          icon={Bot}
          delay={0}
        />
        <StatCard
          label="Workflows"
          value="8"
          change="2 running now"
          trend="neutral"
          icon={Workflow}
          iconColor="text-info"
          delay={0.05}
        />
        <StatCard
          label="Tokens Used"
          value="1.2M"
          change="+18% vs last week"
          trend="up"
          icon={Zap}
          iconColor="text-warning"
          delay={0.1}
        />
        <StatCard
          label="AI Credits"
          value="$47.20"
          change="$12.80 remaining"
          trend="down"
          icon={Coins}
          iconColor="text-success"
          delay={0.15}
        />
      </div>

      <div className="mt-8 grid gap-6 lg:grid-cols-3">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="lg:col-span-2"
        >
          <Card padding="lg">
            <CardHeader>
              <div>
                <CardTitle>Recent Agents</CardTitle>
                <CardDescription>Your latest configured agents</CardDescription>
              </div>
              <Link
                to="/agent-builder"
                className="text-xs font-semibold text-accent no-underline hover:text-accent-hover"
              >
                View all
              </Link>
            </CardHeader>

            <div className="space-y-2">
              {recentAgents.map((agent, index) => (
                <motion.div
                  key={agent.name}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.25 + index * 0.05 }}
                  className="flex items-center justify-between rounded-xl border border-border bg-raised/50 px-4 py-3 transition-colors hover:border-accent/20 hover:bg-raised"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
                      <Bot className="h-4 w-4" strokeWidth={1.75} />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground">{agent.name}</p>
                      <p className="text-xs text-muted">{agent.model}</p>
                    </div>
                  </div>
                  <Badge
                    variant={agent.status === 'active' ? 'success' : 'default'}
                    dot={agent.status === 'active'}
                  >
                    {agent.status}
                  </Badge>
                </motion.div>
              ))}
            </div>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.25 }}
        >
          <Card padding="lg" className="h-full">
            <CardHeader>
              <div>
                <CardTitle>Quick Actions</CardTitle>
                <CardDescription>Jump into your workflow</CardDescription>
              </div>
            </CardHeader>

            <div className="grid grid-cols-2 gap-2">
              {quickActions.map(({ label, to, icon: Icon }) => (
                <Link
                  key={to}
                  to={to}
                  className="group flex flex-col items-center gap-2 rounded-xl border border-border bg-raised/50 p-4 text-center no-underline transition-all hover:border-accent/30 hover:bg-accent-soft"
                >
                  <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-surface text-accent transition-transform group-hover:scale-110">
                    <Icon className="h-5 w-5" strokeWidth={1.75} />
                  </div>
                  <span className="text-xs font-semibold text-foreground">{label}</span>
                </Link>
              ))}
            </div>
          </Card>
        </motion.div>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
        >
          <Card padding="lg">
            <CardHeader>
              <div>
                <CardTitle>Recent Workflows</CardTitle>
                <CardDescription>Execution status at a glance</CardDescription>
              </div>
              <Link
                to="/workflow-builder"
                className="text-xs font-semibold text-accent no-underline hover:text-accent-hover"
              >
                View all
              </Link>
            </CardHeader>

            <div className="space-y-2">
              {recentWorkflows.map((workflow) => (
                <div
                  key={workflow.name}
                  className="flex items-center justify-between rounded-xl border border-border px-4 py-3 transition-colors hover:border-accent/20"
                >
                  <div className="flex items-center gap-3">
                    <Workflow className="h-4 w-4 text-info" strokeWidth={1.75} />
                    <div>
                      <p className="text-sm font-medium text-foreground">{workflow.name}</p>
                      <p className="text-xs text-muted">{workflow.runs} runs</p>
                    </div>
                  </div>
                  <Badge
                    variant={
                      workflow.status === 'running'
                        ? 'success'
                        : workflow.status === 'scheduled'
                          ? 'warning'
                          : 'default'
                    }
                    dot={workflow.status === 'running'}
                  >
                    {workflow.status}
                  </Badge>
                </div>
              ))}
            </div>
          </Card>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
        >
          <Card padding="lg">
            <CardHeader>
              <div>
                <CardTitle>Activity Feed</CardTitle>
                <CardDescription>Latest events across your workspace</CardDescription>
              </div>
            </CardHeader>

            <div className="relative space-y-0">
              {activity.map((item, index) => (
                <div
                  key={`${item.action}-${index}`}
                  className="relative flex gap-3 pb-4 last:pb-0"
                >
                  {index < activity.length - 1 ? (
                    <span
                      className="absolute top-6 left-[7px] h-[calc(100%-12px)] w-px bg-border"
                      aria-hidden="true"
                    />
                  ) : null}
                  <span className="relative z-10 mt-1.5 h-3.5 w-3.5 shrink-0 rounded-full border-2 border-accent bg-surface" />
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium text-foreground">{item.action}</p>
                    <p className="text-xs text-muted">{item.detail}</p>
                  </div>
                  <span className="shrink-0 text-[11px] text-subtle">{item.time}</span>
                </div>
              ))}
            </div>

            <Button variant="ghost" size="sm" className="mt-4 w-full" icon={<ArrowRight className="h-3.5 w-3.5" />}>
              View full activity
            </Button>
          </Card>
        </motion.div>
      </div>
    </PageShell>
  )
}

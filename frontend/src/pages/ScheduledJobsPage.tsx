import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Bot,
  CalendarClock,
  Clock,
  ExternalLink,
  MoreHorizontal,
  Network,
  Pencil,
  Plus,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu'
import {
  describeSchedule,
  formatScheduleRun,
  nextScheduleRuns,
  partsFromCron,
  useAgents,
  type AgentSchedule,
} from '../lib/agents'
import { useWorkflows } from '../lib/workflows'
import { formatRelative } from '../lib/knowledgeBases'
import { fadeUp } from '../lib/motion'

type ScheduleRow = {
  id: string
  kind: 'agent' | 'workflow'
  name: string
  schedule: AgentSchedule
  lastRunAt: string | null
  /** The next firing instant, or null when paused or not parseable. */
  nextRun: Date | null
}

type Schedulable = {
  id: string
  name: string
  schedule: AgentSchedule | null
  lastRunAt: string | null
}

/**
 * A row only exists for a schedule the user actually configured: the untouched
 * builder default ships an empty cron, which is not a schedule.
 */
function toRow(item: Schedulable, kind: ScheduleRow['kind']): ScheduleRow | null {
  const schedule = item.schedule
  if (!schedule || !schedule.cron.trim()) return null
  const parts = partsFromCron(schedule.cron)
  const nextRun =
    schedule.enabled && parts
      ? (nextScheduleRuns(parts, schedule.timezone, 1)[0] ?? null)
      : null
  return {
    id: item.id,
    kind,
    name: item.name,
    schedule,
    lastRunAt: item.lastRunAt,
    nextRun,
  }
}

function nextRunLabel(row: ScheduleRow): string {
  if (!row.schedule.enabled) return 'Paused'
  if (row.nextRun) return formatScheduleRun(row.nextRun, row.schedule.timezone)
  return '—'
}

function ScheduleSkeleton() {
  return (
    <Card padding="none" className="overflow-hidden">
      <div className="divide-y divide-border">
        {[0, 1, 2].map((index) => (
          <div key={index} className="flex items-center gap-3 px-4 py-3.5">
            <span className="skeleton size-7 rounded-md" />
            <div className="flex-1 space-y-2">
              <span className="skeleton block h-3 w-44 rounded" />
              <span className="skeleton block h-2.5 w-64 rounded" />
            </div>
            <span className="skeleton h-5 w-16 rounded-full" />
          </div>
        ))}
      </div>
    </Card>
  )
}

export function ScheduledJobsPage() {
  const navigate = useNavigate()
  const agentsQuery = useAgents()
  const workflowsQuery = useWorkflows()

  const isPending = agentsQuery.isPending || workflowsQuery.isPending
  const isError = agentsQuery.isError || workflowsQuery.isError

  const rows = useMemo(() => {
    const built = [
      ...(agentsQuery.data?.agents ?? []).map((agent) => toRow(agent, 'agent')),
      ...(workflowsQuery.data?.workflows ?? []).map((workflow) =>
        toRow(workflow, 'workflow'),
      ),
    ].filter((row): row is ScheduleRow => row !== null)

    // Enabled first, then soonest to fire, then alphabetically.
    return built.sort((a, b) => {
      if (a.schedule.enabled !== b.schedule.enabled) {
        return a.schedule.enabled ? -1 : 1
      }
      if (a.nextRun && b.nextRun) return a.nextRun.getTime() - b.nextRun.getTime()
      if (a.nextRun) return -1
      if (b.nextRun) return 1
      return a.name.localeCompare(b.name)
    })
  }, [agentsQuery.data, workflowsQuery.data])

  const openBuilder = (row: ScheduleRow) => {
    navigate(
      row.kind === 'agent'
        ? `/agent-builder?agent=${row.id}`
        : `/workflow-builder?workflow=${row.id}`,
    )
  }

  const openChat = (row: ScheduleRow) => {
    navigate(
      row.kind === 'agent'
        ? `/chat?agent=${encodeURIComponent(row.name)}`
        : `/chat?workflow=${encodeURIComponent(row.name)}`,
    )
  }

  return (
    <PageShell>
      <PageHeader
        title="Schedules"
        description="Every schedule attached to your agents and workflows. Times are shown in each schedule's timezone."
        action={{
          label: 'New schedule',
          icon: <Plus className="size-3.5" />,
          onClick: () => navigate('/agent-builder'),
        }}
      />

      {isError ? (
        <ErrorState
          error={agentsQuery.error ?? workflowsQuery.error}
          title="Could not load schedules"
          onRetry={() => {
            agentsQuery.refetch()
            workflowsQuery.refetch()
          }}
        />
      ) : isPending ? (
        <ScheduleSkeleton />
      ) : rows.length === 0 ? (
        <Card padding="none">
          <div className="flex flex-col items-center justify-center gap-1.5 px-6 py-16 text-center">
            <span className="mb-1 flex size-10 items-center justify-center rounded-lg border border-border bg-raised text-subtle">
              <CalendarClock className="size-4" strokeWidth={1.75} />
            </span>
            <p className="text-[13px] font-medium text-foreground">No schedules yet</p>
            <p className="max-w-sm text-[12px] leading-relaxed text-subtle">
              Add a schedule card to an agent or workflow in the builder, then it
              appears here.
            </p>
          </div>
        </Card>
      ) : (
        <motion.div variants={fadeUp} initial="hidden" animate="show">
          <Card padding="none" className="overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] text-left">
                <thead>
                  <tr className="border-b border-border bg-raised/40">
                    {['Name', 'Schedule', 'Next run', 'Last run', 'Status', ''].map(
                      (header, index) => (
                        <th
                          key={index}
                          className="px-4 py-2.5 text-[11px] font-semibold text-muted"
                        >
                          {header}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {rows.map((row) => (
                    <tr
                      key={`${row.kind}-${row.id}`}
                      className="transition-colors hover:bg-raised/40"
                    >
                      <td className="px-4 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <span className="flex size-7 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
                            {row.kind === 'agent' ? (
                              <Bot className="size-3.5" strokeWidth={1.75} />
                            ) : (
                              <Network className="size-3.5" strokeWidth={1.75} />
                            )}
                          </span>
                          <div className="min-w-0">
                            <div className="truncate text-[13px] font-medium text-foreground">
                              {row.name}
                            </div>
                            <div className="text-[11px] text-subtle">
                              {row.kind === 'agent' ? 'Agent' : 'Workflow'}
                            </div>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted">
                        <span className="flex items-center gap-1.5">
                          <Clock className="size-3.5 shrink-0" />
                          <span className="min-w-0 truncate">
                            {describeSchedule(row.schedule.cron)}
                          </span>
                        </span>
                        <span className="mt-0.5 block pl-5 text-[11px] text-subtle">
                          {row.schedule.timezone}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted">
                        {nextRunLabel(row)}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-muted">
                        {row.lastRunAt ? formatRelative(row.lastRunAt) : 'Never'}
                      </td>
                      <td className="px-4 py-2.5">
                        <Badge
                          variant={row.schedule.enabled ? 'success' : 'warning'}
                          dot={row.schedule.enabled}
                        >
                          {row.schedule.enabled ? 'active' : 'paused'}
                        </Badge>
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              type="button"
                              aria-label={`Actions for ${row.name}`}
                              className="rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-foreground"
                            >
                              <MoreHorizontal className="size-4" />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end" className="w-44">
                            <DropdownMenuItem onSelect={() => openBuilder(row)}>
                              <Pencil className="size-3.5" />
                              Edit schedule
                            </DropdownMenuItem>
                            <DropdownMenuItem onSelect={() => openChat(row)}>
                              <ExternalLink className="size-3.5" />
                              Open in chat
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </motion.div>
      )}
    </PageShell>
  )
}

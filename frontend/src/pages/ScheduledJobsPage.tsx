import { motion } from 'framer-motion'
import {
  CalendarClock,
  Clock,
  MoreHorizontal,
  Pause,
  Pencil,
  Play,
  Plus,
  Trash2,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../components/ui/dropdown-menu'
import { fadeUp } from '../lib/motion'

const jobs = [
  {
    name: 'Daily Report Pipeline',
    schedule: 'Every day at 9:00 AM',
    nextRun: 'Tomorrow, 9:00 AM',
    status: 'active' as const,
    lastRun: 'Success · 2h ago',
  },
  {
    name: 'Weekly Analytics',
    schedule: 'Every Monday at 8:00 AM',
    nextRun: 'Mon, 8:00 AM',
    status: 'active' as const,
    lastRun: 'Success · 3 days ago',
  },
  {
    name: 'Customer Support Flow',
    schedule: 'Every hour',
    nextRun: 'In 42 min',
    status: 'paused' as const,
    lastRun: 'Failed · 1 day ago',
  },
]

export function ScheduledJobsPage() {
  return (
    <PageShell>
      <PageHeader
        title="Schedules"
        description="Automate saved agents and workflows on a schedule — set it and let them run on their own."
        action={{ label: 'New schedule', icon: <Plus className="size-3.5" /> }}
      />

      <motion.div variants={fadeUp} initial="hidden" animate="show">
        <Card padding="none" className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-left">
              <thead>
                <tr className="border-b border-border bg-raised/40">
                  {['Workflow', 'Schedule', 'Next run', 'Last run', 'Status', ''].map(
                    (header) => (
                      <th
                        key={header}
                        className="px-4 py-2.5 text-[11px] font-semibold text-muted"
                      >
                        {header}
                      </th>
                    ),
                  )}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {jobs.map((job) => (
                  <tr key={job.name} className="transition-colors hover:bg-raised/40">
                    <td className="px-4 py-2.5">
                      <div className="flex items-center gap-2.5">
                        <span className="flex size-7 items-center justify-center rounded-md border border-border bg-raised text-accent">
                          <CalendarClock className="size-3.5" strokeWidth={1.75} />
                        </span>
                        <span className="text-[13px] font-medium text-foreground">
                          {job.name}
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted">
                      <span className="flex items-center gap-1.5">
                        <Clock className="size-3.5" />
                        {job.schedule}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-xs text-muted">{job.nextRun}</td>
                    <td className="px-4 py-2.5 text-xs text-muted">{job.lastRun}</td>
                    <td className="px-4 py-2.5">
                      <Badge
                        variant={job.status === 'active' ? 'success' : 'warning'}
                        dot={job.status === 'active'}
                      >
                        {job.status}
                      </Badge>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <button
                            type="button"
                            aria-label={`Actions for ${job.name}`}
                            className="rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-foreground"
                          >
                            <MoreHorizontal className="size-4" />
                          </button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-40">
                          <DropdownMenuItem>
                            {job.status === 'active' ? (
                              <>
                                <Pause className="size-3.5" />
                                Pause
                              </>
                            ) : (
                              <>
                                <Play className="size-3.5" />
                                Resume
                              </>
                            )}
                          </DropdownMenuItem>
                          <DropdownMenuItem>
                            <Pencil className="size-3.5" />
                            Edit
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem variant="destructive">
                            <Trash2 className="size-3.5" />
                            Delete
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
    </PageShell>
  )
}

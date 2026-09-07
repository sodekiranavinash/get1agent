import { CalendarClock, Clock, Pause, Play, Plus } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

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
        title="Scheduled Jobs"
        description="Automate saved workflows on a schedule — set it and let agents run on their own."
        badge="Manage"
        action={{ label: 'New Schedule', icon: <Plus className="h-4 w-4" /> }}
      />

      <Card padding="none" className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead>
              <tr className="border-b border-border bg-raised/50">
                <th className="px-5 py-3 text-xs font-semibold tracking-wide text-muted uppercase">
                  Workflow
                </th>
                <th className="px-5 py-3 text-xs font-semibold tracking-wide text-muted uppercase">
                  Schedule
                </th>
                <th className="px-5 py-3 text-xs font-semibold tracking-wide text-muted uppercase">
                  Next Run
                </th>
                <th className="px-5 py-3 text-xs font-semibold tracking-wide text-muted uppercase">
                  Last Run
                </th>
                <th className="px-5 py-3 text-xs font-semibold tracking-wide text-muted uppercase">
                  Status
                </th>
                <th className="px-5 py-3" />
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr
                  key={job.name}
                  className="border-b border-border last:border-0 transition-colors hover:bg-raised/30"
                >
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
                        <CalendarClock className="h-4 w-4" strokeWidth={1.75} />
                      </div>
                      <span className="font-medium text-foreground">{job.name}</span>
                    </div>
                  </td>
                  <td className="px-5 py-4 text-muted">
                    <span className="flex items-center gap-1.5">
                      <Clock className="h-3.5 w-3.5" />
                      {job.schedule}
                    </span>
                  </td>
                  <td className="px-5 py-4 text-muted">{job.nextRun}</td>
                  <td className="px-5 py-4 text-muted">{job.lastRun}</td>
                  <td className="px-5 py-4">
                    <Badge
                      variant={job.status === 'active' ? 'success' : 'warning'}
                      dot={job.status === 'active'}
                    >
                      {job.status}
                    </Badge>
                  </td>
                  <td className="px-5 py-4">
                    <Button variant="ghost" size="sm">
                      {job.status === 'active' ? (
                        <Pause className="h-4 w-4" />
                      ) : (
                        <Play className="h-4 w-4" />
                      )}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </PageShell>
  )
}

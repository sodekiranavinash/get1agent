import { Download, GitBranch, Play, Workflow } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

const workflows = [
  {
    name: 'Daily Report Pipeline',
    description: 'Collects metrics, generates summary, sends to Slack.',
    nodes: 4,
    type: 'mine' as const,
    runs: 156,
  },
  {
    name: 'Customer Onboarding',
    description: 'Automated welcome emails and CRM updates.',
    nodes: 6,
    type: 'public' as const,
    runs: 892,
  },
  {
    name: 'Content Repurposing',
    description: 'Turn blog posts into social threads and newsletters.',
    nodes: 5,
    type: 'public' as const,
    runs: 234,
  },
]

export function WorkflowStorePage() {
  return (
    <PageShell>
      <PageHeader
        title="Workflow Store"
        description="Share workflows with the community or import proven automation templates."
        badge="Discover"
      />

      <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {workflows.map((workflow) => (
          <Card key={workflow.name} hover padding="lg">
            <div className="flex items-start justify-between gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-info-soft text-info">
                <Workflow className="h-5 w-5" strokeWidth={1.75} />
              </div>
              <Badge variant={workflow.type === 'mine' ? 'info' : 'default'}>
                {workflow.type === 'mine' ? 'Mine' : 'Community'}
              </Badge>
            </div>

            <h3 className="mt-4 text-base font-semibold text-foreground">{workflow.name}</h3>
            <p className="mt-2 text-sm leading-relaxed text-muted">{workflow.description}</p>

            <div className="mt-4 flex items-center gap-4 text-xs text-subtle">
              <span className="flex items-center gap-1">
                <GitBranch className="h-3.5 w-3.5" />
                {workflow.nodes} nodes
              </span>
              <span className="flex items-center gap-1">
                <Play className="h-3.5 w-3.5" />
                {workflow.runs} runs
              </span>
            </div>

            <div className="mt-5 flex gap-2">
              <Button
                variant={workflow.type === 'mine' ? 'primary' : 'secondary'}
                size="sm"
                className="flex-1"
              >
                {workflow.type === 'mine' ? 'Open' : 'Preview'}
              </Button>
              {workflow.type === 'public' ? (
                <Button variant="primary" size="sm" icon={<Download className="h-3.5 w-3.5" />}>
                  Import
                </Button>
              ) : null}
            </div>
          </Card>
        ))}
      </div>
    </PageShell>
  )
}

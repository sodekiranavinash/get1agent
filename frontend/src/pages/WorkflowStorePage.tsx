import { motion } from 'framer-motion'
import { Download, GitBranch, Play, Workflow } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { fadeUp, stagger } from '../lib/motion'

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
        title="Workflows"
        description="Share workflows with the community or import proven automation templates."
        badge="Library"
      />

      <Card padding="none" className="overflow-hidden">
        <motion.div variants={stagger} initial="hidden" animate="show" className="divide-y divide-border">
          {workflows.map((workflow) => (
            <motion.div
              key={workflow.name}
              variants={fadeUp}
              className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-raised/40"
            >
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-info">
                <Workflow className="h-4 w-4" strokeWidth={1.75} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="truncate text-[13px] font-medium text-foreground">
                    {workflow.name}
                  </h3>
                  <Badge variant={workflow.type === 'mine' ? 'info' : 'default'}>
                    {workflow.type === 'mine' ? 'Mine' : 'Community'}
                  </Badge>
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-3 text-xs text-subtle">
                  <span className="truncate">{workflow.description}</span>
                  <span className="flex items-center gap-1">
                    <GitBranch className="h-3 w-3" />
                    {workflow.nodes} nodes
                  </span>
                  <span className="flex items-center gap-1">
                    <Play className="h-3 w-3" />
                    {workflow.runs} runs
                  </span>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <Button variant="outline" size="sm">
                  {workflow.type === 'mine' ? 'Open' : 'Preview'}
                </Button>
                {workflow.type === 'public' ? (
                  <Button size="sm" icon={<Download className="h-3.5 w-3.5" />}>
                    Import
                  </Button>
                ) : null}
              </div>
            </motion.div>
          ))}
        </motion.div>
      </Card>
    </PageShell>
  )
}

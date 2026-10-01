import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Bot,
  Network,
  Pencil,
  Plus,
  Trash2,
  Workflow as WorkflowIcon,
} from 'lucide-react'
import { toast } from 'sonner'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { fadeUp, stagger } from '../lib/motion'
import { useApiClient } from '../lib/api'
import {
  deleteWorkflow,
  invalidateWorkflows,
  useWorkflows,
  workflowModeBlurb,
  workflowModeLabel,
  type Workflow,
} from '../lib/workflows'

function formatWhen(iso: string | null): string {
  if (!iso) return 'Never run'
  try {
    return new Date(iso).toLocaleDateString()
  } catch {
    return 'Never run'
  }
}

function WorkflowSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="rounded-lg border border-border bg-surface p-4">
          <div className="flex items-start justify-between">
            <Skeleton className="size-10" />
            <Skeleton className="h-5 w-14" />
          </div>
          <Skeleton className="mt-3 h-4 w-32" />
          <Skeleton className="mt-2 h-3 w-full" />
          <Skeleton className="mt-4 h-7 w-full" />
        </div>
      ))}
    </div>
  )
}

export function WorkflowStorePage() {
  const navigate = useNavigate()
  const api = useApiClient()
  const { data, isPending, isError, error, refetch } = useWorkflows()
  const [pendingDelete, setPendingDelete] = useState<Workflow | null>(null)
  const [deleting, setDeleting] = useState(false)

  const workflows = data?.workflows ?? []

  const handleDelete = async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await deleteWorkflow(api, pendingDelete.id)
      invalidateWorkflows()
      refetch()
      toast.success('Workflow deleted')
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Could not delete workflow')
    } finally {
      setDeleting(false)
      setPendingDelete(null)
    }
  }

  return (
    <PageShell>
      <PageHeader
        title="Workflows"
        description="Compose your agents into a graph or a swarm, then run the whole pipeline."
        badge="Build"
        action={{
          label: 'New workflow',
          icon: <Plus className="size-3.5" />,
          onClick: () => navigate('/workflow-builder'),
        }}
      />

      {isError ? (
        <ErrorState error={error} title="Could not load workflows" onRetry={refetch} />
      ) : isPending ? (
        <div className="mt-3">
          <WorkflowSkeleton />
        </div>
      ) : workflows.length === 0 ? (
        <div className="mt-3 flex flex-col items-center justify-center rounded-lg border border-dashed border-border bg-surface/50 px-6 py-16 text-center">
          <span className="flex size-10 items-center justify-center rounded-lg border border-border bg-raised text-muted">
            <WorkflowIcon className="size-5" strokeWidth={1.75} />
          </span>
          <p className="mt-3 text-[13px] font-medium text-foreground">No workflows yet</p>
          <p className="mt-1 max-w-sm text-xs text-muted">
            Use <span className="text-foreground">New workflow</span> above to drag your agents
            onto a canvas and connect them into a pipeline.
          </p>
        </div>
      ) : (
        <motion.div
          variants={stagger}
          initial="hidden"
          animate="show"
          className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
        >
          {workflows.map((workflow) => (
            <motion.div key={workflow.id} variants={fadeUp}>
              <div className="group flex h-full flex-col rounded-lg border border-border bg-surface p-4 transition-all duration-200 hover:-translate-y-0.5 hover:border-accent/30 hover:shadow-panel">
                <div className="flex items-start justify-between gap-2">
                  <span className="flex size-10 items-center justify-center rounded-lg border border-border bg-raised text-info">
                    {workflow.mode === 'swarm' ? (
                      <Network className="size-5" strokeWidth={1.75} />
                    ) : (
                      <WorkflowIcon className="size-5" strokeWidth={1.75} />
                    )}
                  </span>
                  <Badge variant={workflow.mode === 'swarm' ? 'accent' : 'info'} dot>
                    {workflowModeLabel(workflow.mode)}
                  </Badge>
                </div>

                <h3 className="mt-3 truncate text-[13px] font-semibold text-foreground">
                  {workflow.name}
                </h3>
                <p className="mt-0.5 line-clamp-2 min-h-[2rem] text-xs text-muted">
                  {workflow.description || workflowModeBlurb(workflow.mode)}
                </p>

                <div className="mt-2 flex flex-wrap gap-1">
                  <span className="rounded border border-border bg-raised/50 px-1.5 py-0.5 text-[10px] text-subtle">
                    {workflow.agentCount} agent{workflow.agentCount === 1 ? '' : 's'}
                  </span>
                  <span className="rounded border border-border bg-raised/50 px-1.5 py-0.5 text-[10px] text-subtle">
                    {workflow.nodeCount} nodes
                  </span>
                  {workflow.schedule ? (
                    <span className="rounded border border-border bg-raised/50 px-1.5 py-0.5 text-[10px] text-subtle">
                      scheduled
                    </span>
                  ) : null}
                </div>

                <div className="mt-3 flex items-center gap-3 text-xs text-subtle">
                  <span className="flex items-center gap-1">
                    <Bot className="size-3" />
                    {workflow.verifiedAt ? 'Verified' : 'Draft'}
                  </span>
                  <span className="ml-auto truncate">{formatWhen(workflow.lastRunAt)}</span>
                </div>

                <div className="mt-auto flex items-center gap-1.5 pt-4">
                  <Button
                    variant="primary"
                    size="sm"
                    className="flex-1"
                    icon={<Pencil className="size-3.5" />}
                    onClick={() => navigate(`/workflow-builder?workflow=${workflow.id}`)}
                  >
                    Open
                  </Button>
                  <button
                    type="button"
                    title="Delete workflow"
                    onClick={() => setPendingDelete(workflow)}
                    className="flex size-8 shrink-0 items-center justify-center rounded-md border border-transparent text-subtle transition-colors hover:border-border hover:bg-raised hover:text-accent"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}

      <ConfirmDialog
        open={Boolean(pendingDelete)}
        onOpenChange={(open) => {
          if (!open) setPendingDelete(null)
        }}
        title={`Delete "${pendingDelete?.name ?? ''}"?`}
        description="This permanently removes the workflow. Your agents are not affected."
        confirmLabel="Delete"
        destructive
        loading={deleting}
        onConfirm={handleDelete}
      />
    </PageShell>
  )
}

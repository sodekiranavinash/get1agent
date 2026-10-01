import { ClipboardCheck, Trash2 } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { useApiClient } from '../../lib/api'
import { formatRelative } from '../../lib/knowledgeBases'
import {
  formatMode,
  formatPercent,
  formatTask,
  metricLabel,
  orderedMetrics,
  type EvalRun,
} from '../../lib/evals'

const RUN_VARIANT: Record<EvalRun['status'], 'success' | 'warning' | 'info' | 'default'> = {
  completed: 'success',
  failed: 'warning',
  running: 'info',
  queued: 'default',
}

export function RunsTab({
  runs,
  onOpen,
  onRefresh,
}: {
  runs: EvalRun[]
  onOpen: (runId: string) => void
  onRefresh: () => void
}) {
  const api = useApiClient()

  async function remove(run: EvalRun) {
    if (!window.confirm(`Delete this run of "${run.datasetName}"?`)) return
    try {
      await api.delete(`/v1/evals/runs/${run.runId}`)
    } finally {
      onRefresh()
    }
  }

  if (runs.length === 0) {
    return (
      <Card className="p-10 text-center">
        <ClipboardCheck className="mx-auto size-6 text-subtle" strokeWidth={1.5} />
        <p className="mt-3 text-[13px] text-muted">
          No evaluation runs yet. Start one from a dataset or the header action.
        </p>
      </Card>
    )
  }

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="divide-y divide-border">
        {runs.map((run) => {
          const metrics = orderedMetrics(run.metrics ?? {}).slice(0, 3)
          return (
            <div
              key={run.runId}
              onClick={() => onOpen(run.runId)}
              className="flex cursor-pointer flex-wrap items-center gap-3 px-4 py-3 transition-colors hover:bg-raised/30"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-foreground">{run.datasetName}</p>
                <p className="truncate text-xs text-muted">
                  {formatTask(run.config?.task)} · {formatMode(run.config?.mode ?? 'rag')}
                  {run.knowledgeBaseNames?.length ? ` · ${run.knowledgeBaseNames.join(', ')}` : ''}
                </p>
              </div>
              <div className="hidden items-center gap-1.5 md:flex">
                {metrics.map((name) => (
                  <span key={name} className="rounded border border-border bg-canvas px-2 py-1 text-[11px] text-muted">
                    {metricLabel(name)}{' '}
                    <span className="font-medium tabular-nums text-foreground">
                      {formatPercent(run.metrics[name])}
                    </span>
                  </span>
                ))}
              </div>
              <span className="text-xs text-muted">
                {run.completedCount}/{run.caseCount}
              </span>
              <Badge variant={RUN_VARIANT[run.status]} dot>
                {run.status}
              </Badge>
              <span className="hidden w-24 text-right text-xs text-subtle sm:block">
                {formatRelative(run.createdAt)}
              </span>
              <Button
                variant="ghost"
                size="sm"
                aria-label="Delete run"
                onClick={(event) => {
                  event.stopPropagation()
                  void remove(run)
                }}
                icon={<Trash2 className="size-3.5" />}
              >
                {null}
              </Button>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

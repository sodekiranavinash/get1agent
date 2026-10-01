import { Database, Play, Plus, Trash2 } from 'lucide-react'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { useApiClient } from '../../lib/api'
import { formatRelative } from '../../lib/knowledgeBases'
import type { EvalDataset } from '../../lib/evals'

export function DatasetsTab({
  datasets,
  onOpen,
  onAddCases,
  onRun,
  onRefresh,
}: {
  datasets: EvalDataset[]
  onOpen: (dataset: EvalDataset) => void
  onAddCases: (dataset: EvalDataset) => void
  onRun: (dataset: EvalDataset) => void
  onRefresh: () => void
}) {
  const api = useApiClient()

  async function remove(dataset: EvalDataset) {
    if (!window.confirm(`Delete the dataset "${dataset.name}" and its cases?`)) return
    try {
      await api.delete(`/v1/evals/datasets/${dataset.datasetId}`)
      onRefresh()
    } catch {
      // Refresh anyway; the list will reflect reality.
      onRefresh()
    }
  }

  if (datasets.length === 0) {
    return (
      <Card className="p-10 text-center">
        <Database className="mx-auto size-6 text-subtle" strokeWidth={1.5} />
        <p className="mt-3 text-[13px] text-muted">
          No datasets yet. Create one from the header action, then add golden cases.
        </p>
      </Card>
    )
  }

  return (
    <Card padding="none" className="overflow-hidden">
      <div className="divide-y divide-border">
        {datasets.map((dataset) => (
          <div
            key={dataset.datasetId}
            onClick={() => onOpen(dataset)}
            className="flex cursor-pointer flex-wrap items-center gap-3 px-4 py-3 transition-colors hover:bg-raised/30"
          >
            <span className="flex size-7 items-center justify-center rounded-md border border-border bg-raised text-info">
              <Database className="size-3.5" strokeWidth={1.75} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[13px] font-medium text-foreground">{dataset.name}</p>
              {dataset.description ? (
                <p className="truncate text-xs text-muted">{dataset.description}</p>
              ) : null}
            </div>
            <span className="text-xs text-muted">
              {typeof dataset.caseCount === 'number' ? `${dataset.caseCount} cases` : '—'}
            </span>
            <span className="hidden w-24 text-right text-xs text-subtle sm:block">
              {formatRelative(dataset.updatedAt)}
            </span>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={(event) => {
                  event.stopPropagation()
                  onRun(dataset)
                }}
                icon={<Play className="size-3.5" />}
              >
                Run
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={(event) => {
                  event.stopPropagation()
                  onAddCases(dataset)
                }}
                icon={<Plus className="size-3.5" />}
              >
                Cases
              </Button>
              <Button
                variant="ghost"
                size="sm"
                aria-label={`Delete ${dataset.name}`}
                onClick={(event) => {
                  event.stopPropagation()
                  void remove(dataset)
                }}
                icon={<Trash2 className="size-3.5" />}
              >
                {null}
              </Button>
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}

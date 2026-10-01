import { useState } from 'react'
import { Play, Plus } from 'lucide-react'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Spinner } from '../ui/Spinner'
import { ApiError, useApiClient } from '../../lib/api'
import { usePageQuery } from '../../hooks/usePageQuery'
import { formatRelative } from '../../lib/knowledgeBases'
import {
  datasetRunsQueryKey,
  datasetQueryKey,
  type EvalCase,
  type EvalDataset,
  type EvalDatasetRun,
} from '../../lib/evals'
import { traceAnswer, traceQuestion, type LabTraceDetail } from '../../lib/lab'

type DatasetDetail = EvalDataset & { cases?: EvalCase[] }

export function DatasetDetailDialog({
  dataset,
  onOpenChange,
  onRun,
  onAddCases,
}: {
  dataset: EvalDataset | null
  onOpenChange: (open: boolean) => void
  onRun: (dataset: EvalDataset) => void
  onAddCases: (dataset: EvalDataset) => void
}) {
  const api = useApiClient()
  const name = dataset?.datasetId ?? 'none'

  const detail = usePageQuery<{ dataset: DatasetDetail }>(
    datasetQueryKey(name),
    () => api.get<{ dataset: DatasetDetail }>(`/v1/evals/datasets/${name}`),
    { enabled: dataset !== null },
  )
  const runs = usePageQuery<{ runs: EvalDatasetRun[] }>(
    datasetRunsQueryKey(name),
    () => api.get<{ runs: EvalDatasetRun[] }>(`/v1/evals/datasets/${name}/runs`),
    { enabled: dataset !== null },
  )

  const cases = detail.data?.dataset?.cases ?? []
  const [trace, setTrace] = useState<LabTraceDetail | null>(null)
  const [traceBusy, setTraceBusy] = useState(false)
  const [traceError, setTraceError] = useState('')
  const [activeCase, setActiveCase] = useState('')

  async function viewTrace(caseId: string, traceId: string) {
    setActiveCase(caseId)
    setTraceBusy(true)
    setTrace(null)
    setTraceError('')
    try {
      const response = await api.get<{ trace: LabTraceDetail }>(
        `/v1/lab/traces/${encodeURIComponent(traceId)}`,
      )
      setTrace(response.trace)
    } catch (error) {
      setTraceError(error instanceof ApiError ? error.message : 'Could not load the trace.')
    } finally {
      setTraceBusy(false)
    }
  }

  return (
    <Dialog
      open={dataset !== null}
      onOpenChange={onOpenChange}
      size="2xl"
      title={`Dataset · ${dataset?.name ?? ''}`}
      description={dataset?.description || 'Cases in this dataset and the runs that used it.'}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            variant="outline"
            onClick={() => dataset && onAddCases(dataset)}
            icon={<Plus className="size-3.5" />}
          >
            Add cases
          </Button>
          <Button
            onClick={() => dataset && onRun(dataset)}
            icon={<Play className="size-3.5" />}
          >
            Run evaluation
          </Button>
        </>
      }
    >
      {detail.isPending ? (
        <div className="flex items-center gap-2 py-8 text-[13px] text-muted">
          <Spinner size="sm" /> Loading dataset…
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-3 lg:grid-cols-[1fr_260px]">
            <div className="overflow-hidden rounded-lg border border-border">
              <div className="border-b border-border bg-raised/40 px-3 py-2 text-[11px] font-semibold text-muted">
                Cases ({cases.length})
              </div>
              {cases.length === 0 ? (
                <p className="px-3 py-6 text-center text-[12.5px] text-subtle">
                  No cases yet. Add one from the Traces page.
                </p>
              ) : (
                <div className="max-h-[46vh] divide-y divide-border overflow-y-auto">
                  {cases.map((item) => (
                    <div key={item.caseId} className="px-3 py-2.5">
                      <p className="text-[12.5px] text-foreground">{item.query || '(empty query)'}</p>
                      {item.expectedOutput ? (
                        <p className="mt-0.5 line-clamp-2 text-[12px] text-muted">
                          Expected: {item.expectedOutput}
                        </p>
                      ) : null}
                      <div className="mt-1 flex items-center gap-2">
                        {item.sourceTraceId ? (
                          <>
                            <span className="font-mono text-[11px] text-subtle">
                              trace {item.sourceTraceId.slice(0, 12)}…
                            </span>
                            <button
                              type="button"
                              className="text-[11.5px] text-accent hover:underline"
                              onClick={() => viewTrace(item.caseId, item.sourceTraceId as string)}
                            >
                              View trace
                            </button>
                          </>
                        ) : (
                          <span className="text-[11px] text-subtle">manual case</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="space-y-3">
              <div className="overflow-hidden rounded-lg border border-border">
                <div className="border-b border-border bg-raised/40 px-3 py-2 text-[11px] font-semibold text-muted">
                  Runs using this dataset
                </div>
                {runs.isPending ? (
                  <p className="px-3 py-3 text-[12px] text-subtle">Loading…</p>
                ) : (runs.data?.runs ?? []).length === 0 ? (
                  <p className="px-3 py-3 text-[12px] text-subtle">No runs yet.</p>
                ) : (
                  <ul className="divide-y divide-border">
                    {(runs.data?.runs ?? []).map((run) => (
                      <li key={run.id} className="px-3 py-2">
                        <p className="truncate text-[12.5px] text-foreground">{run.name}</p>
                        <p className="text-[11px] text-subtle">
                          {run.createdAt ? formatRelative(run.createdAt) : ''}
                        </p>
                      </li>
                    ))}
                  </ul>
                )}
              </div>

              {activeCase ? (
                <div className="rounded-lg border border-border bg-canvas/40 p-3">
                  <p className="mb-1 text-[11px] font-semibold text-muted">Source trace</p>
                  {traceBusy ? (
                    <Spinner size="xs" />
                  ) : traceError ? (
                    <p className="text-[12px] text-warning">{traceError}</p>
                  ) : (
                    <div className="space-y-2 text-[12px]">
                      <div>
                        <span className="text-subtle">Input: </span>
                        <span className="text-muted">{traceQuestion(trace) || '—'}</span>
                      </div>
                      <div>
                        <span className="text-subtle">Output: </span>
                        <span className="text-muted">{traceAnswer(trace) || '—'}</span>
                      </div>
                    </div>
                  )}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </Dialog>
  )
}

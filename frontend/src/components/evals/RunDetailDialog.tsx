import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Spinner } from '../ui/Spinner'
import { ApiError, useApiClient } from '../../lib/api'
import { usePageQuery } from '../../hooks/usePageQuery'
import {
  formatMode,
  formatPercent,
  metricLabel,
  orderedMetrics,
  runQueryKey,
  type EvalArtifact,
  type EvalCaseResult,
  type EvalRun,
} from '../../lib/evals'

type RunPayload = { run: EvalRun; cases: EvalCaseResult[] }

export function RunDetailDialog({
  runId,
  onOpenChange,
}: {
  runId: string | null
  onOpenChange: (open: boolean) => void
}) {
  const api = useApiClient()
  const { data, isPending, refetch } = usePageQuery<RunPayload>(
    runQueryKey(runId ?? 'none'),
    async () => {
      const [run, cases] = await Promise.all([
        api.get<{ run: EvalRun }>(`/v1/evals/runs/${runId}`),
        api.get<{ cases: EvalCaseResult[] }>(`/v1/evals/runs/${runId}/cases`),
      ])
      return { run: run.run, cases: cases.cases }
    },
    { enabled: runId !== null },
  )

  const run = data?.run
  const running = run?.status === 'queued' || run?.status === 'running'

  useEffect(() => {
    if (!runId || !running) return
    const timer = window.setInterval(() => refetch(), 4000)
    return () => window.clearInterval(timer)
  }, [runId, running, refetch])

  const [artifact, setArtifact] = useState<EvalArtifact | null>(null)
  const [artifactCaseId, setArtifactCaseId] = useState('')
  const [artifactBusy, setArtifactBusy] = useState(false)
  const [artifactError, setArtifactError] = useState('')

  async function openCase(caseId: string) {
    if (!runId) return
    setArtifactCaseId(caseId)
    setArtifactBusy(true)
    setArtifactError('')
    try {
      const response = await api.get<{ artifact: EvalArtifact | null }>(
        `/v1/evals/runs/${runId}/cases/${caseId}`,
      )
      setArtifact(response.artifact)
      if (!response.artifact) setArtifactError('Artifact not available.')
    } catch (error) {
      setArtifact(null)
      setArtifactError(error instanceof ApiError ? error.message : 'Could not load the case.')
    } finally {
      setArtifactBusy(false)
    }
  }

  return (
    <Dialog
      open={runId !== null}
      onOpenChange={onOpenChange}
      size="2xl"
      title={run ? `Run · ${run.datasetName}` : 'Evaluation run'}
      description={run ? `${formatMode(run.config?.mode ?? 'rag')} · ${run.knowledgeBaseNames.join(', ')}` : undefined}
      footer={
        <>
          <Button variant="outline" size="sm" onClick={() => refetch()} icon={<RefreshCw className="size-3.5" />}>
            Refresh
          </Button>
        </>
      }
    >
      {isPending && !run ? (
        <div className="flex items-center gap-2 py-8 text-[13px] text-muted">
          <Spinner size="sm" /> Loading run…
        </div>
      ) : !run ? (
        <p className="py-8 text-center text-[13px] text-muted">Run not found.</p>
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={run.status} />
            <span className="text-[12.5px] text-muted">
              {run.completedCount}/{run.caseCount} scored
              {run.failedCount ? ` · ${run.failedCount} failed` : ''}
              {run.skippedCount ? ` · ${run.skippedCount} skipped` : ''}
            </span>
            {running ? <Spinner size="xs" /> : null}
          </div>

          {run.error ? <p className="text-[12.5px] text-warning">{run.error}</p> : null}

          <div className="flex flex-wrap gap-2">
            {orderedMetrics(run.metrics ?? {}).map((name) => (
              <span
                key={name}
                className="rounded-md border border-border bg-canvas px-2.5 py-1.5 text-[12px] text-muted"
              >
                {metricLabel(name)}{' '}
                <span className="font-medium tabular-nums text-foreground">
                  {formatPercent(run.metrics[name])}
                </span>
              </span>
            ))}
          </div>

          <div className="grid gap-3 lg:grid-cols-2">
            <div className="overflow-hidden rounded-lg border border-border">
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-border bg-raised/40 text-[11px] font-semibold text-muted">
                    <th className="px-3 py-2">Case</th>
                    <th className="px-3 py-2">Score</th>
                    <th className="px-3 py-2">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {(data?.cases ?? []).map((item) => {
                    const first = orderedMetrics(item.metrics ?? {})[0]
                    return (
                      <tr
                        key={item.caseId}
                        onClick={() => openCase(item.caseId)}
                        className={`cursor-pointer transition-colors hover:bg-raised/40 ${
                          artifactCaseId === item.caseId ? 'bg-raised/50' : ''
                        }`}
                      >
                        <td className="max-w-0 px-3 py-2 text-[12.5px] text-foreground">
                          <span className="block truncate">{item.query || '(empty query)'}</span>
                        </td>
                        <td className="px-3 py-2 text-[12.5px] tabular-nums text-muted">
                          {first ? `${metricLabel(first)} ${formatPercent(item.metrics[first])}` : '—'}
                        </td>
                        <td className="px-3 py-2">
                          <CaseStatus status={item.status} />
                        </td>
                      </tr>
                    )
                  })}
                  {(data?.cases ?? []).length === 0 ? (
                    <tr>
                      <td colSpan={3} className="px-3 py-6 text-center text-[12.5px] text-muted">
                        No case results yet.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>

            <div className="min-h-[200px] rounded-lg border border-border bg-canvas/40 p-3">
              {artifactBusy ? (
                <div className="flex items-center gap-2 text-[13px] text-muted">
                  <Spinner size="sm" /> Loading case…
                </div>
              ) : artifactError ? (
                <p className="text-[12.5px] text-warning">{artifactError}</p>
              ) : artifact ? (
                <ArtifactView artifact={artifact} />
              ) : (
                <p className="text-[12.5px] text-subtle">Select a case to inspect its answer, contexts and judge reasoning.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </Dialog>
  )
}

function ArtifactView({ artifact }: { artifact: EvalArtifact }) {
  return (
    <div className="space-y-3 text-[12.5px]">
      <div>
        <p className="mb-1 text-[11px] font-semibold text-muted">Generated answer</p>
        <p className="whitespace-pre-wrap text-foreground">{artifact.answer || '— (retrieval only)'}</p>
      </div>
      {artifact.judge?.reasoning ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold text-muted">Judge reasoning</p>
          <p className="whitespace-pre-wrap text-muted">{artifact.judge.reasoning}</p>
        </div>
      ) : null}
      {artifact.judge?.claims && artifact.judge.claims.length > 0 ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold text-muted">Answer claims</p>
          <ul className="space-y-1">
            {artifact.judge.claims.map((claim, index) => (
              <li key={index} className="flex items-start gap-1.5">
                <span className={claim.supported ? 'text-success' : 'text-warning'}>
                  {claim.supported ? '✓' : '✗'}
                </span>
                <span className={claim.supported ? 'text-muted' : 'text-foreground'}>
                  {claim.text}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {artifact.judge?.passages && artifact.judge.passages.length > 0 ? (
        <div>
          <p className="mb-1 text-[11px] font-semibold text-muted">
            Context passages (
            {artifact.judge.passages.filter((passage) => passage.relevant).length}/
            {artifact.judge.passages.length} relevant)
          </p>
          <div className="flex flex-wrap gap-1">
            {artifact.judge.passages.map((passage) => (
              <span
                key={passage.index}
                className={`rounded border px-1.5 py-0.5 text-[11px] ${
                  passage.relevant
                    ? 'border-success/40 bg-success/10 text-success'
                    : 'border-border text-subtle'
                }`}
              >
                #{passage.index}
              </span>
            ))}
          </div>
        </div>
      ) : null}
      <div>
        <p className="mb-1 text-[11px] font-semibold text-muted">
          Retrieved contexts ({artifact.contexts?.length ?? 0})
        </p>
        <ul className="space-y-2">
          {(artifact.contexts ?? []).map((context, index) => (
            <li key={index} className="rounded-md border border-border bg-surface/60 p-2">
              <p className="mb-1 text-[11px] text-subtle">
                {context.fileName || context.documentId}
                {context.page ? ` · page ${context.page}` : ''}
              </p>
              <p className="line-clamp-4 whitespace-pre-wrap text-muted">{context.text}</p>
            </li>
          ))}
          {(artifact.contexts ?? []).length === 0 ? <li className="text-subtle">No contexts.</li> : null}
        </ul>
      </div>
      {artifact.error ? <p className="text-warning">{artifact.error}</p> : null}
    </div>
  )
}

function StatusBadge({ status }: { status: EvalRun['status'] }) {
  const variant =
    status === 'completed' ? 'success' : status === 'failed' ? 'warning' : 'info'
  return <Badge variant={variant} dot>{status}</Badge>
}

function CaseStatus({ status }: { status: EvalCaseResult['status'] }) {
  const variant = status === 'ok' ? 'success' : status === 'error' ? 'warning' : 'default'
  return <Badge variant={variant}>{status}</Badge>
}

import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ClipboardList, Database, FlaskConical, ListChecks } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../components/ui/tabs'
import { useApiClient } from '../lib/api'
import { usePageQuery } from '../hooks/usePageQuery'
import { invalidateQuery } from '../lib/query'
import {
  LAB_TRACES_QUERY_KEY,
  formatLatency,
  formatTimestamp,
  traceQuestion,
  type LabDataset,
  type LabQueue,
  type LabScoreConfig,
  type LabTrace,
} from '../lib/lab'
import { AddToDatasetDialog } from '../components/traces/AddToDatasetDialog'
import { AddToQueueDialog } from '../components/traces/AddToQueueDialog'
import { QueueReviewDialog } from '../components/traces/QueueReviewDialog'

type TracesResponse = {
  configured: boolean
  traces: LabTrace[]
  lookedFor?: string[]
  error?: string
  page?: number
  totalPages?: number
  totalItems?: number
}

type StoresResponse = {
  datasets: LabDataset[]
  queues: LabQueue[]
  scoreConfigs: LabScoreConfig[]
}

const PAGE_SIZE = 25

export function TracesPage() {
  const api = useApiClient()
  const navigate = useNavigate()
  const [tab, setTab] = useState('traces')
  const [page, setPage] = useState(1)

  const tracesQuery = usePageQuery<TracesResponse>(
    `${LAB_TRACES_QUERY_KEY}:${page}`,
    () => api.get<TracesResponse>(`/v1/lab/traces?page=${page}&limit=${PAGE_SIZE}`),
    { refetchOnMount: true },
  )
  const storesQuery = usePageQuery<StoresResponse>('lab-stores', async () => {
    const [datasets, queues, configs] = await Promise.all([
      api.get<{ datasets: LabDataset[] }>('/v1/lab/datasets'),
      api.get<{ queues: LabQueue[] }>('/v1/lab/queues'),
      api.get<{ scoreConfigs: LabScoreConfig[] }>('/v1/lab/score-configs'),
    ])
    return {
      datasets: datasets.datasets,
      queues: queues.queues,
      scoreConfigs: configs.scoreConfigs,
    }
  })

  const [datasetTrace, setDatasetTrace] = useState<LabTrace | null>(null)
  const [queueTrace, setQueueTrace] = useState<LabTrace | null>(null)
  const [reviewQueue, setReviewQueue] = useState<LabQueue | null>(null)

  function refreshStores() {
    invalidateQuery('lab-stores')
    storesQuery.refetch()
  }

  const data = tracesQuery.data
  const traces = data?.traces ?? []
  const configured = data?.configured !== false
  const datasets = storesQuery.data?.datasets ?? []
  const queues = storesQuery.data?.queues ?? []
  const scoreConfigs = storesQuery.data?.scoreConfigs ?? []
  const totalPages = data?.totalPages ?? 1

  return (
    <PageShell>
      <PageHeader
        title="Traces"
        description="Every agent and workflow run. This is the only place to add a trace to a dataset or a review queue."
        badge="Evaluate"
        badgeVariant="info"
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="traces">Traces</TabsTrigger>
          <TabsTrigger value="review">Review queues</TabsTrigger>
        </TabsList>

        <TabsContent value="traces">
          {tracesQuery.isPending ? (
            <TracesSkeleton />
          ) : tracesQuery.isError ? (
            <EmptyCard
              message={`Traces API error: ${tracesQuery.error?.message ?? 'unknown error'}`}
            />
          ) : !configured ? (
            <EmptyCard message="Trace storage isn’t configured for this environment yet. Set LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY on user-api." />
          ) : data?.error ? (
            <EmptyCard message={`Could not load traces from Langfuse: ${data.error}`} />
          ) : traces.length === 0 ? (
            <EmptyCard
              message={`No traces yet. Traces are written by agent runs — run an agent in chat and it will show up here. (Looking for traces owned by ${(data?.lookedFor ?? []).join(', ') || '—'}.)`}
            />
          ) : (
            <Card padding="none" className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[860px] text-left">
                  <thead>
                    <tr className="border-b border-border bg-raised/40 text-[11px] font-semibold text-muted">
                      <th className="px-4 py-2.5">Trace</th>
                      <th className="px-4 py-2.5">When</th>
                      <th className="px-4 py-2.5">Latency</th>
                      <th className="px-4 py-2.5">Tags</th>
                      <th className="px-4 py-2.5">Input</th>
                      <th className="px-4 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {traces.map((trace) => (
                      <tr key={trace.id} className="align-top transition-colors hover:bg-raised/30">
                        <td className="px-4 py-3">
                          <span className="font-mono text-[12px] text-foreground">
                            {trace.name || 'trace'}
                          </span>
                        </td>
                        <td className="px-4 py-3 text-[12px] text-muted">
                          {formatTimestamp(trace.timestamp)}
                        </td>
                        <td className="px-4 py-3 text-[12px] tabular-nums text-muted">
                          {formatLatency(trace.latency)}
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex flex-wrap gap-1">
                            {trace.tags.slice(0, 3).map((tag) => (
                              <Badge key={tag}>{tag}</Badge>
                            ))}
                          </div>
                        </td>
                        <td className="max-w-[280px] px-4 py-3">
                          <span className="line-clamp-2 text-[12.5px] text-muted">
                            {traceQuestion(trace) || '—'}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex justify-end gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => setDatasetTrace(trace)}
                              icon={<Database className="size-3.5" />}
                            >
                              Dataset
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() =>
                                navigate(`/playground?trace=${encodeURIComponent(trace.id)}`)
                              }
                              icon={<FlaskConical className="size-3.5" />}
                            >
                              Replay
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setQueueTrace(trace)}
                              icon={<ClipboardList className="size-3.5" />}
                            >
                              Queue
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {totalPages > 1 ? (
                <div className="flex items-center justify-between border-t border-border px-4 py-2.5">
                  <span className="text-[12px] text-subtle">
                    Page {page} of {totalPages}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page <= 1}
                      onClick={() => setPage((current) => Math.max(1, current - 1))}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage((current) => current + 1)}
                    >
                      Next
                    </Button>
                  </div>
                </div>
              ) : null}
            </Card>
          )}
        </TabsContent>

        <TabsContent value="review">
          {storesQuery.isPending ? (
            <TracesSkeleton />
          ) : queues.length === 0 ? (
            <EmptyCard message="No review queues yet. Add a trace to a queue from the Traces tab." />
          ) : (
            <Card padding="none" className="overflow-hidden">
              <div className="divide-y divide-border">
                {queues.map((queue) => (
                  <div key={queue.id} className="flex items-center gap-3 px-4 py-3">
                    <span className="flex size-7 items-center justify-center rounded-md border border-border bg-raised text-accent">
                      <ClipboardList className="size-3.5" strokeWidth={1.75} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-medium text-foreground">{queue.name}</p>
                      <p className="truncate text-xs text-muted">
                        {queue.scoreConfigIds?.length
                          ? `${queue.scoreConfigIds.length} score config(s)`
                          : 'No score configs'}
                      </p>
                    </div>
                    <Button variant="outline" size="sm" onClick={() => setReviewQueue(queue)}>
                      Review
                    </Button>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </TabsContent>
      </Tabs>

      <AddToDatasetDialog
        key={datasetTrace?.id ?? 'none'}
        trace={datasetTrace}
        datasets={datasets}
        onOpenChange={(open) => !open && setDatasetTrace(null)}
        onAdded={refreshStores}
      />
      <AddToQueueDialog
        key={queueTrace?.id ?? 'none'}
        trace={queueTrace}
        queues={queues}
        scoreConfigs={scoreConfigs}
        onOpenChange={(open) => !open && setQueueTrace(null)}
        onAdded={refreshStores}
        onConfigsChanged={refreshStores}
      />
      <QueueReviewDialog
        key={reviewQueue?.id ?? 'none'}
        queue={reviewQueue}
        scoreConfigs={scoreConfigs}
        onOpenChange={(open) => !open && setReviewQueue(null)}
        onChanged={refreshStores}
      />
    </PageShell>
  )
}

function EmptyCard({ message }: { message: string }) {
  return (
    <Card className="p-10 text-center">
      <ListChecks className="mx-auto size-6 text-subtle" strokeWidth={1.5} />
      <p className="mt-3 text-[13px] text-muted">{message}</p>
    </Card>
  )
}

function TracesSkeleton() {
  return (
    <div className="space-y-2">
      {Array.from({ length: 6 }).map((_, index) => (
        <Skeleton key={index} className="h-12 w-full" />
      ))}
    </div>
  )
}

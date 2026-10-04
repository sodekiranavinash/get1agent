import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ClipboardList,
  Database,
  FlaskConical,
  ListChecks,
  Search,
} from 'lucide-react'
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
  formatCostUsd,
  formatDurationMs,
  formatTimestamp,
  formatTokens,
  traceQuestion,
  usageTotals,
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
  nextCursor?: string | null
  error?: string
}

type StoresResponse = {
  datasets: LabDataset[]
  queues: LabQueue[]
  scoreConfigs: LabScoreConfig[]
}

const PAGE_SIZE = 25

const STATUS_STYLE: Record<string, string> = {
  ok: 'bg-success-soft text-success',
  completed: 'bg-success-soft text-success',
  error: 'bg-rose-soft text-rose',
  awaiting_input: 'bg-warning-soft text-warning',
  running: 'bg-info-soft text-info',
}

function StatusPill({ status }: { status?: string }) {
  const key = String(status || 'ok')
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] ${STATUS_STYLE[key] ?? 'bg-raised text-muted'}`}>
      {key === 'ok' || key === 'completed' ? 'Success' : key.replace(/_/g, ' ')}
    </span>
  )
}

export function TracesPage() {
  const api = useApiClient()
  const navigate = useNavigate()
  const [tab, setTab] = useState('traces')
  const [cursor, setCursor] = useState<string | null>(null)
  const [history, setHistory] = useState<(string | null)[]>([])
  const [agentFilter, setAgentFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [search, setSearch] = useState('')

  const tracesQuery = usePageQuery<TracesResponse>(
    `${LAB_TRACES_QUERY_KEY}:${cursor ?? 'first'}:${agentFilter}`,
    () =>
      api.get<TracesResponse>(
        `/v1/lab/traces?limit=${PAGE_SIZE}` +
          (cursor ? `&cursor=${encodeURIComponent(cursor)}` : '') +
          (agentFilter ? `&agentId=${encodeURIComponent(agentFilter)}` : ''),
      ),
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
  const traces = useMemo(() => data?.traces ?? [], [data])
  const configured = data?.configured !== false
  const nextCursor = data?.nextCursor ?? null
  const datasets = storesQuery.data?.datasets ?? []
  const queues = storesQuery.data?.queues ?? []
  const scoreConfigs = storesQuery.data?.scoreConfigs ?? []

  const agentOptions = useMemo(() => {
    const map = new Map<string, string>()
    for (const trace of traces) {
      if (trace.agentId) map.set(trace.agentId, trace.agentName || trace.agentId)
    }
    return [...map.entries()].sort((a, b) => a[1].localeCompare(b[1]))
  }, [traces])

  const visible = useMemo(() => {
    const query = search.trim().toLowerCase()
    return traces.filter((trace) => {
      if (statusFilter && String(trace.status || 'ok') !== statusFilter) return false
      if (!query) return true
      const haystack = [traceQuestion(trace), trace.name, trace.agentName, trace.model]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
      return haystack.includes(query)
    })
  }, [traces, search, statusFilter])

  function handleNext() {
    if (!nextCursor) return
    setHistory((stack) => [...stack, cursor])
    setCursor(nextCursor)
  }

  function handlePrev() {
    if (history.length === 0) return
    const copy = [...history]
    const previous = copy.pop() ?? null
    setHistory(copy)
    setCursor(previous)
  }

  return (
    <PageShell>
      <PageHeader
        title="Traces"
        description="Every agent and workflow run, with its full observation tree. Add a trace to a dataset or a review queue from here."
        badge="Evaluate"
        badgeVariant="info"
      />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="traces">Traces</TabsTrigger>
          <TabsTrigger value="review">Review queues</TabsTrigger>
        </TabsList>

        <TabsContent value="traces">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <div className="relative min-w-[200px] flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-3.5 -translate-y-1/2 text-subtle" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search question, agent or model…"
                className="w-full rounded-md border border-border bg-surface py-2 pl-9 pr-3 text-[12.5px] text-foreground outline-none placeholder:text-subtle focus:border-accent"
              />
            </div>
            <select
              value={agentFilter}
              onChange={(event) => {
                setAgentFilter(event.target.value)
                setCursor(null)
                setHistory([])
              }}
              className="rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] text-foreground outline-none focus:border-accent"
            >
              <option value="">All agents</option>
              {agentOptions.map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              className="rounded-md border border-border bg-surface px-3 py-2 text-[12.5px] text-foreground outline-none focus:border-accent"
            >
              <option value="">All statuses</option>
              <option value="ok">Success</option>
              <option value="error">Error</option>
              <option value="awaiting_input">Awaiting input</option>
            </select>
          </div>

          {tracesQuery.isPending ? (
            <TracesSkeleton />
          ) : tracesQuery.isError ? (
            <EmptyCard
              message={`Traces API error: ${tracesQuery.error?.message ?? 'unknown error'}`}
            />
          ) : !configured ? (
            <EmptyCard message="Traces aren’t available in this environment yet." />
          ) : data?.error ? (
            <EmptyCard message={`Could not load traces: ${data.error}`} />
          ) : visible.length === 0 ? (
            <EmptyCard message="No traces match. Traces are written by agent runs — run an agent in chat and it will show up here." />
          ) : (
            <Card padding="none" className="overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[980px] text-left">
                  <thead>
                    <tr className="border-b border-border bg-raised/40 text-[11px] font-semibold text-muted">
                      <th className="px-4 py-2.5">Trace</th>
                      <th className="px-4 py-2.5">Status</th>
                      <th className="px-4 py-2.5">Agent</th>
                      <th className="px-4 py-2.5">Model</th>
                      <th className="px-4 py-2.5">Latency</th>
                      <th className="px-4 py-2.5">Tokens</th>
                      <th className="px-4 py-2.5">Cost</th>
                      <th className="px-4 py-2.5">When</th>
                      <th className="px-4 py-2.5 text-right">Actions</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border">
                    {visible.map((trace) => {
                      const usage = usageTotals(trace.usage)
                      const latencyMs =
                        trace.latencyMs ?? (trace.latency ? trace.latency * 1000 : null)
                      return (
                        <tr
                          key={trace.id}
                          className="cursor-pointer align-top transition-colors hover:bg-raised/30"
                          onClick={() => navigate(`/traces/${encodeURIComponent(trace.id)}`)}
                        >
                          <td className="max-w-[320px] px-4 py-3">
                            <p className="truncate font-mono text-[12px] text-foreground">
                              {trace.name || 'trace'}
                            </p>
                            <p className="mt-0.5 line-clamp-1 text-[12px] text-muted">
                              {traceQuestion(trace) || '—'}
                            </p>
                          </td>
                          <td className="px-4 py-3">
                            <StatusPill status={trace.status} />
                          </td>
                          <td className="px-4 py-3 text-[12px] text-muted">
                            {trace.agentName || '—'}
                          </td>
                          <td className="px-4 py-3 text-[12px] text-muted">
                            {trace.model || '—'}
                          </td>
                          <td className="px-4 py-3 font-mono text-[12px] tabular-nums text-muted">
                            {formatDurationMs(latencyMs)}
                          </td>
                          <td className="px-4 py-3 font-mono text-[12px] tabular-nums text-muted">
                            {usage.total ? formatTokens(usage.total) : '—'}
                          </td>
                          <td className="px-4 py-3 font-mono text-[12px] tabular-nums text-muted">
                            {formatCostUsd(trace.costMicroUsd) ?? '—'}
                          </td>
                          <td className="px-4 py-3 text-[12px] text-muted">
                            {formatTimestamp(trace.timestamp)}
                          </td>
                          <td className="px-4 py-3">
                            <div
                              className="flex justify-end gap-1.5"
                              onClick={(event) => event.stopPropagation()}
                            >
                              <Button
                                variant="ghost"
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
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {history.length > 0 || nextCursor ? (
                <div className="flex items-center justify-between border-t border-border px-4 py-2.5">
                  <span className="text-[12px] text-subtle">
                    {visible.length} shown
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={history.length === 0}
                      onClick={handlePrev}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={!nextCursor}
                      onClick={handleNext}
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

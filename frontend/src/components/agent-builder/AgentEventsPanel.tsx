import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  FileText,
  Info,
  XCircle,
  type LucideIcon,
} from 'lucide-react'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs'
import { Spinner } from '../ui/Spinner'
import { RunTimeline } from '../chat/RunTimeline'
import { useApiClient } from '../../lib/api'
import type { AgentEvent, AgentEventKind } from '../../lib/agents'
import type { Conversation } from '../../lib/conversations'
import type { RunFields } from '../../lib/runState'

const KIND_META: Record<AgentEventKind, { icon: LucideIcon; className: string }> = {
  info: { icon: Info, className: 'text-muted' },
  success: { icon: CheckCircle2, className: 'text-success' },
  warning: { icon: AlertTriangle, className: 'text-warning' },
  error: { icon: XCircle, className: 'text-accent' },
  tool: { icon: Info, className: 'text-info' },
}

type Tab = 'response' | 'history' | 'errors'

function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (seconds < 5) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function Count({ value, tone }: { value: number; tone?: string }) {
  return (
    <span
      className={`rounded-full px-1.5 text-[10px] font-semibold tabular-nums ${
        tone ?? 'bg-raised text-subtle'
      }`}
    >
      {value}
    </span>
  )
}

function EventList({ events, empty }: { events: AgentEvent[]; empty: string }) {
  if (events.length === 0) {
    return <div className="px-5 py-10 text-center text-[12px] text-subtle">{empty}</div>
  }
  return (
    <ol className="relative">
      {events.map((event) => {
        const meta = KIND_META[event.kind] ?? KIND_META.info
        const Icon = meta.icon
        return (
          <li
            key={event.id}
            className="flex gap-3 border-b border-border/70 px-4 py-2.5 last:border-b-0"
          >
            <span className="mt-0.5 shrink-0">
              <Icon className={`size-3.5 ${meta.className}`} strokeWidth={1.9} />
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[12.5px] leading-snug text-foreground">{event.title}</p>
              {event.detail ? (
                <p className="mt-0.5 truncate text-[11px] text-muted">{event.detail}</p>
              ) : null}
            </div>
            <span className="shrink-0 whitespace-nowrap text-[10px] text-subtle">
              {timeAgo(event.at)}
            </span>
          </li>
        )
      })}
    </ol>
  )
}

function RunsList({
  agentId,
  agentName,
  refreshKey,
}: {
  agentId: string
  agentName: string
  refreshKey: number
}) {
  const api = useApiClient()
  const [runs, setRuns] = useState<Conversation[]>([])
  const [pending, setPending] = useState(true)

  useEffect(() => {
    if (!agentId) {
      setRuns([])
      setPending(false)
      return
    }
    let cancelled = false
    setPending(true)
    api
      .get<{ runs: Conversation[] }>(`/v1/agents/${agentId}/runs`)
      .then((response) => {
        if (!cancelled) setRuns(response.runs)
      })
      .catch(() => {
        if (!cancelled) setRuns([])
      })
      .finally(() => {
        if (!cancelled) setPending(false)
      })
    return () => {
      cancelled = true
    }
  }, [api, agentId, refreshKey])

  if (pending) {
    return (
      <div className="flex h-20 items-center justify-center">
        <Spinner label="Loading runs…" />
      </div>
    )
  }
  if (runs.length === 0) {
    return (
      <div className="px-5 py-8 text-center text-[12px] text-subtle">
        No runs yet. Run a test to see it here.
      </div>
    )
  }
  return (
    <ul>
      {runs.map((run) => (
        <li key={run.conversationId} className="border-b border-border/70 last:border-b-0">
          <Link
            to={`/chat/conversation/${run.conversationId}?agent=${encodeURIComponent(
              agentName || run.agentName,
            )}`}
            className="flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-raised/60"
          >
            <span className="mt-0.5 shrink-0 rounded-full bg-raised px-1.5 text-[10px] font-semibold tabular-nums text-subtle">
              #{run.conversationId}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-[12.5px] leading-snug text-foreground">
                {run.title || 'Untitled run'}
              </p>
              <p className="mt-0.5 truncate text-[11px] text-muted">
                {run.lastPreview || (run.kind === 'run' ? 'Test run' : 'Conversation')}
              </p>
            </div>
            <span className="shrink-0 whitespace-nowrap text-[10px] text-subtle">
              {timeAgo(run.updatedAt)}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  )
}

export function AgentEventsPanel({
  events,
  run = null,
  running = false,
  agentId = '',
  agentName = '',
  conversationId = '',
  refreshKey = 0,
}: {
  events: AgentEvent[]
  run?: RunFields | null
  running?: boolean
  agentId?: string
  agentName?: string
  conversationId?: string
  refreshKey?: number
}) {
  const [tab, setTab] = useState<Tab>('response')

  const errors = useMemo(
    () => events.filter((event) => event.kind === 'error' || event.kind === 'warning'),
    [events],
  )
  const toolCount = run?.tools.length ?? 0
  const answer = run?.answer ?? ''

  return (
    <aside className="hidden min-h-0 w-[384px] shrink-0 flex-col border-l border-border bg-surface lg:flex">
      <Tabs
        value={tab}
        onValueChange={(value) => setTab(value as Tab)}
        className="flex min-h-0 flex-1 flex-col gap-0"
      >
        <div className="shrink-0 border-b border-border px-4 pt-3.5 pb-3">
          <div className="mb-2.5">
            <h2 className="text-[13px] font-semibold text-foreground">Agent</h2>
            <p className="text-[11px] text-subtle">Run, history &amp; errors</p>
          </div>
          <TabsList className="w-full">
            <TabsTrigger value="response">
              Live
              <Count value={toolCount} />
            </TabsTrigger>
            <TabsTrigger value="history">History</TabsTrigger>
            <TabsTrigger value="errors">
              Errors
              {errors.length > 0 ? (
                <Count value={errors.length} tone="bg-accent-soft text-accent" />
              ) : (
                <Count value={0} />
              )}
            </TabsTrigger>
          </TabsList>
        </div>

        <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">
          <TabsContent value="response">
            {run ? (
              <div className="space-y-3 p-3">
                <RunTimeline
                  plan={run.plan}
                  planning={run.planning}
                  status={run.status}
                  startedAt={run.startedAt}
                  endedAt={run.endedAt}
                  usage={run.usage}
                  answer={run.answer}
                />
                {answer && conversationId ? (
                  <Link
                    to={`/chat/conversation/${conversationId}?agent=${encodeURIComponent(
                      agentName,
                    )}`}
                    className="flex items-center gap-2.5 rounded-lg border border-border bg-canvas/40 px-3 py-2.5 no-underline transition-colors hover:bg-raised/60"
                  >
                    <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-accent-soft text-accent">
                      <FileText className="size-3.5" strokeWidth={1.9} />
                    </span>
                    <span className="min-w-0 flex-1 truncate text-[12.5px] font-medium text-foreground">
                      Final Answer
                    </span>
                    <ArrowUpRight className="size-3.5 shrink-0 text-subtle" />
                  </Link>
                ) : null}
              </div>
            ) : (
              <div className="px-5 py-10 text-center text-[12px] text-subtle">
                {running ? 'Working…' : 'No run activity yet. Run a test to see the agent.'}
              </div>
            )}
          </TabsContent>
          <TabsContent value="history">
            <div className="border-b border-border/60 px-4 py-2 text-[10px] font-semibold tracking-[0.14em] text-subtle uppercase">
              Runs
            </div>
            <RunsList agentId={agentId} agentName={agentName} refreshKey={refreshKey} />
          </TabsContent>
          <TabsContent value="errors">
            <EventList events={errors} empty="No errors or warnings." />
          </TabsContent>
        </div>
      </Tabs>
    </aside>
  )
}

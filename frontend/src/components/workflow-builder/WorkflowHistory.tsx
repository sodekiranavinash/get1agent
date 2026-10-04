import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink } from 'lucide-react'
import { Spinner } from '../ui/Spinner'
import { useApiClient } from '../../lib/api'
import { traceViewHref } from '../../lib/trace'
import type { Conversation } from '../../lib/conversations'
import { RunFeedback } from '../chat/RunFeedback'

function timeAgo(iso: string): string {
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

/**
 * The workflow's persisted runs, mirroring the agent builder's History tab.
 * Each row opens the run in the chat screen, where the final answer renders.
 */
export function WorkflowHistory({
  workflowId,
  workflowName,
  refreshKey,
}: {
  workflowId: string
  workflowName: string
  refreshKey: number
}) {
  const api = useApiClient()
  const [runs, setRuns] = useState<Conversation[]>([])
  const [pending, setPending] = useState(true)

  useEffect(() => {
    if (!workflowId) return
    let cancelled = false
    api
      .get<{ runs: Conversation[] }>(`/v1/workflows/${workflowId}/runs`)
      .then((response) => {
        if (!cancelled) setRuns(response.runs ?? [])
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
  }, [api, workflowId, refreshKey])

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
        No runs yet. Run the workflow to see it here.
      </div>
    )
  }

  return (
    <ul>
      {runs.map((run) => (
        <li key={run.conversationId} className="border-b border-border/70 last:border-b-0">
          <div className="flex items-start gap-3 px-4 py-2.5 transition-colors hover:bg-raised/60">
            <Link
              to={`/chat/conversation/${run.conversationId}?workflow=${encodeURIComponent(
                workflowName || run.agentName,
              )}`}
              className="flex min-w-0 flex-1 items-start gap-3"
            >
              <span className="mt-0.5 shrink-0 rounded-full bg-raised px-1.5 text-[10px] font-semibold tabular-nums text-subtle">
                #{run.conversationId}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[12.5px] leading-snug text-foreground">
                  {run.title || 'Untitled run'}
                </p>
                <p className="mt-0.5 truncate text-[11px] text-muted">
                  {run.lastPreview || 'Workflow run'}
                </p>
              </div>
            </Link>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <span className="whitespace-nowrap text-[10px] text-subtle">
                {timeAgo(run.updatedAt)}
              </span>
              <div className="flex items-center gap-2">
                {run.lastRunId ? (
                  <RunFeedback
                    runId={run.lastRunId}
                    feedback={run.feedback}
                    traceId={run.lastTraceId}
                    conversationId={run.conversationId}
                  />
                ) : null}
                {traceViewHref(run.lastTraceUrl, run.lastTraceId) ? (
                  <a
                    href={traceViewHref(run.lastTraceUrl, run.lastTraceId) ?? undefined}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-[10px] font-medium text-subtle transition-colors hover:text-accent"
                  >
                    Trace
                    <ExternalLink className="size-2.5" strokeWidth={1.9} />
                  </a>
                ) : null}
              </div>
            </div>
          </div>
        </li>
      ))}
    </ul>
  )
}

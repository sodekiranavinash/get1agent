import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Boxes,
  CheckCircle2,
  ChevronDown,
  Database,
  FileSearch,
  Loader2,
  Radio,
  Scissors,
  UploadCloud,
  X,
  XCircle,
} from 'lucide-react'
import { Badge } from '../ui/Badge'
import { IconButton } from '../ui/IconButton'
import {
  formatBytes,
  formatRelative,
  type DocumentStatus,
  type IngestionEvent,
  type IngestionEventDetails,
  type IngestionEventStatus,
  type IngestionStage,
} from '../../lib/knowledgeBases'

type StageKey = 'uploaded' | 'extracted' | 'chunked' | 'embedding' | 'indexed'

const STAGES: { key: StageKey; label: string; icon: LucideIcon }[] = [
  { key: 'uploaded', label: 'Uploaded', icon: UploadCloud },
  { key: 'extracted', label: 'Parsed', icon: FileSearch },
  { key: 'chunked', label: 'Chunked', icon: Scissors },
  { key: 'embedding', label: 'Embedded', icon: Boxes },
  { key: 'indexed', label: 'Indexed', icon: Database },
]

type StageState = {
  stage: IngestionStage
  status: IngestionEventStatus
  message: string | null
  details: IngestionEventDetails | null
  createdAt: string
}

type DocumentActivity = {
  documentId: string
  fileName: string
  documentStatus: DocumentStatus
  latest: IngestionEvent
  stages: Partial<Record<StageKey, StageState>>
  failed: StageState | null
}

function formatCount(value: number): string {
  return value.toLocaleString('en-US')
}

function plural(value: number, label: string): string {
  return `${formatCount(value)} ${label}${value === 1 ? '' : 's'}`
}

function toStageState(event: IngestionEvent): StageState {
  return {
    stage: event.stage,
    status: event.status,
    message: event.message,
    details: event.details,
    createdAt: event.createdAt,
  }
}

function statusRank(status: IngestionEventStatus): number {
  if (status === 'succeeded') return 3
  if (status === 'failed') return 2
  return 1
}

function groupByDocument(events: IngestionEvent[]): DocumentActivity[] {
  const grouped = new Map<string, IngestionEvent[]>()
  for (const event of events) {
    const list = grouped.get(event.documentId)
    if (list) list.push(event)
    else grouped.set(event.documentId, [event])
  }

  const documents: DocumentActivity[] = []
  for (const [documentId, list] of grouped) {
    // Events arrive newest-first; the first entry is the document's latest state.
    const latest = list[0]
    const stages: Partial<Record<StageKey, StageState>> = {}
    let failed: StageState | null = null
    for (const event of list) {
      if (event.stage === 'failed') {
        if (!failed) failed = toStageState(event)
        continue
      }
      if (!(event.stage in STAGE_INDEX)) continue
      const key = event.stage as StageKey
      const existing = stages[key]
      if (!existing || statusRank(event.status) > statusRank(existing.status)) {
        stages[key] = toStageState(event)
      }
    }
    documents.push({
      documentId,
      fileName: latest.fileName,
      documentStatus: latest.documentStatus,
      latest,
      stages,
      failed,
    })
  }
  return documents
}

const STAGE_INDEX: Record<StageKey, number> = {
  uploaded: 0,
  extracted: 1,
  chunked: 2,
  embedding: 3,
  indexed: 4,
}

function frontierIndex(activity: DocumentActivity): number {
  for (let index = 0; index < STAGES.length; index += 1) {
    if (activity.stages[STAGES[index].key]?.status !== 'succeeded') return index
  }
  return -1
}

function failedStageKey(activity: DocumentActivity): StageKey | null {
  const stage = activity.failed?.details?.failedStage
  if (stage && stage in STAGE_INDEX) return stage as StageKey
  if (!activity.failed) return null
  const index = frontierIndex(activity)
  return index === -1 ? null : STAGES[index].key
}

type StageView = 'done' | 'active' | 'todo' | 'failed'

function stageView(activity: DocumentActivity, index: number): StageView {
  const key = STAGES[index].key
  if (failedStageKey(activity) === key) return 'failed'
  const entry = activity.stages[key]
  if (entry?.status === 'succeeded') return 'done'
  if (entry?.status === 'started') return 'active'
  if (isActive(activity) && index === frontierIndex(activity)) return 'active'
  return 'todo'
}

function isActive(activity: DocumentActivity): boolean {
  if (activity.failed) return false
  if (activity.documentStatus === 'ready' || activity.documentStatus === 'failed') {
    return false
  }
  return true
}

// A document that has not advanced in this long is shown as stalled so it is
// not mistaken for "ready" (e.g. the S3 event never reached the pipeline).
const STALL_MS = 5 * 60 * 1000

// Coarse clock so stall detection is pure during render (updated off a timer).
function useNow(): number | null {
  const [now, setNow] = useState<number | null>(null)
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 30_000)
    return () => window.clearInterval(id)
  }, [])
  return now
}

function statusLabel(activity: DocumentActivity): string {
  if (activity.failed) {
    return activity.failed.message || 'Ingestion failed'
  }
  switch (activity.documentStatus) {
    case 'ready':
      return 'Indexed and ready'
    case 'processing':
      return activity.latest.message || 'Processing'
    case 'uploaded':
      return 'Queued for processing'
    case 'pending':
      return 'Waiting for upload'
    default:
      return activity.latest.message || ''
  }
}

/**
 * Stage-specific detail line, built from the event's structured `details`.
 *
 * `chunkCount` is the document's text-chunk count. When a later stage's count
 * matches it (no image embeddings), the count is redundant and the stage renders
 * as a plain heading instead.
 */
function stageDetail(
  stage: StageKey,
  entry: StageState | undefined,
  chunkCount: number | undefined,
): string | null {
  if (!entry) return null
  const details = entry.details ?? {}
  switch (stage) {
    case 'uploaded': {
      const parts: string[] = []
      if (typeof details.sizeBytes === 'number') {
        parts.push(formatBytes(details.sizeBytes))
      }
      if (details.source === 'inline') parts.push('written')
      else if (details.source === 'upload') parts.push('uploaded')
      return parts.join(' · ') || entry.message
    }
    case 'extracted': {
      const parts: string[] = []
      if (typeof details.sourceBytes === 'number') {
        parts.push(formatBytes(details.sourceBytes))
      }
      if (details.images) parts.push(plural(details.images, 'image'))
      if (details.pages) parts.push(plural(details.pages, 'page'))
      if (details.sheets) parts.push(plural(details.sheets, 'sheet'))
      if (details.rows) parts.push(plural(details.rows, 'row'))
      if (details.paragraphs) parts.push(plural(details.paragraphs, 'paragraph'))
      if (details.words) parts.push(plural(details.words, 'word'))
      return parts.join(' · ') || entry.message
    }
    case 'chunked': {
      const parts: string[] = []
      if (details.chunks) parts.push(plural(details.chunks, 'chunk'))
      if (details.tokens) parts.push(`${formatCount(details.tokens)} tokens`)
      if (details.chunkSize) {
        parts.push(
          `${formatCount(details.chunkSize)}/${formatCount(details.chunkOverlap ?? 0)} size/overlap`,
        )
      }
      return parts.join(' · ') || entry.message
    }
    case 'embedding': {
      if (entry.status === 'started') {
        // Without images this is just the chunk count again — keep it a heading.
        if (!details.imageEmbeddings) return null
        return `Embedding ${formatCount(details.textEmbeddings ?? 0)} text · ${formatCount(
          details.imageEmbeddings,
        )} image…`
      }
      // Same count as the chunks => nothing new to say.
      if (details.embeddings && details.embeddings === chunkCount) return null
      const parts: string[] = []
      if (details.embeddings) parts.push(plural(details.embeddings, 'embedding'))
      if (details.textEmbeddings && details.imageEmbeddings) {
        parts.push(
          `${formatCount(details.textEmbeddings)} text · ${formatCount(details.imageEmbeddings)} image`,
        )
      }
      return parts.join(' · ') || entry.message
    }
    case 'indexed': {
      if (details.vectors && details.vectors === chunkCount) return null
      const parts: string[] = []
      if (details.vectors) parts.push(`${formatCount(details.vectors)} vectors`)
      if (details.chunks !== undefined || details.images !== undefined) {
        parts.push(
          `${formatCount(details.chunks ?? 0)} chunks · ${formatCount(details.images ?? 0)} images`,
        )
      }
      return parts.join(' · ') || entry.message
    }
  }
}

type IngestionActivityProps = {
  events: IngestionEvent[]
  /** Auto-refresh stopped after the cap; show a manual refresh. */
  capped?: boolean
  onRefresh?: () => void
  onClose?: () => void
}

export function IngestionActivity({
  events,
  capped = false,
  onRefresh,
  onClose,
}: IngestionActivityProps) {
  const documents = groupByDocument(events).sort(
    (a, b) =>
      new Date(b.latest.createdAt).getTime() -
      new Date(a.latest.createdAt).getTime(),
  )
  const active = documents.filter(isActive)
  const recent = documents.filter((item) => !isActive(item)).slice(0, 8)
  const hasActivity = documents.length > 0
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (documentId: string) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(documentId)) next.delete(documentId)
      else next.add(documentId)
      return next
    })
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border px-4 py-3">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2 w-2">
              {active.length > 0 ? (
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent opacity-60" />
              ) : null}
              <span
                className={`relative inline-flex h-2 w-2 rounded-full ${
                  active.length > 0 ? 'bg-accent' : 'bg-subtle'
                }`}
              />
            </span>
            <h2 className="text-[13px] font-semibold text-foreground">
              Ingestion activity
            </h2>
          </div>
          {onClose ? (
            <IconButton
              size="sm"
              aria-label="Close activity"
              title="Close activity"
              onClick={onClose}
            >
              <X className="h-3.5 w-3.5" />
            </IconButton>
          ) : null}
        </div>
        <p className="mt-0.5 text-xs text-muted">
          Live RAG pipeline — upload, parse, chunk, embed, index.
        </p>
        {capped && onRefresh ? (
          <div className="mt-2.5 flex items-center justify-between gap-2 rounded-md border border-warning/30 bg-warning-soft/40 px-2.5 py-1.5">
            <p className="text-[11px] text-muted">
              Live updates paused after 10 minutes.
            </p>
            <button
              type="button"
              onClick={onRefresh}
              className="shrink-0 text-[11px] font-medium text-accent hover:underline"
            >
              Refresh
            </button>
          </div>
        ) : null}
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-4">
        {!hasActivity ? (
          <div className="flex h-full flex-col items-center justify-center py-16 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-border bg-raised text-subtle">
              <Radio className="h-4 w-4" strokeWidth={1.5} />
            </div>
            <p className="mt-3 text-[13px] font-medium text-foreground">
              No activity yet
            </p>
            <p className="mt-1 max-w-[15rem] text-xs text-muted">
              Upload files to watch them move through the pipeline in real time.
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {active.map((activity) => (
              <PipelineCard key={activity.documentId} activity={activity} />
            ))}

            {recent.length > 0 ? (
              <div className={active.length > 0 ? 'pt-1' : ''}>
                <p className="mb-1.5 px-0.5 text-[10px] font-semibold tracking-[0.1em] text-subtle uppercase">
                  Recent
                </p>
                <div className="space-y-0.5">
                  {recent.map((activity) => (
                    <RecentEvent
                      key={activity.documentId}
                      activity={activity}
                      expanded={expanded.has(activity.documentId)}
                      onToggle={() => toggle(activity.documentId)}
                    />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        )}
      </div>
    </div>
  )
}

function PipelineCard({ activity }: { activity: DocumentActivity }) {
  const completed = STAGES.filter(
    (stage) => activity.stages[stage.key]?.status === 'succeeded',
  ).length
  const progress = Math.min(99, Math.round((completed / STAGES.length) * 100))
  const now = useNow()
  const stalled =
    now !== null && now - new Date(activity.latest.createdAt).getTime() > STALL_MS

  return (
    <div className="overflow-hidden rounded-lg border border-accent/25 bg-accent-soft/15">
      <div className="flex items-center justify-between gap-2 border-b border-accent/15 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-medium text-foreground">
            {activity.fileName}
          </p>
          <p className="mt-0.5 truncate text-[11px] text-muted">
            {stalled
              ? 'No progress for a while — check pipeline logs'
              : `${statusLabel(activity)} · ${progress}%`}
          </p>
        </div>
        <Badge variant={stalled ? 'warning' : 'accent'} dot>
          {stalled ? 'Stalled' : 'Live'}
        </Badge>
      </div>

      <div className="px-3 py-2.5">
        <div className="mb-2.5 h-1 w-full overflow-hidden rounded-full bg-accent-soft">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        <StageTimeline activity={activity} />
      </div>
    </div>
  )
}

function RecentEvent({
  activity,
  expanded,
  onToggle,
}: {
  activity: DocumentActivity
  expanded: boolean
  onToggle: () => void
}) {
  const failed = activity.failed !== null
  return (
    <div className="rounded-md transition-colors hover:bg-raised/60">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="flex w-full items-start gap-3 rounded-md px-2 py-2 text-left"
      >
        <span
          className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${
            failed ? 'bg-warning-soft text-warning' : 'bg-success-soft text-success'
          }`}
        >
          {failed ? (
            <XCircle className="h-3.5 w-3.5" />
          ) : (
            <CheckCircle2 className="h-3.5 w-3.5" />
          )}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-foreground">
            {activity.fileName}
          </p>
          <p className="truncate text-[11px] text-muted">
            {statusLabel(activity)}
          </p>
        </div>
        <span className="shrink-0 text-[11px] text-subtle">
          {formatRelative(activity.latest.createdAt)}
        </span>
        <ChevronDown
          className={`mt-0.5 h-3.5 w-3.5 shrink-0 text-subtle transition-transform ${
            expanded ? 'rotate-180' : ''
          }`}
        />
      </button>
      {expanded ? (
        <div className="px-2.5 pb-3 pl-11">
          <StageTimeline activity={activity} />
        </div>
      ) : null}
    </div>
  )
}

function StageTimeline({ activity }: { activity: DocumentActivity }) {
  const chunkCount = activity.stages.chunked?.details?.chunks
  return (
    <ol>
      {STAGES.map((stage, index) => {
        const view = stageView(activity, index)
        const entry = activity.stages[stage.key]
        const detail =
          view === 'todo'
            ? null
            : stageDetail(stage.key, entry, chunkCount) ??
              (view === 'failed' ? activity.failed?.message : null)
        const Icon = stage.icon
        return (
          <li key={stage.key} className="relative flex gap-3 pb-3 last:pb-0">
            {index < STAGES.length - 1 ? (
              <span
                className={`absolute top-6 left-[10.5px] h-[calc(100%-16px)] w-px ${
                  view === 'done' ? 'bg-success/40' : 'bg-border'
                }`}
                aria-hidden="true"
              />
            ) : null}
            <span
              className={`relative z-10 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border ${
                view === 'done'
                  ? 'border-success/30 bg-success-soft text-success'
                  : view === 'failed'
                    ? 'border-warning/30 bg-warning-soft text-warning'
                    : view === 'active'
                      ? 'border-accent/40 bg-accent-soft text-accent'
                      : 'border-border bg-raised text-subtle'
              }`}
            >
              {view === 'done' ? (
                <CheckCircle2 className="h-3.5 w-3.5" />
              ) : view === 'failed' ? (
                <XCircle className="h-3.5 w-3.5" />
              ) : view === 'active' ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Icon className="h-3 w-3" strokeWidth={1.75} />
              )}
            </span>
            <div className="min-w-0 flex-1 pt-0.5">
              <div className="flex items-baseline justify-between gap-2">
                <p
                  className={`text-xs font-medium ${
                    view === 'todo' ? 'text-subtle' : 'text-foreground'
                  }`}
                >
                  {stage.label}
                </p>
                {entry ? (
                  <span className="shrink-0 text-[10px] text-subtle">
                    {formatRelative(entry.createdAt)}
                  </span>
                ) : null}
              </div>
              {detail ? (
                <p
                  className={`mt-0.5 text-[11px] leading-relaxed ${
                    view === 'failed'
                      ? 'text-warning'
                      : view === 'active'
                        ? 'text-accent'
                        : 'text-muted'
                  }`}
                >
                  {detail}
                </p>
              ) : null}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

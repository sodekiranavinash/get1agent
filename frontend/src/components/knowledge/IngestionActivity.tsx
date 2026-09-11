import type { LucideIcon } from 'lucide-react'
import {
  Boxes,
  CheckCircle2,
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
  formatRelative,
  type DocumentStatus,
  type IngestionEvent,
} from '../../lib/knowledgeBases'

const STAGES: { key: string; label: string; icon: LucideIcon }[] = [
  { key: 'uploaded', label: 'Uploaded', icon: UploadCloud },
  { key: 'extracted', label: 'Parsing & cleaning', icon: FileSearch },
  { key: 'chunked', label: 'Chunking text', icon: Scissors },
  { key: 'embedding', label: 'Generating embeddings', icon: Boxes },
  { key: 'indexed', label: 'Writing to vector store', icon: Database },
]

const STAGE_INDEX: Record<string, number> = {
  uploaded: 0,
  extracted: 1,
  chunked: 2,
  embedding: 3,
  indexed: 4,
}

type DocumentActivity = {
  documentId: string
  fileName: string
  documentStatus: DocumentStatus
  latest: IngestionEvent
}

function groupByDocument(events: IngestionEvent[]): DocumentActivity[] {
  const grouped = new Map<string, DocumentActivity>()
  for (const event of events) {
    if (grouped.has(event.documentId)) continue
    grouped.set(event.documentId, {
      documentId: event.documentId,
      fileName: event.fileName,
      documentStatus: event.documentStatus,
      latest: event,
    })
  }
  return [...grouped.values()]
}

function isActive(activity: DocumentActivity): boolean {
  if (activity.latest.stage === 'failed') return false
  return activity.latest.status === 'started' || activity.documentStatus === 'processing'
}

type IngestionActivityProps = {
  events: IngestionEvent[]
  onClose?: () => void
}

export function IngestionActivity({
  events,
  onClose,
}: IngestionActivityProps) {
  const documents = groupByDocument(events)
  const active = documents.filter(isActive)
  const recent = documents.filter((item) => !isActive(item)).slice(0, 8)
  const hasActivity = documents.length > 0

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border px-5 py-4">
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
            <h2 className="text-sm font-semibold text-foreground">
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
              <X className="h-4 w-4" />
            </IconButton>
          ) : null}
        </div>
        <p className="mt-1 text-xs text-muted">
          Live RAG pipeline — upload, parse, chunk, embed, index.
        </p>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto px-5 py-4">
        {!hasActivity ? (
          <div className="flex h-full flex-col items-center justify-center py-16 text-center">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-raised text-subtle">
              <Radio className="h-5 w-5" strokeWidth={1.5} />
            </div>
            <p className="mt-3 text-sm font-medium text-foreground">
              No activity yet
            </p>
            <p className="mt-1 max-w-[15rem] text-xs text-muted">
              Upload files to watch them move through the pipeline in real time.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {active.map((activity) => (
              <PipelineCard key={activity.documentId} activity={activity} />
            ))}

            {recent.length > 0 ? (
              <div className={active.length > 0 ? 'pt-1' : ''}>
                <p className="mb-2 px-0.5 text-[10px] font-bold tracking-[0.16em] text-subtle uppercase">
                  Recent
                </p>
                <div className="space-y-0.5">
                  {recent.map((activity) => (
                    <RecentEvent key={activity.documentId} activity={activity} />
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
  const activeIndex = STAGE_INDEX[activity.latest.stage] ?? 0
  const progress = Math.min(
    99,
    Math.round(((activeIndex + 1) / STAGES.length) * 100),
  )

  return (
    <div className="overflow-hidden rounded-2xl border border-accent/25 bg-accent-soft/20">
      <div className="flex items-center justify-between gap-2 border-b border-accent/15 px-3.5 py-2.5">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-foreground">
            {activity.fileName}
          </p>
          <p className="mt-0.5 truncate text-[11px] text-muted">
            {activity.latest.message || 'In progress'} · {progress}%
          </p>
        </div>
        <Badge variant="accent" dot>
          Live
        </Badge>
      </div>

      <div className="px-3.5 py-3">
        <div className="mb-3 h-1 w-full overflow-hidden rounded-full bg-accent-soft">
          <div
            className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>

        <ol>
          {STAGES.map((stage, index) => {
            const state =
              index < activeIndex
                ? 'done'
                : index === activeIndex
                  ? 'active'
                  : 'todo'
            const Icon = stage.icon
            return (
              <li
                key={stage.key}
                className="relative flex gap-3 pb-3 last:pb-0"
              >
                {index < STAGES.length - 1 ? (
                  <span
                    className={`absolute top-6 left-[10.5px] h-[calc(100%-16px)] w-px ${
                      index < activeIndex ? 'bg-success/40' : 'bg-border'
                    }`}
                    aria-hidden="true"
                  />
                ) : null}
                <span
                  className={`relative z-10 flex h-[22px] w-[22px] shrink-0 items-center justify-center rounded-full border ${
                    state === 'done'
                      ? 'border-success/30 bg-success-soft text-success'
                      : state === 'active'
                        ? 'border-accent/40 bg-accent-soft text-accent'
                        : 'border-border bg-raised text-subtle'
                  }`}
                >
                  {state === 'done' ? (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  ) : state === 'active' ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : (
                    <Icon className="h-3 w-3" strokeWidth={1.75} />
                  )}
                </span>
                <div className="min-w-0 pt-0.5">
                  <p
                    className={`text-xs font-medium ${
                      state === 'todo' ? 'text-subtle' : 'text-foreground'
                    }`}
                  >
                    {stage.label}
                  </p>
                  {state === 'active' ? (
                    <p className="truncate text-[11px] text-accent">
                      {activity.latest.message || 'In progress…'}
                    </p>
                  ) : null}
                </div>
              </li>
            )
          })}
        </ol>
      </div>
    </div>
  )
}

function RecentEvent({ activity }: { activity: DocumentActivity }) {
  const failed = activity.latest.stage === 'failed'
  return (
    <div className="flex items-start gap-3 rounded-xl px-2.5 py-2 transition-colors hover:bg-raised/60">
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
          {failed
            ? activity.latest.message || 'Ingestion failed'
            : 'Indexed and ready'}
        </p>
      </div>
      <span className="shrink-0 text-[11px] text-subtle">
        {formatRelative(activity.latest.createdAt)}
      </span>
    </div>
  )
}

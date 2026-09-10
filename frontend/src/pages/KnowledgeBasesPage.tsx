import { useMemo, useState } from 'react'
import {
  AlertCircle,
  CheckCircle2,
  FileStack,
  Loader2,
  Paperclip,
  Plus,
  Upload,
  X,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'

type KnowledgeBaseStatus = 'ready' | 'processing' | 'failed'

type KnowledgeBase = {
  id: string
  name: string
  description: string
  fileCount: number
  status: KnowledgeBaseStatus
  attachedTo: { agents: number; workflows: number }
  updatedAt: string
}

type IngestionEvent = {
  id: string
  knowledgeBaseId: string
  message: string
  detail?: string
  status: 'active' | 'done' | 'error'
  time: string
}

const knowledgeBases: KnowledgeBase[] = [
  {
    id: 'kb-product',
    name: 'Product Documentation',
    description: 'Specs, API docs, and release notes for RAG retrieval.',
    fileCount: 24,
    status: 'ready',
    attachedTo: { agents: 2, workflows: 0 },
    updatedAt: '2 days ago',
  },
  {
    id: 'kb-sales',
    name: 'Q3 Sales Reports',
    description: 'PDF exports and spreadsheets from the sales team.',
    fileCount: 5,
    status: 'processing',
    attachedTo: { agents: 0, workflows: 0 },
    updatedAt: 'Just now',
  },
  {
    id: 'kb-hr',
    name: 'HR Policies',
    description: 'Handbooks, benefits guides, and onboarding material.',
    fileCount: 8,
    status: 'ready',
    attachedTo: { agents: 0, workflows: 1 },
    updatedAt: '1 week ago',
  },
  {
    id: 'kb-legal',
    name: 'Legal Contracts',
    description: 'Vendor agreements pending review and indexing.',
    fileCount: 2,
    status: 'failed',
    attachedTo: { agents: 0, workflows: 0 },
    updatedAt: '3 hours ago',
  },
]

const ingestionEvents: IngestionEvent[] = [
  {
    id: 'ev-1',
    knowledgeBaseId: 'kb-sales',
    message: 'Upload received',
    detail: '5 files queued',
    status: 'done',
    time: '2m ago',
  },
  {
    id: 'ev-2',
    knowledgeBaseId: 'kb-sales',
    message: 'Extracting text',
    detail: 'Parsing PDFs and spreadsheets',
    status: 'done',
    time: '1m ago',
  },
  {
    id: 'ev-3',
    knowledgeBaseId: 'kb-sales',
    message: 'Chunking documents',
    detail: '142 segments created',
    status: 'done',
    time: '45s ago',
  },
  {
    id: 'ev-4',
    knowledgeBaseId: 'kb-sales',
    message: 'Generating embeddings',
    detail: 'Batch 2 of 3',
    status: 'active',
    time: 'Now',
  },
  {
    id: 'ev-5',
    knowledgeBaseId: 'kb-sales',
    message: 'Building vector index',
    status: 'active',
    time: 'Pending',
  },
]

const statusConfig: Record<
  KnowledgeBaseStatus,
  { variant: 'success' | 'accent' | 'warning'; label: string }
> = {
  ready: { variant: 'success', label: 'Ready' },
  processing: { variant: 'accent', label: 'Processing' },
  failed: { variant: 'warning', label: 'Failed' },
}

export function KnowledgeBasesPage() {
  const [dismissedBanner, setDismissedBanner] = useState(false)

  const processingCount = knowledgeBases.filter((kb) => kb.status === 'processing').length
  const activeEvents = useMemo(
    () => ingestionEvents.filter((event) => event.knowledgeBaseId === 'kb-sales'),
    [],
  )
  const showEventsPanel = processingCount > 0

  return (
    <PageShell className="!py-0">
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-border px-6 py-5 lg:px-8">
            <PageHeader
              title="Knowledge"
              description="Upload documents for RAG. Attach ready knowledge bases to agents and workflows only."
              badge="Agents"
              action={{ label: 'New Knowledge Base', icon: <Plus className="h-4 w-4" /> }}
            />
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6 scrollbar-thin lg:px-8">
            {!dismissedBanner && processingCount > 0 ? (
              <div className="mb-6 flex items-start justify-between gap-4 rounded-2xl border border-accent/25 bg-accent-soft/40 px-4 py-3">
                <div className="flex items-start gap-3">
                  <Loader2 className="mt-0.5 h-4 w-4 shrink-0 animate-spin text-accent" />
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      Ingestion in progress for Q3 Sales Reports
                    </p>
                    <p className="mt-1 text-xs text-muted">
                      {showEventsPanel
                        ? 'Live processing events are streaming on the right.'
                        : 'Resize the window to see live ingestion events.'}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setDismissedBanner(true)}
                  className="rounded-md p-1 text-subtle transition-colors hover:bg-raised hover:text-foreground"
                  aria-label="Dismiss ingestion notice"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            ) : null}

            <Card
              padding="lg"
              className="mb-6 border-dashed border-border-strong bg-raised/20 text-center"
            >
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
                <Upload className="h-6 w-6" strokeWidth={1.5} />
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">Upload documents</h3>
              <p className="mx-auto mt-2 max-w-md text-sm text-muted">
                Drop PDFs, DOCX, CSV, or TXT files. We chunk, embed, and index them for retrieval
                once processing completes.
              </p>
              <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
                <Button icon={<Upload className="h-4 w-4" />}>Choose Files</Button>
                <Button variant="outline" icon={<Plus className="h-4 w-4" />}>
                  Create Knowledge Base
                </Button>
              </div>
            </Card>

            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-foreground">Your knowledge bases</h2>
              <p className="text-xs text-muted">
                {knowledgeBases.filter((kb) => kb.status === 'ready').length} ready to attach
              </p>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              {knowledgeBases.map((kb) => {
                const status = statusConfig[kb.status]
                const attachmentLabel =
                  kb.attachedTo.agents + kb.attachedTo.workflows === 0
                    ? 'Not attached'
                    : [
                        kb.attachedTo.agents > 0 ? `${kb.attachedTo.agents} agents` : null,
                        kb.attachedTo.workflows > 0 ? `${kb.attachedTo.workflows} workflows` : null,
                      ]
                        .filter(Boolean)
                        .join(' · ')

                return (
                  <Card key={kb.id} hover padding="lg">
                    <div className="flex items-start gap-4">
                      <div
                        className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-raised ${
                          kb.status === 'ready'
                            ? 'text-success'
                            : kb.status === 'processing'
                              ? 'text-accent'
                              : 'text-warning'
                        }`}
                      >
                        <FileStack className="h-6 w-6" strokeWidth={1.5} />
                      </div>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <div>
                            <h3 className="text-base font-semibold text-foreground">{kb.name}</h3>
                            <p className="mt-1 text-sm leading-relaxed text-muted">{kb.description}</p>
                          </div>
                          <Badge variant={status.variant} dot={kb.status === 'processing'}>
                            {status.label}
                          </Badge>
                        </div>

                        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
                          <span className="inline-flex items-center gap-1.5">
                            <Paperclip className="h-3.5 w-3.5" />
                            {kb.fileCount} files
                          </span>
                          <span>{attachmentLabel}</span>
                          <span>Updated {kb.updatedAt}</span>
                        </div>

                        <div className="mt-4 flex flex-wrap gap-2">
                          {kb.status === 'ready' ? (
                            <>
                              <Button size="sm">Attach to Agent</Button>
                              <Button variant="outline" size="sm">
                                Attach to Workflow
                              </Button>
                            </>
                          ) : kb.status === 'processing' ? (
                            <Button variant="outline" size="sm" disabled>
                              Available after ingestion
                            </Button>
                          ) : (
                            <Button variant="secondary" size="sm">
                              Retry Ingestion
                            </Button>
                          )}
                          <Button variant="ghost" size="sm">
                            Manage Files
                          </Button>
                        </div>
                      </div>
                    </div>
                  </Card>
                )
              })}
            </div>
          </div>
        </div>

        {showEventsPanel ? (
          <aside className="hidden w-80 shrink-0 border-l border-border bg-surface/80 p-5 backdrop-blur-xl xl:block">
            <div className="flex items-center gap-2">
              <Loader2 className="h-4 w-4 animate-spin text-accent" strokeWidth={1.75} />
              <h3 className="text-sm font-semibold text-foreground">Ingestion Events</h3>
            </div>
            <p className="mt-1 text-xs text-muted">Live RAG pipeline for Q3 Sales Reports</p>

            <div className="mt-5 space-y-2">
              {activeEvents.map((event) => (
                <div
                  key={event.id}
                  className="rounded-xl border border-border bg-raised/50 px-3 py-2.5"
                >
                  <div className="flex items-center gap-2">
                    {event.status === 'done' ? (
                      <CheckCircle2 className="h-3.5 w-3.5 text-success" strokeWidth={1.75} />
                    ) : event.status === 'error' ? (
                      <AlertCircle className="h-3.5 w-3.5 text-warning" strokeWidth={1.75} />
                    ) : (
                      <Loader2 className="h-3.5 w-3.5 animate-spin text-accent" strokeWidth={1.75} />
                    )}
                    <span className="text-xs font-semibold text-foreground">{event.message}</span>
                    <Badge
                      variant={
                        event.status === 'done'
                          ? 'success'
                          : event.status === 'error'
                            ? 'warning'
                            : 'accent'
                      }
                      dot={event.status === 'active'}
                    >
                      {event.status}
                    </Badge>
                  </div>
                  {event.detail ? (
                    <p className="mt-1 pl-5 text-xs text-muted">{event.detail}</p>
                  ) : null}
                  <p className="mt-1 pl-5 text-[10px] text-subtle">{event.time}</p>
                </div>
              ))}
            </div>

            <p className="mt-5 rounded-xl border border-border bg-raised/30 px-3 py-2.5 text-xs leading-relaxed text-muted">
              Knowledge bases become attachable only after status is{' '}
              <span className="font-semibold text-success">Ready</span>. Agents and workflows can
              reference them for retrieval during runs.
            </p>
          </aside>
        ) : null}
      </div>
    </PageShell>
  )
}

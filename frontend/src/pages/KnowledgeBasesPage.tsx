import { useState } from 'react'
import { FileStack, Paperclip, Plus, Settings2 } from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { Spinner } from '../components/ui/Spinner'
import { FileDropzone } from '../components/knowledge/FileDropzone'
import { CreateKnowledgeBaseDialog } from '../components/knowledge/CreateKnowledgeBaseDialog'
import { KnowledgeBaseDetailDialog } from '../components/knowledge/KnowledgeBaseDetailDialog'
import {
  MAX_FILES_PER_KB,
  useKnowledgeBases,
  type KnowledgeBase,
  type KnowledgeBaseStatus,
} from '../lib/knowledgeBases'

const statusConfig: Record<
  KnowledgeBaseStatus,
  { variant: 'success' | 'accent' | 'warning'; label: string }
> = {
  ready: { variant: 'success', label: 'Ready' },
  processing: { variant: 'accent', label: 'Processing' },
  failed: { variant: 'warning', label: 'Failed' },
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return 'just now'
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (seconds < 60) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days}d ago`
  return new Date(iso).toLocaleDateString()
}

function KnowledgeBasesSkeleton() {
  return (
    <PageShell className="!py-0">
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-border px-6 py-5 lg:px-8">
            <div className="space-y-3">
              <Skeleton className="h-5 w-20 rounded-full" />
              <Skeleton className="h-8 w-48" />
              <Skeleton className="h-4 w-96 max-w-full" />
            </div>
          </div>
          <div className="flex-1 px-6 py-6 lg:px-8">
            <Skeleton className="mb-6 h-40 w-full rounded-2xl" />
            <div className="grid gap-4 lg:grid-cols-2">
              {Array.from({ length: 4 }).map((_, index) => (
                <Skeleton key={index} className="h-40 w-full rounded-2xl" />
              ))}
            </div>
          </div>
        </div>
      </div>
    </PageShell>
  )
}

export function KnowledgeBasesPage() {
  const { data, isPending, refetch } = useKnowledgeBases()
  const [createOpen, setCreateOpen] = useState(false)
  const [createTab, setCreateTab] = useState<'write' | 'upload'>('write')
  const [createFiles, setCreateFiles] = useState<File[] | undefined>(undefined)
  const [detailId, setDetailId] = useState<string | null>(null)

  const knowledgeBases = data ?? []
  const processing = knowledgeBases.filter((kb) => kb.status === 'processing')
  const totalFiles = knowledgeBases.reduce((sum, kb) => sum + kb.fileCount, 0)

  const openCreate = (tab: 'write' | 'upload', files?: File[]) => {
    setCreateTab(tab)
    setCreateFiles(files)
    setCreateOpen(true)
  }

  if (isPending) return <KnowledgeBasesSkeleton />

  return (
    <PageShell className="!py-0">
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <div className="border-b border-border px-6 py-5 lg:px-8">
            <PageHeader
              title="Knowledge"
              description="Write knowledge or upload documents for RAG. Attach ready knowledge bases to agents only."
              badge="Agents"
              action={{
                label: 'New Knowledge Base',
                icon: <Plus className="h-4 w-4" />,
                onClick: () => openCreate('write'),
              }}
            />
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-6 scrollbar-thin lg:px-8">
            <div className="mb-6">
              <FileDropzone
                remaining={MAX_FILES_PER_KB}
                onFiles={(files) => openCreate('upload', files)}
              />
              <p className="mt-2 text-center text-xs text-muted">
                Prefer to type?{' '}
                <button
                  type="button"
                  onClick={() => openCreate('write')}
                  className="font-semibold text-accent hover:text-accent-hover"
                >
                  Write knowledge directly
                </button>
                .
              </p>
            </div>

            <div className="mb-4 flex items-center justify-between gap-3">
              <h2 className="text-sm font-semibold text-foreground">
                Your knowledge bases
              </h2>
              <p className="text-xs text-muted">
                {knowledgeBases.length} total · {totalFiles} files
              </p>
            </div>

            {knowledgeBases.length === 0 ? (
              <Card padding="lg" className="text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
                  <FileStack className="h-6 w-6" strokeWidth={1.5} />
                </div>
                <h3 className="mt-4 text-base font-semibold text-foreground">
                  No knowledge bases yet
                </h3>
                <p className="mx-auto mt-2 max-w-md text-sm text-muted">
                  Create your first knowledge base with the{' '}
                  <span className="font-semibold text-foreground">
                    New Knowledge Base
                  </span>{' '}
                  button above — write a note or upload documents.
                </p>
              </Card>
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                {knowledgeBases.map((kb: KnowledgeBase) => {
                  const status = statusConfig[kb.status] ?? statusConfig.ready
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
                            <div className="min-w-0">
                              <h3 className="truncate text-base font-semibold text-foreground">
                                {kb.name}
                              </h3>
                              <p className="mt-1 line-clamp-2 text-sm leading-relaxed text-muted">
                                {kb.description || 'No description'}
                              </p>
                            </div>
                            <Badge
                              variant={status.variant}
                              dot={kb.status === 'processing'}
                            >
                              {status.label}
                            </Badge>
                          </div>

                          <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted">
                            <span className="inline-flex items-center gap-1.5">
                              <Paperclip className="h-3.5 w-3.5" />
                              {kb.fileCount} / {MAX_FILES_PER_KB} files
                            </span>
                            <span>Updated {formatRelative(kb.updatedAt)}</span>
                          </div>

                          <div className="mt-4 flex flex-wrap gap-2">
                            <Button
                              variant="outline"
                              size="sm"
                              icon={<Settings2 className="h-3.5 w-3.5" />}
                              onClick={() => setDetailId(kb.id)}
                            >
                              Manage files
                            </Button>
                          </div>
                        </div>
                      </div>
                    </Card>
                  )
                })}
              </div>
            )}
          </div>
        </div>

        {processing.length > 0 ? (
          <aside className="hidden w-80 shrink-0 border-l border-border bg-surface/80 p-5 backdrop-blur-xl xl:block">
            <div className="flex items-center gap-2">
              <Spinner size="xs" />
              <h3 className="text-sm font-semibold text-foreground">
                Ingestion Events
              </h3>
            </div>
            <p className="mt-1 text-xs text-muted">
              Live RAG pipeline for processing knowledge bases
            </p>

            <div className="mt-5 space-y-2">
              {processing.map((kb) => (
                <div
                  key={kb.id}
                  className="rounded-xl border border-border bg-raised/50 px-3 py-2.5"
                >
                  <div className="flex items-center gap-2">
                    <Spinner size="xs" />
                    <span className="text-xs font-semibold text-foreground">
                      {kb.name}
                    </span>
                    <Badge variant="accent" dot>
                      processing
                    </Badge>
                  </div>
                  <p className="mt-1 pl-5 text-xs text-muted">
                    {kb.fileCount} file{kb.fileCount === 1 ? '' : 's'} in the
                    pipeline
                  </p>
                </div>
              ))}
            </div>

            <p className="mt-5 rounded-xl border border-border bg-raised/30 px-3 py-2.5 text-xs leading-relaxed text-muted">
              Knowledge bases become attachable only after status is{' '}
              <span className="font-semibold text-success">Ready</span>. Agents
              can reference them for retrieval during runs.
            </p>
          </aside>
        ) : null}
      </div>

      <CreateKnowledgeBaseDialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) setCreateFiles(undefined)
        }}
        initialTab={createTab}
        initialFiles={createFiles}
        onCreated={refetch}
      />

      <KnowledgeBaseDetailDialog
        open={detailId !== null}
        onOpenChange={(open) => {
          if (!open) setDetailId(null)
        }}
        knowledgeBaseId={detailId}
        onChanged={refetch}
      />
    </PageShell>
  )
}

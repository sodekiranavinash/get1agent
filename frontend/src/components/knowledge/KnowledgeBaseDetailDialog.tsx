import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, AlertTriangle, FileText, Loader2, Scissors, Trash2 } from 'lucide-react'
import { Dialog } from '../ui/Dialog'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { ConfirmDialog } from '../ui/ConfirmDialog'
import { Segmented } from '../ui/Segmented'
import { Spinner } from '../ui/Spinner'
import { ApiError, useApiClient } from '../../lib/api'
import {
  CHUNK_OVERLAPS,
  CHUNK_SIZES,
  deleteDocument,
  deleteKnowledgeBase,
  fetchKnowledgeBase,
  formatBytes,
  invalidateKnowledgeBases,
  type KnowledgeBaseDetail,
  type KnowledgeBaseDocument,
} from '../../lib/knowledgeBases'

type KnowledgeBaseDetailDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  knowledgeBaseId: string | null
  onChanged?: () => void
}

const statusVariant: Record<
  string,
  'default' | 'accent' | 'success' | 'warning' | 'info'
> = {
  ready: 'success',
  uploaded: 'info',
  processing: 'accent',
  pending: 'default',
  failed: 'warning',
}

function ConfigLabel({ children }: { children: string }) {
  return (
    <span className="mb-1.5 block text-[11px] font-medium text-muted">
      {children}
    </span>
  )
}

export function KnowledgeBaseDetailDialog({
  open,
  onOpenChange,
  knowledgeBaseId,
  onChanged,
}: KnowledgeBaseDetailDialogProps) {
  const api = useApiClient()
  const [detail, setDetail] = useState<KnowledgeBaseDetail | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [busyId, setBusyId] = useState<string | null>(null)
  const [deletingKb, setDeletingKb] = useState(false)
  const [confirmingDelete, setConfirmingDelete] = useState(false)
  const [lastFile, setLastFile] = useState<{
    id: string
    name: string
  } | null>(null)

  const load = useCallback(async () => {
    if (!knowledgeBaseId) return
    setLoading(true)
    setError(null)
    try {
      setDetail(await fetchKnowledgeBase(api, knowledgeBaseId))
    } catch (loadError) {
      setError(
        loadError instanceof Error ? loadError.message : 'Failed to load files',
      )
    } finally {
      setLoading(false)
    }
  }, [api, knowledgeBaseId])

  useEffect(() => {
    if (open) {
      setDetail(null)
      setConfirmingDelete(false)
      setLastFile(null)
      void load()
    }
  }, [open, load])

  const removeDocument = async (documentId: string, alsoDeleteKb = false) => {
    if (!knowledgeBaseId) return
    setBusyId(documentId)
    try {
      await deleteDocument(api, knowledgeBaseId, documentId)
      if (alsoDeleteKb) {
        await deleteKnowledgeBase(api, knowledgeBaseId)
        invalidateKnowledgeBases()
        onChanged?.()
        onOpenChange(false)
        return
      }
      await load()
      invalidateKnowledgeBases()
      onChanged?.()
    } catch (deleteError) {
      setError(
        deleteError instanceof Error ? deleteError.message : 'Delete failed',
      )
    } finally {
      setBusyId(null)
    }
  }

  const requestRemoveDocument = (document: KnowledgeBaseDocument) => {
    if (detail && detail.documents.length <= 1) {
      setLastFile({ id: document.id, name: document.fileName })
      return
    }
    void removeDocument(document.id)
  }

  const removeKnowledgeBase = async () => {
    if (!knowledgeBaseId) return
    setDeletingKb(true)
    try {
      await deleteKnowledgeBase(api, knowledgeBaseId)
      invalidateKnowledgeBases()
      onChanged?.()
      onOpenChange(false)
    } catch (deleteError) {
      if (deleteError instanceof ApiError && deleteError.status === 404) {
        // Already gone — treat as deleted.
        invalidateKnowledgeBases()
        onChanged?.()
        onOpenChange(false)
        return
      }
      setError(
        deleteError instanceof Error
          ? deleteError.message
          : 'Could not delete knowledge base',
      )
    } finally {
      setDeletingKb(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="xl"
      title={detail?.knowledgeBase.name ?? 'Knowledge base'}
      description={detail?.knowledgeBase.description ?? 'Files in this knowledge base.'}
      footer={
        confirmingDelete ? (
          <>
            <p className="mr-auto text-sm text-muted">
              Delete this knowledge base and all its files?
            </p>
            <Button
              variant="ghost"
              onClick={() => setConfirmingDelete(false)}
              disabled={deletingKb}
            >
              Cancel
            </Button>
            <Button
              onClick={removeKnowledgeBase}
              disabled={deletingKb}
              variant="danger"
              icon={
                deletingKb ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <AlertTriangle className="h-4 w-4" />
                )
              }
            >
              {deletingKb ? 'Deleting…' : 'Delete'}
            </Button>
          </>
        ) : (
          <>
            <Button
              variant="danger"
              onClick={() => setConfirmingDelete(true)}
              disabled={loading}
              icon={<Trash2 className="h-4 w-4" />}
              className="mr-auto"
            >
              Delete knowledge base
            </Button>
            <Button variant="ghost" onClick={() => onOpenChange(false)}>
              Close
            </Button>
          </>
        )
      }
    >
      {error ? (
        <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <p className="text-sm text-foreground">{error}</p>
        </div>
      ) : null}

      {detail ? (
        <div className="mb-4 rounded-xl border border-border bg-raised/30 p-3">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-subtle">
            <Scissors className="h-3.5 w-3.5" />
            Chunking
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <ConfigLabel>Chunk size (tokens)</ConfigLabel>
              <Segmented
                options={CHUNK_SIZES}
                value={detail.knowledgeBase.chunkSize}
                disabled
                size="sm"
              />
            </div>
            <div>
              <ConfigLabel>Chunk overlap (tokens)</ConfigLabel>
              <Segmented
                options={CHUNK_OVERLAPS}
                value={detail.knowledgeBase.chunkOverlap}
                disabled
                size="sm"
              />
            </div>
          </div>
          <p className="mt-2 text-[11px] text-subtle">
            Fixed at creation — every file in this knowledge base uses the same
            chunking.
          </p>
        </div>
      ) : null}

      {loading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" label="Loading files…" />
        </div>
      ) : detail && detail.documents.length > 0 ? (
        <ul className="space-y-2">
          {detail.documents.map((document) => (
            <li
              key={document.id}
              className="rounded-xl border border-border bg-raised/40 p-3.5"
            >
              <div className="flex items-start gap-3">
                <FileText className="mt-0.5 h-4 w-4 shrink-0 text-accent" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium text-foreground">
                      {document.fileName}
                    </p>
                    <Badge variant={statusVariant[document.status] ?? 'default'}>
                      {document.status}
                    </Badge>
                    <Badge variant="default">{document.source}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-subtle">
                    {formatBytes(document.sizeBytes)} · {document.tags.length} tag
                    {document.tags.length === 1 ? '' : 's'}
                  </p>
                  {document.tags.length > 0 ? (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {document.tags.map((tag) => (
                        <span
                          key={tag.name}
                          title={tag.description}
                          className="rounded-full border border-border bg-canvas px-2 py-0.5 text-[11px] text-muted"
                        >
                          {tag.name}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
                <button
                  type="button"
                  onClick={() => requestRemoveDocument(document)}
                  disabled={busyId === document.id}
                  aria-label={`Delete ${document.fileName}`}
                  className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning disabled:opacity-40"
                >
                  {busyId === document.id ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                </button>
              </div>
            </li>
          ))}
        </ul>
      ) : (
        <p className="py-10 text-center text-sm text-muted">
          No files in this knowledge base yet.
        </p>
      )}

      <ConfirmDialog
        open={lastFile !== null}
        onOpenChange={(next) => {
          if (!next) setLastFile(null)
        }}
        title="Delete last file?"
        description="This knowledge base will have no files left, so it will be deleted too."
        confirmLabel="Delete file & knowledge base"
        destructive
        loading={busyId === lastFile?.id}
        onConfirm={async () => {
          if (!lastFile) return
          await removeDocument(lastFile.id, true)
          setLastFile(null)
        }}
      >
        <p className="text-sm text-muted">
          <span className="font-semibold text-foreground">
            {lastFile?.name}
          </span>{' '}
          is the only file in this knowledge base. Deleting it will also delete
          the knowledge base. This cannot be undone.
        </p>
      </ConfirmDialog>
    </Dialog>
  )
}

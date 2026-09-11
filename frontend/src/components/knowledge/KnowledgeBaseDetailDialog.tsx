import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, FileText, Loader2, Trash2 } from 'lucide-react'
import { Dialog } from '../ui/Dialog'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { Spinner } from '../ui/Spinner'
import { useApiClient } from '../../lib/api'
import {
  deleteDocument,
  deleteKnowledgeBase,
  fetchKnowledgeBase,
  formatBytes,
  invalidateKnowledgeBases,
  type KnowledgeBaseDetail,
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
      void load()
    }
  }, [open, load])

  const removeDocument = async (documentId: string) => {
    if (!knowledgeBaseId) return
    setBusyId(documentId)
    try {
      await deleteDocument(api, knowledgeBaseId, documentId)
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

  const removeKnowledgeBase = async () => {
    if (!knowledgeBaseId) return
    setDeletingKb(true)
    try {
      await deleteKnowledgeBase(api, knowledgeBaseId)
      invalidateKnowledgeBases()
      onChanged?.()
      onOpenChange(false)
    } catch (deleteError) {
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
      size="lg"
      title={detail?.knowledgeBase.name ?? 'Knowledge base'}
      description={detail?.knowledgeBase.description ?? 'Files in this knowledge base.'}
      footer={
        <>
          <Button
            variant="secondary"
            onClick={removeKnowledgeBase}
            disabled={deletingKb || loading}
            icon={
              deletingKb ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )
            }
            className="mr-auto text-warning"
          >
            Delete knowledge base
          </Button>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </>
      }
    >
      {error ? (
        <div className="mb-4 flex items-start gap-2.5 rounded-xl border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <p className="text-sm text-foreground">{error}</p>
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
                  onClick={() => removeDocument(document.id)}
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
    </Dialog>
  )
}

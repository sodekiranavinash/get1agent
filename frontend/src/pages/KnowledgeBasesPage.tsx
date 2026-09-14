import { useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  Boxes,
  Clock,
  FileStack,
  HardDrive,
  Image as ImageIcon,
  Layers,
  Lock,
  Paperclip,
  Plus,
  Scissors,
  Settings2,
  Trash2,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { FileDropzone } from '../components/knowledge/FileDropzone'
import { CreateKnowledgeBaseDialog } from '../components/knowledge/CreateKnowledgeBaseDialog'
import { KnowledgeBaseDetailDialog } from '../components/knowledge/KnowledgeBaseDetailDialog'
import { IngestionActivity } from '../components/knowledge/IngestionActivity'
import { useAdaptivePoll } from '../hooks/useAdaptivePoll'
import { fadeUp, stagger } from '../lib/motion'
import { ApiError, useApiClient } from '../lib/api'
import {
  MAX_FILES_PER_KB,
  MAX_FILES_PER_USER,
  MAX_KNOWLEDGE_BASES,
  MAX_STORAGE_BYTES,
  DEFAULT_CHUNK_OVERLAP,
  DEFAULT_CHUNK_SIZE,
  EMBEDDING_DIM,
  IMAGE_EMBED_MODEL,
  TEXT_EMBED_MODEL,
  deleteKnowledgeBase,
  formatBytes,
  formatRelative,
  invalidateKnowledgeBases,
  removeIngestionEvents,
  useIngestionEvents,
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

function UsageStat({
  icon: Icon,
  label,
  value,
  sub,
  percent,
  tone,
  bar,
}: {
  icon: LucideIcon
  label: string
  value: string
  sub: string
  percent: number
  tone: string
  bar: string
}) {
  const width = Math.min(100, Math.max(0, percent))
  return (
    <div className="rounded-lg border border-border bg-surface p-3.5">
      <div className="flex items-center gap-2.5">
        <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-raised ${tone}`}>
          <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs text-muted">{label}</p>
          <p className="truncate text-[13px] font-semibold text-foreground">{value}</p>
        </div>
        <span className="text-[11px] font-medium tabular-nums text-subtle">
          {Math.round(percent)}%
        </span>
      </div>
      <div className="mt-2.5 h-1 w-full overflow-hidden rounded-full bg-raised">
        <div className={`h-full rounded-full ${bar}`} style={{ width: `${width}%` }} />
      </div>
      <p className="mt-1 truncate text-[10px] text-subtle">{sub}</p>
    </div>
  )
}

function KnowledgeBaseRow({
  kb,
  filesPerKb,
  onManage,
  onDelete,
}: {
  kb: KnowledgeBase
  filesPerKb: number
  onManage: () => void
  onDelete: () => void
}) {
  const status = statusConfig[kb.status] ?? statusConfig.ready
  const pct =
    filesPerKb > 0 ? Math.min(100, Math.round((kb.fileCount / filesPerKb) * 100)) : 0
  const tone =
    kb.status === 'ready'
      ? 'text-success'
      : kb.status === 'processing'
        ? 'text-accent'
        : 'text-warning'

  return (
    <motion.div
      variants={fadeUp}
      className="flex items-center gap-3 px-4 py-2.5 transition-colors hover:bg-raised/40"
    >
      <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-raised ${tone}`}>
        <FileStack className="h-3.5 w-3.5" strokeWidth={1.75} />
      </span>

      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h3 className="truncate text-[13px] font-medium text-foreground">{kb.name}</h3>
          <Badge variant={status.variant} dot={kb.status === 'processing'}>
            {status.label}
          </Badge>
        </div>
        <p className="mt-0.5 truncate text-xs text-muted">
          {kb.description || 'No description'}
        </p>
      </div>

      <div className="hidden shrink-0 items-center gap-4 text-[11px] text-muted lg:flex">
        <span className="inline-flex items-center gap-1.5">
          <Paperclip className="h-3.5 w-3.5" />
          {kb.fileCount}/{filesPerKb}
        </span>
        <span className="inline-flex items-center gap-1 text-subtle">
          <Clock className="h-3 w-3" />
          {formatRelative(kb.updatedAt)}
        </span>
        <span className="w-8 text-right tabular-nums text-subtle">{pct}%</span>
      </div>

      <div className="flex shrink-0 items-center gap-1">
        <Button
          variant="outline"
          size="sm"
          icon={<Settings2 className="h-3.5 w-3.5" />}
          onClick={onManage}
        >
          Manage
        </Button>
        <button
          type="button"
          onClick={onDelete}
          aria-label={`Delete ${kb.name}`}
          title={`Delete ${kb.name}`}
          className="rounded-md p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      </div>
    </motion.div>
  )
}

function KnowledgeBasesSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-5 w-40" />
        <Skeleton className="h-3.5 w-96 max-w-full" />
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, index) => (
          <Skeleton key={index} className="h-[86px] w-full rounded-lg" />
        ))}
      </div>
      <div className="mt-3 flex gap-3">
        <div className="min-w-0 flex-1 space-y-3">
          <Skeleton className="h-24 w-full rounded-lg" />
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-14 w-full rounded-lg" />
          ))}
        </div>
        <Skeleton className="hidden w-[340px] shrink-0 self-stretch rounded-lg xl:block" />
      </div>
    </PageShell>
  )
}

export function KnowledgeBasesPage() {
  const { data, isPending, error, refetch } = useKnowledgeBases()
  const { data: ingestionEvents, refetch: refetchEvents } = useIngestionEvents()
  const api = useApiClient()
  const [createOpen, setCreateOpen] = useState(false)
  const [createTab, setCreateTab] = useState<'write' | 'upload'>('write')
  const [createFiles, setCreateFiles] = useState<File[] | undefined>(undefined)
  const [detailId, setDetailId] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<KnowledgeBase | null>(null)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [activityOpen, setActivityOpen] = useState(true)

  const knowledgeBases = data?.knowledgeBases ?? []
  const usage = data?.usage
  const limits = usage?.limits
  const kbLimit = limits?.knowledgeBases ?? MAX_KNOWLEDGE_BASES
  const fileLimit = limits?.files ?? MAX_FILES_PER_USER
  const filesPerKb = limits?.filesPerKnowledgeBase ?? MAX_FILES_PER_KB
  const storageLimit = limits?.storageBytes ?? MAX_STORAGE_BYTES
  const usedKbs = usage?.knowledgeBases ?? knowledgeBases.length
  const usedFiles =
    usage?.files ?? knowledgeBases.reduce((sum, kb) => sum + kb.fileCount, 0)
  const usedStorage = usage?.storageBytes ?? 0
  const atKbLimit = usedKbs >= kbLimit
  const remainingUserFiles = Math.max(0, fileLimit - usedFiles)
  const maxFilesForNewKb = Math.max(0, Math.min(filesPerKb, remainingUserFiles))
  const processing = knowledgeBases.filter((kb) => kb.status === 'processing')
  const hasActiveIngestion = (ingestionEvents ?? []).some(
    (event) => event.documentStatus !== 'ready' && event.documentStatus !== 'failed',
  )

  const pollTick = useRef(0)
  const { cappedOut, reset: resetPoll } = useAdaptivePoll({
    enabled: activityOpen && (processing.length > 0 || hasActiveIngestion),
    resetKey: ingestionEvents?.[0]?.id,
    onPoll: () => {
      refetchEvents()
      pollTick.current += 1
      if (pollTick.current % 4 === 0) refetch()
    },
  })

  const refreshAll = () => {
    refetch()
    refetchEvents()
  }

  const refreshActivity = () => {
    resetPoll()
    refreshAll()
  }

  const openCreate = (tab: 'write' | 'upload', files?: File[]) => {
    setCreateTab(tab)
    setCreateFiles(files)
    setCreateOpen(true)
  }

  const openDelete = (kb: KnowledgeBase) => {
    setDeleteError(null)
    setDeleteTarget(kb)
  }

  const confirmDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteKnowledgeBase(api, deleteTarget.id)
      invalidateKnowledgeBases()
      removeIngestionEvents((event) => event.knowledgeBaseId === deleteTarget.id)
      if (detailId === deleteTarget.id) setDetailId(null)
      setDeleteTarget(null)
      refetch()
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        invalidateKnowledgeBases()
        removeIngestionEvents((event) => event.knowledgeBaseId === deleteTarget.id)
        if (detailId === deleteTarget.id) setDetailId(null)
        setDeleteTarget(null)
        refetch()
        return
      }
      setDeleteError(
        error instanceof Error ? error.message : 'Could not delete knowledge base',
      )
    } finally {
      setDeleting(false)
    }
  }

  if (isPending) return <KnowledgeBasesSkeleton />

  if (error) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState
            title="Couldn't load knowledge bases"
            error={error}
            onRetry={refreshAll}
          />
        </div>
      </PageShell>
    )
  }

  const kbPercent = kbLimit > 0 ? (usedKbs / kbLimit) * 100 : 0
  const filePercent = fileLimit > 0 ? (usedFiles / fileLimit) * 100 : 0
  const storagePercent = storageLimit > 0 ? (usedStorage / storageLimit) * 100 : 0

  return (
    <PageShell>
      <PageHeader
        title="Knowledge"
        description="Write knowledge or upload documents for RAG. Attach ready knowledge bases to agents."
        badge="Agents"
        secondaryAction={{
          label: 'Activity',
          icon: <Activity className="h-3.5 w-3.5" />,
          onClick: () => setActivityOpen((open) => !open),
          active: activityOpen,
        }}
        action={{
          label: 'Knowledge base',
          icon: <Plus className="h-3.5 w-3.5" />,
          onClick: () => openCreate('write'),
          disabled: atKbLimit,
        }}
      />

      <motion.div
        variants={stagger}
        initial="hidden"
        animate="show"
        className="grid gap-3 sm:grid-cols-3"
      >
        <motion.div variants={fadeUp}>
          <UsageStat
            icon={Layers}
            label="Knowledge bases"
            value={`${usedKbs}/${kbLimit}`}
            sub="created"
            percent={kbPercent}
            tone="text-accent"
            bar="bg-accent"
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <UsageStat
            icon={Paperclip}
            label="Documents"
            value={`${usedFiles}/${fileLimit}`}
            sub="files"
            percent={filePercent}
            tone="text-info"
            bar="bg-info"
          />
        </motion.div>
        <motion.div variants={fadeUp}>
          <UsageStat
            icon={HardDrive}
            label="Storage"
            value={formatBytes(usedStorage)}
            sub={`of ${formatBytes(storageLimit)}`}
            percent={storagePercent}
            tone="text-success"
            bar="bg-success"
          />
        </motion.div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, delay: 0.05 }}
        className="mt-3 flex gap-3"
      >
        <Card padding="none" className="min-w-0 flex-1 overflow-hidden">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-4 py-2.5">
            <h2 className="flex items-center gap-2 text-[13px] font-semibold text-foreground">
              <FileStack className="h-3.5 w-3.5 text-accent" />
              Knowledge bases
              <span className="rounded-md bg-raised px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-muted">
                {usedKbs}/{kbLimit}
              </span>
            </h2>
            <button
              type="button"
              onClick={() => openCreate('write')}
              disabled={atKbLimit}
              className="text-xs font-medium text-accent transition-colors hover:text-accent-hover disabled:opacity-50"
            >
              Write knowledge directly
            </button>
          </div>

          <div className="border-b border-border p-3">
            <FileDropzone
              remaining={maxFilesForNewKb}
              disabled={atKbLimit}
              onFiles={(files) => openCreate('upload', files)}
              compact
            />
          </div>

          {knowledgeBases.length > 0 ? (
            <motion.div
              variants={stagger}
              initial="hidden"
              animate="show"
              className="divide-y divide-border"
            >
              {knowledgeBases.map((kb) => (
                <KnowledgeBaseRow
                  key={kb.id}
                  kb={kb}
                  filesPerKb={filesPerKb}
                  onManage={() => setDetailId(kb.id)}
                  onDelete={() => openDelete(kb)}
                />
              ))}
            </motion.div>
          ) : (
            <p className="px-4 py-8 text-center text-[13px] text-muted">
              No knowledge bases yet. Create one to get started.
            </p>
          )}

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 border-t border-border px-4 py-2.5 text-[11px] text-muted">
            <span title={TEXT_EMBED_MODEL} className="inline-flex items-center gap-1.5">
              <Boxes className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
              Text · Titan Text V2 · {EMBEDDING_DIM}-d
            </span>
            <span title={IMAGE_EMBED_MODEL} className="inline-flex items-center gap-1.5">
              <ImageIcon className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
              Image · Titan Multimodal G1 · {EMBEDDING_DIM}-d
            </span>
            <span className="inline-flex items-center gap-1.5">
              <Scissors className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
              Chunk {DEFAULT_CHUNK_SIZE} · overlap {DEFAULT_CHUNK_OVERLAP}
            </span>
            <span className="ml-auto inline-flex items-center gap-1 text-subtle">
              <Lock className="h-3 w-3" />
              Per knowledge base
            </span>
          </div>
        </Card>

        <AnimatePresence initial={false}>
          {activityOpen ? (
            <motion.aside
              key="activity-panel"
              initial={{ width: 0, opacity: 0 }}
              animate={{ width: 340, opacity: 1 }}
              exit={{ width: 0, opacity: 0 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="relative hidden shrink-0 self-stretch overflow-hidden xl:block"
            >
              <div className="absolute inset-y-0 right-0 w-[340px]">
                <Card padding="none" className="flex h-full flex-col overflow-hidden">
                  <IngestionActivity
                    events={ingestionEvents ?? []}
                    capped={cappedOut}
                    onRefresh={refreshActivity}
                    onClose={() => setActivityOpen(false)}
                  />
                </Card>
              </div>
            </motion.aside>
          ) : null}
        </AnimatePresence>
      </motion.div>

      <AnimatePresence>
        {activityOpen ? (
          <motion.div
            key="activity-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setActivityOpen(false)}
            className="fixed inset-0 z-40 bg-canvas/60 xl:hidden"
          />
        ) : null}
      </AnimatePresence>
      <AnimatePresence>
        {activityOpen ? (
          <motion.aside
            key="activity-drawer"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 340, damping: 34 }}
            className="fixed inset-y-0 right-0 z-50 flex w-[360px] max-w-[92vw] flex-col border-l border-border bg-surface xl:hidden"
          >
            <IngestionActivity
              events={ingestionEvents ?? []}
              capped={cappedOut}
              onRefresh={refreshActivity}
              onClose={() => setActivityOpen(false)}
            />
          </motion.aside>
        ) : null}
      </AnimatePresence>

      <CreateKnowledgeBaseDialog
        open={createOpen}
        onOpenChange={(open) => {
          setCreateOpen(open)
          if (!open) setCreateFiles(undefined)
        }}
        initialTab={createTab}
        initialFiles={createFiles}
        maxFiles={maxFilesForNewKb}
        onCreated={refreshAll}
      />

      <KnowledgeBaseDetailDialog
        open={detailId !== null}
        onOpenChange={(open) => {
          if (!open) setDetailId(null)
        }}
        knowledgeBaseId={detailId}
        filesPerKb={filesPerKb}
        onChanged={refreshAll}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title={`Delete "${deleteTarget?.name ?? ''}"?`}
        description="This permanently deletes the knowledge base and all its files."
        confirmLabel="Delete"
        destructive
        loading={deleting}
        onConfirm={confirmDelete}
      >
        {deleteError ? (
          <p className="text-sm text-warning">{deleteError}</p>
        ) : (
          <p className="text-sm text-muted">
            {deleteTarget && deleteTarget.fileCount > 0
              ? `${deleteTarget.fileCount} file${deleteTarget.fileCount === 1 ? '' : 's'} will be deleted. This cannot be undone.`
              : 'This cannot be undone.'}
          </p>
        )}
      </ConfirmDialog>
    </PageShell>
  )
}

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

const toneStyles = {
  accent: { box: 'bg-accent-soft text-accent', bar: 'bg-accent' },
  info: { box: 'bg-info-soft text-info', bar: 'bg-info' },
  success: { box: 'bg-success-soft text-success', bar: 'bg-success' },
} as const

type Tone = keyof typeof toneStyles

function UsageStat({
  icon: Icon,
  label,
  value,
  sub,
  percent,
  tone,
  delay,
}: {
  icon: LucideIcon
  label: string
  value: string
  sub: string
  percent: number
  tone: Tone
  delay: number
}) {
  const t = toneStyles[tone]
  const width = Math.min(100, Math.max(0, percent))
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay, ease: [0.25, 0.46, 0.45, 0.94] }}
    >
      <div className="rounded-2xl border border-border bg-surface p-3.5 shadow-panel">
        <div className="flex items-center gap-2.5">
          <span
            className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-lg ${t.box}`}
          >
            <Icon className="h-4 w-4" strokeWidth={1.75} />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[11px] text-muted">{label}</p>
            <p className="truncate text-sm font-semibold text-foreground">
              {value}
            </p>
          </div>
          <span className="text-[11px] font-semibold tabular-nums text-subtle">
            {Math.round(percent)}%
          </span>
        </div>
        <div className="mt-2.5 h-1 w-full overflow-hidden rounded-full bg-raised">
          <motion.div
            className={`h-full rounded-full ${t.bar}`}
            initial={{ width: 0 }}
            animate={{ width: `${width}%` }}
            transition={{ duration: 0.5, delay: delay + 0.1, ease: 'easeOut' }}
          />
        </div>
        <p className="mt-1 truncate text-[10px] text-subtle">{sub}</p>
      </div>
    </motion.div>
  )
}

function KnowledgeBasesPanel({
  knowledgeBases,
  filesPerKb,
  count,
  limit,
  atLimit,
  remaining,
  disabled,
  onFiles,
  onWrite,
  onManage,
  onDelete,
}: {
  knowledgeBases: KnowledgeBase[]
  filesPerKb: number
  count: number
  limit: number
  atLimit: boolean
  remaining: number
  disabled: boolean
  onFiles: (files: File[]) => void
  onWrite: () => void
  onManage: (kb: KnowledgeBase) => void
  onDelete: (kb: KnowledgeBase) => void
}) {
  return (
    <Card padding="none" className="gradient-border relative overflow-hidden">
      <div className="p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
            <FileStack className="h-4 w-4 text-accent" />
            Knowledge bases
            <span className="rounded-full bg-raised px-2 py-0.5 text-[11px] font-semibold tabular-nums text-muted">
              {count}/{limit}
            </span>
          </h2>
          <div className="flex items-center gap-3">
            {atLimit ? (
              <span className="text-xs text-warning">
                Limit of {limit} reached
              </span>
            ) : null}
            <button
              type="button"
              onClick={onWrite}
              disabled={disabled}
              className="text-xs font-semibold text-accent transition-colors hover:text-accent-hover disabled:opacity-50"
            >
              Write knowledge directly
            </button>
          </div>
        </div>

        <div className="mt-3">
          <FileDropzone
            remaining={remaining}
            disabled={disabled}
            onFiles={onFiles}
          />
        </div>
      </div>

      <div className="border-t border-border">
        <div className="p-5">
          {knowledgeBases.length === 0 ? (
            <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border-strong bg-raised/20 px-6 py-10 text-center">
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
                <FileStack className="h-6 w-6" strokeWidth={1.5} />
              </div>
              <h3 className="mt-4 text-base font-semibold text-foreground">
                No knowledge bases yet
              </h3>
              <p className="mx-auto mt-2 max-w-md text-sm text-muted">
                Drop documents above, or use the{' '}
                <span className="font-semibold text-foreground">
                  Knowledge Base
                </span>{' '}
                button to get started.
              </p>
            </div>
          ) : (
            <div className="scrollbar-thin max-h-[292px] overflow-y-auto pr-1">
              <div className="flex flex-col gap-2.5">
                {knowledgeBases.map((kb, index) => (
                  <KnowledgeBaseRow
                    key={kb.id}
                    kb={kb}
                    filesPerKb={filesPerKb}
                    index={index}
                    onManage={() => onManage(kb)}
                    onDelete={() => onDelete(kb)}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-border px-5 py-3 text-[11px] text-muted">
        <span
          title={TEXT_EMBED_MODEL}
          className="inline-flex items-center gap-1.5"
        >
          <Boxes className="h-3.5 w-3.5 text-accent" strokeWidth={1.75} />
          Text · Titan Text V2 · {EMBEDDING_DIM}-d
        </span>
        <span
          title={IMAGE_EMBED_MODEL}
          className="inline-flex items-center gap-1.5"
        >
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
  )
}

function KnowledgeBaseRow({
  kb,
  filesPerKb,
  index,
  onManage,
  onDelete,
}: {
  kb: KnowledgeBase
  filesPerKb: number
  index: number
  onManage: () => void
  onDelete: () => void
}) {
  const status = statusConfig[kb.status] ?? statusConfig.ready
  const pct =
    filesPerKb > 0
      ? Math.min(100, Math.round((kb.fileCount / filesPerKb) * 100))
      : 0
  const tone =
    kb.status === 'ready'
      ? 'text-success'
      : kb.status === 'processing'
        ? 'text-accent'
        : 'text-warning'

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.3,
        delay: 0.04 + index * 0.03,
        ease: [0.25, 0.46, 0.45, 0.94],
      }}
    >
      <div className="group flex h-16 items-center gap-4 rounded-xl border border-border bg-raised/30 px-4 transition-colors hover:border-accent/20 hover:bg-raised/50">
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-raised ${tone}`}
        >
          <FileStack className="h-4 w-4" strokeWidth={1.5} />
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-foreground">
              {kb.name}
            </h3>
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
          <span className="w-9 text-right tabular-nums text-subtle">
            {pct}%
          </span>
        </div>

        <div className="flex shrink-0 items-center gap-1.5">
          <Button
            variant="outline"
            size="sm"
            icon={<Settings2 className="h-3.5 w-3.5" />}
            onClick={onManage}
          >
            Manage files
          </Button>
          <button
            type="button"
            onClick={onDelete}
            aria-label={`Delete ${kb.name}`}
            title={`Delete ${kb.name}`}
            className="rounded-lg p-2 text-subtle transition-colors hover:bg-raised hover:text-warning"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
    </motion.div>
  )
}

function KnowledgeBasesSkeleton() {
  return (
    <PageShell className="!py-0">
      <div className="pt-6 pb-10 lg:pt-8">
        <div className="mb-8 space-y-3">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-4 w-96 max-w-full" />
        </div>
        <div className="flex gap-6">
          <div className="min-w-0 flex-1 space-y-6">
            <div className="grid gap-3 sm:grid-cols-3">
              {Array.from({ length: 3 }).map((_, index) => (
                <Skeleton key={index} className="h-24 w-full rounded-2xl" />
              ))}
            </div>
            <div className="space-y-3">
              <Skeleton className="h-52 w-full rounded-2xl" />
              <Skeleton className="h-16 w-full rounded-xl" />
              <Skeleton className="h-16 w-full rounded-xl" />
            </div>
          </div>
          <Skeleton className="hidden w-[360px] shrink-0 self-stretch rounded-2xl xl:block" />
        </div>
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
    usage?.files ??
    knowledgeBases.reduce((sum, kb) => sum + kb.fileCount, 0)
  const usedStorage = usage?.storageBytes ?? 0
  const atKbLimit = usedKbs >= kbLimit
  const remainingUserFiles = Math.max(0, fileLimit - usedFiles)
  const maxFilesForNewKb = Math.max(0, Math.min(filesPerKb, remainingUserFiles))
  const processing = knowledgeBases.filter((kb) => kb.status === 'processing')
  // `documentStatus` is the document's current status, so any non-terminal
  // event means that file is still moving through the pipeline.
  const hasActiveIngestion = (ingestionEvents ?? []).some(
    (event) =>
      event.documentStatus !== 'ready' && event.documentStatus !== 'failed',
  )

  // Poll only while the activity panel is open and something is actually
  // moving. A closed panel costs nothing; a slow stage backs off; a stuck
  // document stops after the cap and offers a manual refresh.
  const pollTick = useRef(0)
  const { cappedOut, reset: resetPoll } = useAdaptivePoll({
    enabled: activityOpen && (processing.length > 0 || hasActiveIngestion),
    resetKey: ingestionEvents?.[0]?.id,
    onPoll: () => {
      refetchEvents()
      pollTick.current += 1
      // Knowledge-base status changes far less often than ingestion events.
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
      removeIngestionEvents(
        (event) => event.knowledgeBaseId === deleteTarget.id,
      )
      if (detailId === deleteTarget.id) setDetailId(null)
      setDeleteTarget(null)
      refetch()
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        invalidateKnowledgeBases()
        removeIngestionEvents(
          (event) => event.knowledgeBaseId === deleteTarget.id,
        )
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
      <PageShell className="!py-0">
        <div className="flex min-h-[60vh] items-center justify-center pt-6 pb-10 lg:pt-8">
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
  const storagePercent =
    storageLimit > 0 ? (usedStorage / storageLimit) * 100 : 0

  return (
    <PageShell className="!py-0">
      <div className="pt-6 pb-10 lg:pt-8">
        <PageHeader
          title="Knowledge"
          description="Write knowledge or upload documents for RAG. Attach ready knowledge bases to agents"
          secondaryAction={{
            label: 'Activity',
            icon: <Activity className="h-4 w-4" />,
            onClick: () => setActivityOpen((open) => !open),
            active: activityOpen,
          }}
          action={{
            label: 'Knowledge Base',
            icon: <Plus className="h-4 w-4" />,
            onClick: () => openCreate('write'),
            disabled: atKbLimit,
          }}
        />

        <div className="flex gap-6">
          <div className="min-w-0 flex-1 space-y-6">
            <div className="grid gap-3 sm:grid-cols-3">
              <UsageStat
                icon={Layers}
                label="Knowledge bases"
                value={`${usedKbs}/${kbLimit}`}
                sub="created"
                percent={kbPercent}
                tone="accent"
                delay={0}
              />
              <UsageStat
                icon={Paperclip}
                label="Documents"
                value={`${usedFiles}/${fileLimit}`}
                sub="files"
                percent={filePercent}
                tone="info"
                delay={0.05}
              />
              <UsageStat
                icon={HardDrive}
                label="Storage"
                value={formatBytes(usedStorage)}
                sub={`of ${formatBytes(storageLimit)}`}
                percent={storagePercent}
                tone="success"
                delay={0.1}
              />
            </div>

            <KnowledgeBasesPanel
              knowledgeBases={knowledgeBases}
              filesPerKb={filesPerKb}
              count={usedKbs}
              limit={kbLimit}
              atLimit={atKbLimit}
              remaining={maxFilesForNewKb}
              disabled={atKbLimit}
              onFiles={(files) => openCreate('upload', files)}
              onWrite={() => openCreate('write')}
              onManage={(kb) => setDetailId(kb.id)}
              onDelete={openDelete}
            />
          </div>

          <AnimatePresence initial={false}>
            {activityOpen ? (
              <motion.aside
                key="activity-panel"
                initial={{ width: 0, opacity: 0 }}
                animate={{ width: 360, opacity: 1 }}
                exit={{ width: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: [0.25, 0.46, 0.45, 0.94] }}
                className="relative hidden shrink-0 self-stretch overflow-hidden xl:block"
              >
                <div className="absolute inset-y-0 right-0 w-[360px]">
                  <Card
                    padding="none"
                    className="flex h-full flex-col overflow-hidden"
                  >
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
        </div>
      </div>

      <AnimatePresence>
        {activityOpen ? (
          <motion.div
            key="activity-backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={() => setActivityOpen(false)}
            className="fixed inset-0 z-40 bg-canvas/60 backdrop-blur-sm xl:hidden"
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
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
            className="fixed inset-y-0 right-0 z-50 flex w-[380px] max-w-[92vw] flex-col border-l border-border bg-surface/95 shadow-panel backdrop-blur-xl xl:hidden"
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

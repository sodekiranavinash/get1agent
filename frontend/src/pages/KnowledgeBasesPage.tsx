import { Fragment, useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  ArrowRight,
  Boxes,
  Clock,
  Database,
  FileSearch,
  FileStack,
  HardDrive,
  Layers,
  Paperclip,
  Plus,
  Scissors,
  Settings2,
  Sparkles,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { Badge } from '../components/ui/Badge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ConfirmDialog } from '../components/ui/ConfirmDialog'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { FileDropzone } from '../components/knowledge/FileDropzone'
import { CreateKnowledgeBaseDialog } from '../components/knowledge/CreateKnowledgeBaseDialog'
import { KnowledgeBaseDetailDialog } from '../components/knowledge/KnowledgeBaseDetailDialog'
import { IngestionActivity } from '../components/knowledge/IngestionActivity'
import { RagSettings } from '../components/knowledge/RagSettings'
import { ApiError, useApiClient } from '../lib/api'
import {
  MAX_FILES_PER_KB,
  MAX_FILES_PER_USER,
  MAX_KNOWLEDGE_BASES,
  MAX_STORAGE_BYTES,
  deleteKnowledgeBase,
  formatBytes,
  formatRelative,
  invalidateKnowledgeBases,
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

const PIPELINE_STEPS: { label: string; icon: LucideIcon }[] = [
  { label: 'Upload', icon: UploadCloud },
  { label: 'Parse', icon: FileSearch },
  { label: 'Chunk', icon: Scissors },
  { label: 'Embed', icon: Boxes },
  { label: 'Index', icon: Database },
]

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

function UploadPanel({
  remaining,
  disabled,
  onFiles,
  onWrite,
}: {
  remaining: number
  disabled: boolean
  onFiles: (files: File[]) => void
  onWrite: () => void
}) {
  return (
    <Card
      padding="none"
      className="gradient-border relative flex h-full flex-col overflow-hidden"
    >
      <div
        className="pointer-events-none absolute -right-12 -top-12 h-44 w-44 rounded-full bg-accent-soft blur-3xl"
        aria-hidden="true"
      />
      <div className="relative flex h-full flex-col p-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="max-w-lg">
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Sparkles className="h-4 w-4 text-accent" />
              Add documents
            </h2>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              Drop files to build a new knowledge base. We parse, chunk, embed,
              and index everything automatically.
            </p>
          </div>
          <button
            type="button"
            onClick={onWrite}
            disabled={disabled}
            className="text-xs font-semibold text-accent transition-colors hover:text-accent-hover disabled:opacity-50"
          >
            Write knowledge directly
          </button>
        </div>

        <div className="mt-4 flex-1">
          <FileDropzone
            remaining={remaining}
            disabled={disabled}
            onFiles={onFiles}
            className="h-full"
          />
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-1.5">
          {PIPELINE_STEPS.map((step, index) => (
            <Fragment key={step.label}>
              {index > 0 ? (
                <ArrowRight className="h-3 w-3 text-subtle" />
              ) : null}
              <span className="inline-flex items-center gap-1.5 rounded-full border border-border bg-raised/60 px-2.5 py-1 text-[11px] font-medium text-muted">
                <step.icon className="h-3 w-3 text-accent" strokeWidth={1.75} />
                {step.label}
              </span>
            </Fragment>
          ))}
        </div>
      </div>
    </Card>
  )
}

type SectionTab = 'bases' | 'upload'

function SectionTabs({
  value,
  onChange,
  count,
  limit,
}: {
  value: SectionTab
  onChange: (value: SectionTab) => void
  count: number
  limit: number
}) {
  const tabs: {
    key: SectionTab
    label: string
    icon: LucideIcon
    badge?: string
  }[] = [
    {
      key: 'bases',
      label: 'Knowledge bases',
      icon: FileStack,
      badge: `${count}/${limit}`,
    },
    { key: 'upload', label: 'Add documents', icon: UploadCloud },
  ]

  return (
    <div className="inline-flex items-center gap-1 rounded-2xl border border-border bg-raised/60 p-1">
      {tabs.map((item) => {
        const active = value === item.key
        return (
          <button
            key={item.key}
            type="button"
            onClick={() => onChange(item.key)}
            className={`relative inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
              active ? 'text-foreground' : 'text-muted hover:text-foreground'
            }`}
          >
            {active ? (
              <motion.span
                layoutId="kb-section-tab"
                className="absolute inset-0 rounded-xl border border-border bg-surface shadow-panel"
                transition={{ type: 'spring', stiffness: 400, damping: 32 }}
              />
            ) : null}
            <item.icon className="relative z-10 h-4 w-4" strokeWidth={1.75} />
            <span className="relative z-10">{item.label}</span>
            {item.badge ? (
              <span className="relative z-10 rounded-full bg-raised px-2 py-0.5 text-[11px] font-semibold tabular-nums text-muted">
                {item.badge}
              </span>
            ) : null}
          </button>
        )
      })}
    </div>
  )
}

function KnowledgeBaseCard({
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
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{
        duration: 0.35,
        delay: 0.05 + index * 0.04,
        ease: [0.25, 0.46, 0.45, 0.94],
      }}
      className="h-full"
    >
      <Card hover className="group flex h-full flex-col">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <div
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-raised ${tone}`}
            >
              <FileStack className="h-5 w-5" strokeWidth={1.5} />
            </div>
            <div className="min-w-0">
              <h3 className="truncate text-sm font-semibold text-foreground">
                {kb.name}
              </h3>
              <p className="mt-0.5 inline-flex items-center gap-1 text-[11px] text-subtle">
                <Clock className="h-3 w-3" />
                {formatRelative(kb.updatedAt)}
              </p>
            </div>
          </div>
          <Badge variant={status.variant} dot={kb.status === 'processing'}>
            {status.label}
          </Badge>
        </div>

        <p className="mt-3 line-clamp-2 min-h-[2.25rem] text-xs leading-relaxed text-muted">
          {kb.description || 'No description'}
        </p>

        <div className="mt-4 flex items-center justify-between text-[11px] text-muted">
          <span className="inline-flex items-center gap-1.5">
            <Paperclip className="h-3.5 w-3.5" />
            {kb.fileCount}/{filesPerKb} files
          </span>
          <span className="tabular-nums">{pct}%</span>
        </div>
        <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-raised">
          <div
            className={`h-full rounded-full ${
              kb.status === 'failed' ? 'bg-warning' : 'bg-accent'
            }`}
            style={{ width: `${pct}%` }}
          />
        </div>

        <div className="mt-4 flex items-center gap-2 border-t border-border pt-4">
          <Button
            variant="outline"
            size="sm"
            icon={<Settings2 className="h-3.5 w-3.5" />}
            onClick={onManage}
            className="flex-1"
          >
            Manage
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
      </Card>
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
            <Skeleton className="h-44 w-full rounded-2xl" />
            <div>
              <Skeleton className="mb-4 h-11 w-72 rounded-2xl" />
              <Skeleton className="h-[400px] w-full rounded-2xl" />
            </div>
          </div>
          <Skeleton className="hidden w-[360px] shrink-0 self-stretch rounded-2xl xl:block" />
        </div>
      </div>
    </PageShell>
  )
}

export function KnowledgeBasesPage() {
  const { data, isPending, refetch } = useKnowledgeBases()
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
  const [tab, setTab] = useState<SectionTab>('bases')

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

  useEffect(() => {
    if (processing.length === 0) return
    const id = window.setInterval(() => {
      refetch()
      refetchEvents()
    }, 4000)
    return () => window.clearInterval(id)
  }, [processing.length, refetch, refetchEvents])

  const refreshAll = () => {
    refetch()
    refetchEvents()
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
      if (detailId === deleteTarget.id) setDetailId(null)
      setDeleteTarget(null)
      refetch()
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        invalidateKnowledgeBases()
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

            <div>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <SectionTabs
                  value={tab}
                  onChange={setTab}
                  count={usedKbs}
                  limit={kbLimit}
                />
                {atKbLimit ? (
                  <span className="text-xs text-warning">
                    Limit of {kbLimit} reached
                  </span>
                ) : null}
              </div>

              <div className="lg:h-[400px]">
                <AnimatePresence mode="wait" initial={false}>
                  {tab === 'bases' ? (
                    <motion.div
                      key="bases"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.2 }}
                      className="h-full"
                    >
                      {knowledgeBases.length === 0 ? (
                        <div className="flex h-full flex-col items-center justify-center rounded-2xl border border-dashed border-border-strong bg-raised/20 px-6 py-12 text-center">
                          <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">
                            <FileStack className="h-6 w-6" strokeWidth={1.5} />
                          </div>
                          <h3 className="mt-4 text-base font-semibold text-foreground">
                            No knowledge bases yet
                          </h3>
                          <p className="mx-auto mt-2 max-w-md text-sm text-muted">
                            Switch to the{' '}
                            <span className="font-semibold text-foreground">
                              Add documents
                            </span>{' '}
                            tab, or use the{' '}
                            <span className="font-semibold text-foreground">
                              Knowledge Base
                            </span>{' '}
                            button above to get started.
                          </p>
                        </div>
                      ) : (
                        <div className="scrollbar-thin h-full overflow-y-auto pr-1">
                          <div className="grid grid-cols-[repeat(auto-fill,minmax(260px,1fr))] gap-4">
                            {knowledgeBases.map((kb, index) => (
                              <KnowledgeBaseCard
                                key={kb.id}
                                kb={kb}
                                filesPerKb={filesPerKb}
                                index={index}
                                onManage={() => setDetailId(kb.id)}
                                onDelete={() => openDelete(kb)}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </motion.div>
                  ) : (
                    <motion.div
                      key="upload"
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0, y: -8 }}
                      transition={{ duration: 0.2 }}
                      className="h-full"
                    >
                      <UploadPanel
                        remaining={maxFilesForNewKb}
                        disabled={atKbLimit}
                        onFiles={(files) => openCreate('upload', files)}
                        onWrite={() => openCreate('write')}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>
            </div>

            <RagSettings />
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

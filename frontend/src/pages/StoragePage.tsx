import { useCallback, useMemo, useState } from 'react'
import { useDropzone } from 'react-dropzone'
import { motion } from 'framer-motion'
import {
  AlertTriangle,
  File as FileIcon,
  HardDrive,
  Loader2,
  Trash2,
  UploadCloud,
} from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { ErrorState } from '../components/ui/ErrorState'
import { PageHeader } from '../components/ui/PageHeader'
import { PageShell } from '../components/ui/PageShell'
import { Skeleton } from '../components/ui/Skeleton'
import { fadeUp, stagger } from '../lib/motion'
import { useApiClient } from '../lib/api'
import { uploadToPresignedUrl, formatRelative } from '../lib/knowledgeBases'
import {
  MAX_STORAGE_BYTES,
  MAX_STORAGE_FILE_BYTES,
  MAX_STORAGE_FILES,
  completeStorageUpload,
  deleteStorageFile,
  formatBytes,
  invalidateStorage,
  requestStorageUpload,
  resolveStorageContentType,
  useStorageFiles,
  validateStorageFile,
  type StorageFile,
} from '../lib/storage'

type UploadItem = {
  id: string
  name: string
  size: number
  progress: number
  status: 'uploading' | 'error'
  error?: string
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong. Please try again.'
}

function StorageSkeleton() {
  return (
    <PageShell>
      <div className="mb-5 space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-3.5 w-80 max-w-full" />
      </div>
      <Skeleton className="h-28 w-full rounded-lg" />
      <div className="mt-4 space-y-2">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-14 w-full rounded-lg" />
        ))}
      </div>
    </PageShell>
  )
}

export function StoragePage() {
  const api = useApiClient()
  const { data, isPending, error, refetch } = useStorageFiles()

  const [uploads, setUploads] = useState<UploadItem[]>([])
  const [rejected, setRejected] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const files = useMemo(() => data?.files ?? [], [data])
  const usage = data?.usage
  const usedBytes = usage?.storageBytes ?? 0
  const fileCount = usage?.fileCount ?? files.length
  const pct = Math.min(100, Math.round((usedBytes / MAX_STORAGE_BYTES) * 100))

  const uploadOne = useCallback(
    async (file: File) => {
      const itemId = `${file.name}-${file.size}-${Date.now()}-${Math.random()}`
      setUploads((prev) => [
        { id: itemId, name: file.name, size: file.size, progress: 0, status: 'uploading' },
        ...prev,
      ])
      const update = (patch: Partial<UploadItem>) =>
        setUploads((prev) => prev.map((u) => (u.id === itemId ? { ...u, ...patch } : u)))
      try {
        const contentType = resolveStorageContentType(file)
        const presign = await requestStorageUpload(api, {
          fileName: file.name,
          contentType,
          sizeBytes: file.size,
        })
        await uploadToPresignedUrl(
          presign.uploadUrl,
          file,
          presign.contentType || contentType,
          (progress) => update({ progress }),
        )
        await completeStorageUpload(api, presign.fileId, {
          fileName: file.name,
          contentType,
          sizeBytes: file.size,
        })
        setUploads((prev) => prev.filter((u) => u.id !== itemId))
      } catch (err) {
        update({ status: 'error', error: errorMessage(err) })
      }
    },
    [api],
  )

  const addFiles = useCallback(
    async (incoming: File[]) => {
      setRejected(null)
      let count = fileCount
      let bytes = usedBytes
      const accepted: File[] = []
      for (const file of incoming) {
        const problem = validateStorageFile(file, count, bytes)
        if (problem) {
          setRejected(problem)
          continue
        }
        accepted.push(file)
        count += 1
        bytes += file.size
      }
      if (accepted.length === 0) return
      await Promise.all(accepted.map((file) => uploadOne(file)))
      invalidateStorage()
      refetch()
    },
    [fileCount, usedBytes, uploadOne, refetch],
  )

  const onDrop = useCallback(
    (accepted: File[]) => {
      if (accepted.length > 0) void addFiles(accepted)
    },
    [addFiles],
  )

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: true,
    disabled: fileCount >= MAX_STORAGE_FILES,
  })

  const removeFile = async (file: StorageFile) => {
    setDeletingId(file.id)
    try {
      await deleteStorageFile(api, file.id)
      toast.success(`${file.fileName} removed`)
      invalidateStorage()
      refetch()
    } catch (err) {
      toast.error(errorMessage(err))
    } finally {
      setDeletingId(null)
    }
  }

  if (isPending) return <StorageSkeleton />

  if (error) {
    return (
      <PageShell>
        <div className="flex min-h-[60vh] items-center justify-center">
          <ErrorState title="Couldn't load your files" error={error} onRetry={() => refetch()} />
        </div>
      </PageShell>
    )
  }

  const full = fileCount >= MAX_STORAGE_FILES

  return (
    <PageShell>
      <PageHeader
        title="Storage"
        description="Upload files to attach to your agents and skills later. Stored securely in S3, separate from your knowledge bases."
        badge="Build"
      />

      <Card className="mb-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="flex size-9 items-center justify-center rounded-md border border-border bg-raised text-accent">
              <HardDrive className="size-4" strokeWidth={1.75} />
            </span>
            <div>
              <p className="text-[13px] font-medium text-foreground">
                {formatBytes(usedBytes)} of {formatBytes(MAX_STORAGE_BYTES)}
              </p>
              <p className="text-[11px] text-subtle">
                {fileCount}/{MAX_STORAGE_FILES} files · up to {formatBytes(MAX_STORAGE_FILE_BYTES)} each
              </p>
            </div>
          </div>
          <span className="text-[11px] tabular-nums text-subtle">{pct}%</span>
        </div>
        <div className="mt-3 h-1.5 w-full overflow-hidden rounded-full bg-raised">
          <div
            className="h-full rounded-full bg-accent transition-all"
            style={{ width: `${pct}%` }}
          />
        </div>
      </Card>

      <div
        {...getRootProps()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-6 py-10 text-center transition-colors ${
          isDragActive
            ? 'border-accent bg-accent-soft/40'
            : 'border-border-strong bg-raised/20 hover:border-accent/50'
        } ${full ? 'cursor-not-allowed opacity-60' : ''}`}
      >
        <input {...getInputProps()} />
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <UploadCloud className="h-5 w-5" strokeWidth={1.5} />
        </div>
        <p className="mt-3 text-sm font-medium text-foreground">
          {full ? 'Storage is full' : 'Drag & drop files here'}
        </p>
        <p className="mt-1 max-w-sm text-xs text-muted">
          {full
            ? `You've reached the ${MAX_STORAGE_FILES}-file limit. Remove a file to add more.`
            : 'Any file type. Or click to browse.'}
        </p>
      </div>

      {rejected ? (
        <div className="mt-3 flex items-start gap-2.5 rounded-md border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
          <p className="text-sm text-foreground">{rejected}</p>
        </div>
      ) : null}

      {uploads.length > 0 ? (
        <div className="mt-4 space-y-2">
          {uploads.map((upload) => (
            <div
              key={upload.id}
              className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3.5 py-2.5"
            >
              <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-subtle">
                {upload.status === 'error' ? (
                  <AlertTriangle className="size-3.5 text-warning" />
                ) : (
                  <Loader2 className="size-3.5 animate-spin" />
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-medium text-foreground">{upload.name}</p>
                {upload.status === 'error' ? (
                  <p className="truncate text-[11px] text-warning">{upload.error}</p>
                ) : (
                  <div className="mt-1 h-1 w-full overflow-hidden rounded-full bg-raised">
                    <div
                      className="h-full rounded-full bg-accent transition-all"
                      style={{ width: `${upload.progress}%` }}
                    />
                  </div>
                )}
              </div>
              <span className="shrink-0 text-[11px] tabular-nums text-subtle">
                {formatBytes(upload.size)}
              </span>
            </div>
          ))}
        </div>
      ) : null}

      <section className="mt-6">
        <div className="mb-2 flex items-center gap-2">
          <h2 className="text-xs font-semibold text-foreground">Your files</h2>
          <span className="rounded-md bg-raised px-1.5 py-0.5 text-[11px] font-medium tabular-nums text-muted">
            {files.length}
          </span>
        </div>

        {files.length === 0 ? (
          <Card padding="none" className="overflow-hidden">
            <p className="px-4 py-8 text-center text-[13px] text-muted">
              No files yet. Drop some above to get started.
            </p>
          </Card>
        ) : (
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="show"
            className="space-y-2"
          >
            {files.map((file) => (
              <motion.div key={file.id} variants={fadeUp}>
                <div className="flex items-center gap-3 rounded-lg border border-border bg-surface px-3.5 py-2.5 transition-colors hover:border-border-strong">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
                    <FileIcon className="size-3.5" strokeWidth={1.75} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[13px] font-medium text-foreground">
                      {file.fileName}
                    </p>
                    <p className="truncate text-[11px] text-subtle">
                      {formatBytes(file.sizeBytes)}
                      {file.contentType ? ` · ${file.contentType}` : ''} ·{' '}
                      {formatRelative(file.createdAt)}
                    </p>
                  </div>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={
                      deletingId === file.id ? (
                        <Loader2 className="size-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="size-3.5" />
                      )
                    }
                    disabled={deletingId === file.id}
                    onClick={() => removeFile(file)}
                  >
                    Remove
                  </Button>
                </div>
              </motion.div>
            ))}
          </motion.div>
        )}
      </section>
    </PageShell>
  )
}

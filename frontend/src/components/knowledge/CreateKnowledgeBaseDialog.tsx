import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlertCircle,
  CheckCircle2,
  FileText,
  FilePlus2,
  Loader2,
  PenLine,
  Scissors,
  Upload,
  X,
} from 'lucide-react'
import { Dialog } from '../ui/Dialog'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { Segmented } from '../ui/Segmented'
import { FileDropzone } from './FileDropzone'
import { TagEditor } from './TagEditor'
import { useApiClient } from '../../lib/api'
import {
  CHUNK_OVERLAPS,
  CHUNK_SIZES,
  DEFAULT_CHUNK_OVERLAP,
  DEFAULT_CHUNK_SIZE,
  MAX_DESCRIPTION_LENGTH,
  MAX_FILES_PER_KB,
  MAX_FILE_BYTES,
  MAX_NAME_LENGTH,
  completeUpload,
  createInlineDocument,
  createKnowledgeBase,
  fileToBase64,
  formatBytes,
  invalidateKnowledgeBases,
  invalidateTagSuggestions,
  requestUpload,
  resolveContentType,
  uploadLocal,
  uploadToPresignedUrl,
  useTagSuggestions,
  validateFile,
  type DocumentTag,
} from '../../lib/knowledgeBases'

type Tab = 'write' | 'upload'
type ItemStatus = 'pending' | 'done' | 'error'

type Note = {
  id: string
  title: string
  content: string
  tags: DocumentTag[]
  status: ItemStatus
  error?: string
}

type StagedFile = {
  id: string
  file: File
  tags: DocumentTag[]
  status: 'queued' | 'uploading' | 'done' | 'error'
  progress: number
  error?: string
}

type CreateKnowledgeBaseDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  initialTab?: Tab
  initialFiles?: File[]
  maxFiles?: number
  onCreated?: () => void
}

function newId(): string {
  return Math.random().toString(36).slice(2)
}

function noteFileName(note: Note): string {
  const base = note.title.trim() || 'Untitled'
  return /\.md$/i.test(base) ? base : `${base}.md`
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () =>
      resolve(typeof reader.result === 'string' ? reader.result : '')
    reader.onerror = () => reject(new Error('Could not read file'))
    reader.readAsText(file)
  })
}

export function CreateKnowledgeBaseDialog({
  open,
  onOpenChange,
  initialTab = 'write',
  initialFiles,
  maxFiles = MAX_FILES_PER_KB,
  onCreated,
}: CreateKnowledgeBaseDialogProps) {
  const api = useApiClient()
  const mdInputRef = useRef<HTMLInputElement>(null)
  const { tags: tagSuggestions, refetch: refetchTags } = useTagSuggestions()

  const [tab, setTab] = useState<Tab>(initialTab)
  const [name, setName] = useState('')
  const [nameInvalid, setNameInvalid] = useState(false)
  const [description, setDescription] = useState('')
  const [notes, setNotes] = useState<Note[]>([])
  const [activeNoteId, setActiveNoteId] = useState<string | null>(null)
  const [notePreview, setNotePreview] = useState(false)
  const [staged, setStaged] = useState<StagedFile[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [kbId, setKbId] = useState<string | null>(null)
  const [chunkSize, setChunkSize] = useState<number>(DEFAULT_CHUNK_SIZE)
  const [chunkOverlap, setChunkOverlap] = useState<number>(
    DEFAULT_CHUNK_OVERLAP,
  )

  useEffect(() => {
    if (!open) return
    refetchTags()
    setName('')
    setNameInvalid(false)
    setDescription('')
    setNotes([])
    setActiveNoteId(null)
    setNotePreview(false)
    setStaged([])
    setError(null)
    setSubmitting(false)
    setKbId(null)
    setTab(initialTab)
    setChunkSize(DEFAULT_CHUNK_SIZE)
    setChunkOverlap(DEFAULT_CHUNK_OVERLAP)

    const files = initialFiles ?? []
    if (files.length > 0) {
      setStaged(
        files.slice(0, maxFiles).map((file) => ({
          id: newId(),
          file,
          tags: [],
          status: 'queued' as const,
          progress: 0,
        })),
      )
      setTab('upload')
    }
  }, [open, initialTab, initialFiles, maxFiles, refetchTags])

  const contentNotes = notes.filter((note) => note.content.trim().length > 0)
  const hasWrittenContent = contentNotes.length > 0
  const hasUploads = staged.length > 0
  const totalCount = contentNotes.length + staged.length
  const remaining = maxFiles - totalCount
  const activeNote = notes.find((note) => note.id === activeNoteId) ?? notes[0]

  // --- notes -----------------------------------------------------------------

  const addNote = (title = '', content = '') => {
    const note: Note = {
      id: newId(),
      title,
      content,
      tags: [],
      status: 'pending',
    }
    setNotes((current) => [...current, note])
    setActiveNoteId(note.id)
    setTab('write')
  }

  const updateNote = (id: string, patch: Partial<Note>) => {
    setNotes((current) =>
      current.map((note) => (note.id === id ? { ...note, ...patch } : note)),
    )
  }

  const removeNote = (id: string) => {
    setNotes((current) => {
      const next = current.filter((note) => note.id !== id)
      if (activeNoteId === id) setActiveNoteId(next[0]?.id ?? null)
      return next
    })
  }

  const openMarkdownFiles = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const remainingSlots = maxFiles - notes.length
    const chosen = Array.from(files).slice(0, Math.max(0, remainingSlots))
    const loaded: Note[] = []
    for (const file of chosen) {
      try {
        const content = await readFileAsText(file)
        loaded.push({
          id: newId(),
          title: file.name.replace(/\.md$/i, ''),
          content,
          tags: [],
          status: 'pending',
        })
      } catch {
        setError(`Could not read ${file.name}`)
      }
    }
    if (loaded.length > 0) {
      setNotes((current) => [...current, ...loaded])
      setActiveNoteId(loaded[0].id)
    }
  }

  // --- uploads ---------------------------------------------------------------

  const addFiles = (files: File[]) => {
    setError(null)
    const next: StagedFile[] = []
    const problems: string[] = []
    let slots = maxFiles - staged.length - notes.length
    const existingNames = new Set(
      staged.map((item) => item.file.name.toLowerCase()),
    )
    for (const file of files) {
      const problem = validateFile(file, slots)
      if (problem) {
        problems.push(`${file.name}: ${problem}`)
        continue
      }
      if (existingNames.has(file.name.toLowerCase())) {
        problems.push(`${file.name}: a file with this name is already added`)
        continue
      }
      existingNames.add(file.name.toLowerCase())
      next.push({ id: newId(), file, tags: [], status: 'queued', progress: 0 })
      slots -= 1
    }
    if (next.length > 0) setStaged((current) => [...current, ...next])
    if (problems.length > 0) setError(problems[0])
  }

  const removeStaged = (id: string) => {
    setStaged((current) => current.filter((item) => item.id !== id))
  }

  const updateStaged = (id: string, patch: Partial<StagedFile>) => {
    setStaged((current) =>
      current.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    )
  }

  const uploadOne = async (knowledgeBaseId: string, item: StagedFile) => {
    updateStaged(item.id, { status: 'uploading', progress: 0, error: undefined })
    try {
      const contentType = resolveContentType(item.file)
      const presign = await requestUpload(api, knowledgeBaseId, {
        fileName: item.file.name,
        contentType,
        sizeBytes: item.file.size,
        tags: item.tags,
      })
      if (presign.mode === 's3' && presign.uploadUrl) {
        await uploadToPresignedUrl(
          presign.uploadUrl,
          item.file,
          presign.contentType || contentType,
          (progress) => updateStaged(item.id, { progress }),
        )
        await completeUpload(api, knowledgeBaseId, presign.documentId)
      } else {
        const base64 = await fileToBase64(item.file)
        await uploadLocal(api, knowledgeBaseId, presign.documentId, base64)
      }
      updateStaged(item.id, { status: 'done', progress: 100 })
      return true
    } catch (uploadError) {
      updateStaged(item.id, {
        status: 'error',
        error:
          uploadError instanceof Error ? uploadError.message : 'Upload failed',
      })
      return false
    }
  }

  // --- submit ----------------------------------------------------------------

  const handleSubmit = async () => {
    setError(null)
    setNameInvalid(false)
    if (!name.trim()) {
      setNameInvalid(true)
      setError('Knowledge base name is required')
      return
    }
    if (hasWrittenContent && hasUploads) {
      setError('Use either written files or uploads, not both')
      return
    }
    if (totalCount === 0) {
      setError('Write a file or add at least one upload')
      return
    }
    if (totalCount > maxFiles) {
      setError(`A knowledge base can hold at most ${maxFiles} files`)
      return
    }
    const missingName = contentNotes.find((note) => !note.title.trim())
    if (missingName) {
      setActiveNoteId(missingName.id)
      setError('Every file needs a name before saving')
      return
    }
    const seenNames = new Set<string>()
    for (const name of [
      ...contentNotes.map((note) => noteFileName(note)),
      ...staged.map((item) => item.file.name),
    ]) {
      const key = name.toLowerCase()
      if (seenNames.has(key)) {
        setError(
          `Duplicate file name "${name}" — file names must be unique in a knowledge base`,
        )
        return
      }
      seenNames.add(key)
    }

    setSubmitting(true)
    try {
      let knowledgeBaseId = kbId
      if (!knowledgeBaseId) {
        const created = await createKnowledgeBase(api, {
          name: name.trim(),
          description: description.trim() || undefined,
          chunkSize,
          chunkOverlap,
        })
        knowledgeBaseId = created.id
        setKbId(created.id)
      }

      let noteFailures = 0
      for (const note of contentNotes.filter((item) => item.status !== 'done')) {
        try {
          await createInlineDocument(api, knowledgeBaseId, {
            name: note.title.trim(),
            content: note.content,
            tags: note.tags,
          })
          updateNote(note.id, { status: 'done' })
        } catch (noteError) {
          noteFailures += 1
          updateNote(note.id, {
            status: 'error',
            error:
              noteError instanceof Error ? noteError.message : 'Save failed',
          })
        }
      }

      const pending = staged.filter((item) => item.status !== 'done')
      const uploadResults = await Promise.all(
        pending.map((item) => uploadOne(knowledgeBaseId as string, item)),
      )

      const failedUploads = uploadResults.filter((ok) => !ok).length
      if (noteFailures + failedUploads === 0) {
        invalidateKnowledgeBases()
        invalidateTagSuggestions()
        onCreated?.()
        onOpenChange(false)
      } else {
        setError(
          `${noteFailures + failedUploads} file(s) failed. Retry or remove them.`,
        )
      }
    } catch (submitError) {
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Something went wrong. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  const summaryNames = [
    ...contentNotes.map((note) => noteFileName(note)),
    ...staged.map((item) => item.file.name),
  ]

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="2xl"
      contentClassName="h-[85vh]"
      title="New knowledge base"
      description="Write markdown files, or upload documents. Pick one — not both."
      banner={
        error ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <p className="text-sm text-foreground">{error}</p>
          </div>
        ) : null
      }
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={submitting}
            icon={
              submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <PenLine className="h-4 w-4" />
              )
            }
          >
            {submitting ? 'Saving…' : 'Save knowledge base'}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <div className="space-y-4">
          <label className="block">
            <span className="mb-1.5 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted">
              <span>Name</span>
              <span className="normal-case text-subtle">
                {name.length}/{MAX_NAME_LENGTH}
              </span>
            </span>
            <input
              value={name}
              onChange={(event) => {
                setName(event.target.value)
                if (nameInvalid) {
                  setNameInvalid(false)
                  setError(null)
                }
              }}
              placeholder="e.g. Product Documentation"
              maxLength={MAX_NAME_LENGTH}
              disabled={Boolean(kbId)}
              className={`h-10 w-full rounded-xl border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 disabled:opacity-60 ${
                nameInvalid ? 'border-warning' : 'border-border'
              }`}
            />
          </label>
          <label className="block">
            <span className="mb-1.5 flex items-center justify-between text-xs font-semibold uppercase tracking-wide text-muted">
              <span>
                Description{' '}
                <span className="normal-case text-subtle">(optional)</span>
              </span>
              <span className="normal-case text-subtle">
                {description.length}/{MAX_DESCRIPTION_LENGTH}
              </span>
            </span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What does this knowledge base cover?"
              rows={3}
              maxLength={MAX_DESCRIPTION_LENGTH}
              disabled={Boolean(kbId)}
              className="w-full resize-y rounded-xl border border-border bg-canvas px-3 py-2.5 text-sm leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 disabled:opacity-60 scrollbar-thin"
            />
          </label>
        </div>

        <div className="rounded-xl border border-border bg-raised/30 p-3">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted">
            <Scissors className="h-3.5 w-3.5" />
            Chunking
          </div>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <span className="mb-1.5 block text-[11px] font-medium text-muted">
                Chunk size (tokens)
              </span>
              <Segmented
                options={CHUNK_SIZES}
                value={chunkSize}
                onChange={setChunkSize}
                size="sm"
                disabled={Boolean(kbId)}
              />
            </div>
            <div>
              <span className="mb-1.5 block text-[11px] font-medium text-muted">
                Chunk overlap (tokens)
              </span>
              <Segmented
                options={CHUNK_OVERLAPS}
                value={chunkOverlap}
                onChange={setChunkOverlap}
                size="sm"
                disabled={Boolean(kbId)}
              />
            </div>
          </div>
          <p className="mt-2 text-[11px] leading-relaxed text-subtle">
            Fixed at creation — every file in this knowledge base follows the
            same chunking.
          </p>
        </div>

        <div className="inline-flex rounded-xl border border-border bg-raised/40 p-1">
          {(
            [
              { id: 'write', label: 'Write files', icon: PenLine },
              { id: 'upload', label: 'Upload files', icon: Upload },
            ] as const
          ).map((item) => {
            const Icon = item.icon
            const active = tab === item.id
            const disabled =
              (item.id === 'write' && hasUploads) ||
              (item.id === 'upload' && hasWrittenContent)
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                disabled={disabled}
                title={
                  disabled
                    ? item.id === 'write'
                      ? 'Remove uploaded files to write instead'
                      : 'Remove written files to upload instead'
                    : undefined
                }
                className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
                  active
                    ? 'bg-accent-soft text-accent'
                    : 'text-muted hover:text-foreground'
                } ${disabled ? 'cursor-not-allowed opacity-40' : ''}`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            )
          })}
        </div>

        {tab === 'write' ? (
          <div className="space-y-3">
            <input
              ref={mdInputRef}
              type="file"
              accept=".md,text/markdown"
              multiple
              className="hidden"
              onChange={(event) => {
                void openMarkdownFiles(event.target.files)
                event.target.value = ''
              }}
            />

            {notes.length === 0 ? (
              <div className="flex flex-col items-center rounded-2xl border border-dashed border-border-strong bg-raised/20 px-6 py-10 text-center">
                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-accent-soft text-accent">
                  <PenLine className="h-5 w-5" strokeWidth={1.5} />
                </div>
                <p className="mt-3 text-sm font-medium text-foreground">
                  No files yet
                </p>
                <p className="mt-1 text-xs text-muted">
                  Each file is saved as a markdown document in this knowledge
                  base.
                </p>
                <div className="mt-4 flex gap-2">
                  <Button
                    size="sm"
                    icon={<FilePlus2 className="h-3.5 w-3.5" />}
                    onClick={() => addNote()}
                  >
                    New file
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    icon={<Upload className="h-3.5 w-3.5" />}
                    onClick={() => mdInputRef.current?.click()}
                  >
                    Open .md
                  </Button>
                </div>
              </div>
            ) : (
              <div className="overflow-hidden rounded-2xl border border-border">
                <div className="flex items-center gap-1 overflow-x-auto border-b border-border bg-raised/40 px-2 py-1.5 scrollbar-thin">
                  {notes.map((note) => {
                    const active = activeNote?.id === note.id
                    return (
                      <span
                        key={note.id}
                        className={`group inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
                          active
                            ? 'bg-accent-soft text-accent'
                            : 'text-muted hover:bg-raised hover:text-foreground'
                        }`}
                      >
                        <button
                          type="button"
                          onClick={() => setActiveNoteId(note.id)}
                          className="max-w-[12rem] truncate"
                        >
                          {noteFileName(note)}
                        </button>
                        {note.status === 'done' ? (
                          <CheckCircle2 className="h-3 w-3 text-success" />
                        ) : note.status === 'error' ? (
                          <AlertCircle className="h-3 w-3 text-warning" />
                        ) : null}
                        <button
                          type="button"
                          onClick={() => removeNote(note.id)}
                          disabled={submitting}
                          aria-label={`Close ${noteFileName(note)}`}
                          className="rounded p-0.5 text-subtle hover:bg-canvas hover:text-warning disabled:opacity-40"
                        >
                          <X className="h-3 w-3" />
                        </button>
                      </span>
                    )
                  })}
                  <button
                    type="button"
                    onClick={() => addNote()}
                    disabled={notes.length >= maxFiles}
                    aria-label="New file"
                    className="ml-1 rounded-lg p-1.5 text-subtle transition-colors hover:bg-raised hover:text-accent disabled:opacity-40"
                  >
                    <FilePlus2 className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => mdInputRef.current?.click()}
                    className="ml-0.5 shrink-0 rounded-lg px-2 py-1.5 text-[11px] font-semibold text-subtle transition-colors hover:bg-raised hover:text-accent"
                  >
                    Open .md
                  </button>
                </div>

                {activeNote ? (
                  <div className="space-y-3 p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <input
                        value={activeNote.title}
                        onChange={(event) =>
                          updateNote(activeNote.id, {
                            title: event.target.value,
                          })
                        }
                        placeholder="File name (without .md)"
                        maxLength={200}
                        disabled={activeNote.status === 'done'}
                        className="h-9 min-w-0 flex-1 rounded-lg border border-border bg-canvas px-3 text-sm font-medium text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 disabled:opacity-60"
                      />
                      <div className="inline-flex rounded-lg border border-border bg-raised/40 p-0.5">
                        {(
                          [
                            { id: false, label: 'Edit' },
                            { id: true, label: 'Preview' },
                          ] as const
                        ).map((option) => (
                          <button
                            key={option.label}
                            type="button"
                            onClick={() => setNotePreview(option.id)}
                            className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                              notePreview === option.id
                                ? 'bg-accent-soft text-accent'
                                : 'text-muted hover:text-foreground'
                            }`}
                          >
                            {option.label}
                          </button>
                        ))}
                      </div>
                    </div>

                    {notePreview ? (
                      <div className="md-preview h-96 w-full overflow-y-auto rounded-xl border border-border bg-canvas px-4 py-3 scrollbar-thin">
                        {activeNote.content.trim() ? (
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {activeNote.content}
                          </ReactMarkdown>
                        ) : (
                          <p className="text-sm text-subtle">
                            Nothing to preview yet.
                          </p>
                        )}
                      </div>
                    ) : (
                      <textarea
                        value={activeNote.content}
                        onChange={(event) =>
                          updateNote(activeNote.id, {
                            content: event.target.value,
                          })
                        }
                        rows={16}
                        disabled={activeNote.status === 'done'}
                        placeholder={'# Heading\n\nWrite the knowledge here. Markdown is supported.'}
                        className="h-96 w-full resize-y rounded-xl border border-border bg-canvas px-3 py-2.5 font-mono text-[13px] leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 disabled:opacity-60 scrollbar-thin"
                      />
                    )}

                    <div className="rounded-xl border border-border bg-raised/30 p-3">
                      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted">
                        Tags{' '}
                        <span className="normal-case text-subtle">
                          (optional)
                        </span>
                      </p>
                      <TagEditor
                        tags={activeNote.tags}
                        onChange={(tags) => updateNote(activeNote.id, { tags })}
                        suggestions={tagSuggestions}
                        disabled={activeNote.status === 'done'}
                      />
                    </div>
                  </div>
                ) : null}
              </div>
            )}
          </div>
        ) : (
          <div className="space-y-4">
            <FileDropzone
              onFiles={addFiles}
              onRejected={(message) => setError(message)}
              remaining={remaining}
              disabled={submitting}
            />

            {staged.length > 0 ? (
              <ul className="space-y-2">
                {staged.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-xl border border-border bg-raised/40 p-3.5"
                  >
                    <div className="flex items-center gap-3">
                      <FileText className="h-4 w-4 shrink-0 text-accent" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-foreground">
                          {item.file.name}
                        </p>
                        <p className="text-xs text-subtle">
                          {formatBytes(item.file.size)}
                          {item.status === 'error' && item.error
                            ? ` · ${item.error}`
                            : ''}
                        </p>
                        {item.status === 'uploading' ? (
                          <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-elevated">
                            <div
                              className="h-full rounded-full bg-accent transition-all"
                              style={{ width: `${item.progress}%` }}
                            />
                          </div>
                        ) : null}
                      </div>
                      <div className="flex items-center gap-1.5">
                        {item.status === 'done' ? (
                          <CheckCircle2 className="h-4 w-4 text-success" />
                        ) : item.status === 'uploading' ? (
                          <Loader2 className="h-4 w-4 animate-spin text-accent" />
                        ) : item.status === 'error' ? (
                          <AlertCircle className="h-4 w-4 text-warning" />
                        ) : null}
                        <button
                          type="button"
                          onClick={() => removeStaged(item.id)}
                          disabled={submitting || item.status === 'uploading'}
                          className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning disabled:opacity-40"
                          aria-label="Remove file"
                        >
                          <X className="h-4 w-4" />
                        </button>
                      </div>
                    </div>
                    <div className="mt-3 border-t border-border pt-3">
                      <TagEditor
                        tags={item.tags}
                        onChange={(tags) =>
                          setStaged((current) =>
                            current.map((value) =>
                              value.id === item.id ? { ...value, tags } : value,
                            ),
                          )
                        }
                        suggestions={tagSuggestions}
                        disabled={submitting || item.status === 'done'}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        )}

        <div className="rounded-xl border border-border bg-raised/30 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant={totalCount >= maxFiles ? 'warning' : 'default'}
            >
              {totalCount}/{maxFiles} files
            </Badge>
            <span className="text-xs text-subtle">
              Max {formatBytes(MAX_FILE_BYTES)} per file · tags optional
            </span>
          </div>
          {summaryNames.length > 0 ? (
            <div className="mt-2 text-xs text-muted">
              <span className="font-semibold text-foreground">
                Will save {summaryNames.length} file
                {summaryNames.length === 1 ? '' : 's'}:
              </span>{' '}
              {summaryNames.join(', ')}
            </div>
          ) : null}
        </div>
      </div>
    </Dialog>
  )
}

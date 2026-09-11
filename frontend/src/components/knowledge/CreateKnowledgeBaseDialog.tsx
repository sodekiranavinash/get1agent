import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  FileText,
  Loader2,
  PenLine,
  Trash2,
  Upload,
} from 'lucide-react'
import { Dialog } from '../ui/Dialog'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { FileDropzone } from './FileDropzone'
import { TagEditor } from './TagEditor'
import { useApiClient } from '../../lib/api'
import {
  MAX_FILES_PER_KB,
  MAX_FILE_BYTES,
  MAX_TAGS_PER_DOCUMENT,
  MIN_TAG_DESCRIPTION_LENGTH,
  completeUpload,
  createInlineDocument,
  createKnowledgeBase,
  fileToBase64,
  formatBytes,
  invalidateKnowledgeBases,
  requestUpload,
  resolveContentType,
  uploadLocal,
  uploadToPresignedUrl,
  validateFile,
  type DocumentTag,
} from '../../lib/knowledgeBases'

type Tab = 'write' | 'upload'

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
  onCreated?: () => void
}

function validateTags(tags: DocumentTag[], label: string): string | null {
  if (tags.length > MAX_TAGS_PER_DOCUMENT) {
    return `${label}: at most ${MAX_TAGS_PER_DOCUMENT} tags`
  }
  const seen = new Set<string>()
  for (const tag of tags) {
    const name = tag.name.trim()
    if (!name) return `${label}: every tag needs a name`
    if (seen.has(name.toLowerCase())) return `${label}: duplicate tag "${name}"`
    seen.add(name.toLowerCase())
    if (tag.description.trim().length < MIN_TAG_DESCRIPTION_LENGTH) {
      return `${label}: tag "${name}" needs a description of at least ${MIN_TAG_DESCRIPTION_LENGTH} characters`
    }
  }
  return null
}

function newId(): string {
  return Math.random().toString(36).slice(2)
}

export function CreateKnowledgeBaseDialog({
  open,
  onOpenChange,
  initialTab = 'write',
  initialFiles,
  onCreated,
}: CreateKnowledgeBaseDialogProps) {
  const api = useApiClient()
  const [tab, setTab] = useState<Tab>(initialTab)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [noteTitle, setNoteTitle] = useState('')
  const [noteContent, setNoteContent] = useState('')
  const [noteTags, setNoteTags] = useState<DocumentTag[]>([])
  const [showNoteTags, setShowNoteTags] = useState(false)
  const [notePreview, setNotePreview] = useState(false)
  const [staged, setStaged] = useState<StagedFile[]>([])
  const [expanded, setExpanded] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [kbId, setKbId] = useState<string | null>(null)
  const [noteCreated, setNoteCreated] = useState(false)

  useEffect(() => {
    if (!open) return
    setName('')
    setDescription('')
    setNoteTitle('')
    setNoteContent('')
    setNoteTags([])
    setShowNoteTags(false)
    setStaged([])
    setExpanded([])
    setError(null)
    setSubmitting(false)
    setKbId(null)
    setNoteCreated(false)
    setTab(initialTab)

    const files = initialFiles ?? []
    if (files.length > 0) {
      const next: StagedFile[] = []
      for (const file of files.slice(0, MAX_FILES_PER_KB)) {
        next.push({
          id: newId(),
          file,
          tags: [],
          status: 'queued',
          progress: 0,
        })
      }
      setStaged(next)
      setTab('upload')
    }
  }, [open, initialTab, initialFiles])

  const noteHasContent = noteContent.trim().length > 0
  const totalCount = staged.length + (noteHasContent ? 1 : 0)
  const remaining = MAX_FILES_PER_KB - staged.length - (noteHasContent ? 1 : 0)

  const updateStaged = (id: string, patch: Partial<StagedFile>) => {
    setStaged((current) =>
      current.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    )
  }

  const addFiles = (files: File[]) => {
    setError(null)
    const next: StagedFile[] = []
    const problems: string[] = []
    let slots = MAX_FILES_PER_KB - staged.length - (noteHasContent ? 1 : 0)
    for (const file of files) {
      const problem = validateFile(file, slots)
      if (problem) {
        problems.push(`${file.name}: ${problem}`)
        continue
      }
      next.push({ id: newId(), file, tags: [], status: 'queued', progress: 0 })
      slots -= 1
    }
    if (next.length > 0) setStaged((current) => [...current, ...next])
    if (problems.length > 0) setError(problems[0])
  }

  const removeStaged = (id: string) => {
    setStaged((current) => current.filter((item) => item.id !== id))
  }

  const toggleExpanded = (id: string) => {
    setExpanded((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : [...current, id],
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

  const handleSubmit = async () => {
    setError(null)
    if (!name.trim()) {
      setError('Knowledge base name is required')
      return
    }
    if (noteHasContent && !noteTitle.trim()) {
      setError('Give your note a title')
      return
    }
    if (noteHasContent && noteContent.length > MAX_FILE_BYTES) {
      setError(`Note exceeds the ${formatBytes(MAX_FILE_BYTES)} limit`)
      return
    }
    if (totalCount === 0) {
      setError('Write a note or add at least one file')
      return
    }
    if (totalCount > MAX_FILES_PER_KB) {
      setError(`A knowledge base can hold at most ${MAX_FILES_PER_KB} files`)
      return
    }
    const noteTagError = validateTags(noteTags, 'Note')
    if (noteHasContent && noteTagError) {
      setShowNoteTags(true)
      setError(noteTagError)
      return
    }
    for (const item of staged) {
      const tagError = validateTags(item.tags, item.file.name)
      if (tagError) {
        setExpanded((current) =>
          current.includes(item.id) ? current : [...current, item.id],
        )
        setError(tagError)
        return
      }
    }

    setSubmitting(true)
    try {
      let knowledgeBaseId = kbId
      if (!knowledgeBaseId) {
        const created = await createKnowledgeBase(api, {
          name: name.trim(),
          description: description.trim() || undefined,
        })
        knowledgeBaseId = created.id
        setKbId(created.id)
      }

      if (noteHasContent && !noteCreated) {
        await createInlineDocument(api, knowledgeBaseId, {
          name: noteTitle.trim(),
          content: noteContent,
          tags: noteTags,
        })
        setNoteCreated(true)
      }

      const pending = staged.filter((item) => item.status !== 'done')
      const results = await Promise.all(
        pending.map((item) => uploadOne(knowledgeBaseId as string, item)),
      )
      const failures = results.filter((ok) => !ok).length

      if (failures === 0) {
        invalidateKnowledgeBases()
        onCreated?.()
        onOpenChange(false)
      } else {
        setError(
          `${failures} file${failures === 1 ? '' : 's'} failed to upload. Retry or remove them.`,
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

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="xl"
      title="New knowledge base"
      description="Write knowledge directly, or upload documents. Add tags to make retrieval smarter later."
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
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              Name
            </span>
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Product Documentation"
              maxLength={255}
              disabled={Boolean(kbId)}
              className="h-10 w-full rounded-xl border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 disabled:opacity-60"
            />
          </label>
          <label className="block">
            <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
              Description <span className="normal-case text-subtle">(optional)</span>
            </span>
            <input
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What does this knowledge base cover?"
              disabled={Boolean(kbId)}
              className="h-10 w-full rounded-xl border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 disabled:opacity-60"
            />
          </label>
        </div>

        <div className="inline-flex rounded-xl border border-border bg-raised/40 p-1">
          {(
            [
              { id: 'write', label: 'Write', icon: PenLine },
              { id: 'upload', label: 'Upload files', icon: Upload },
            ] as const
          ).map((item) => {
            const Icon = item.icon
            const active = tab === item.id
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setTab(item.id)}
                className={`inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold transition-colors ${
                  active
                    ? 'bg-accent-soft text-accent'
                    : 'text-muted hover:text-foreground'
                }`}
              >
                <Icon className="h-4 w-4" />
                {item.label}
              </button>
            )
          })}
        </div>

        {error ? (
          <div className="flex items-start gap-2.5 rounded-xl border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warning" />
            <p className="text-sm text-foreground">{error}</p>
          </div>
        ) : null}

        {tab === 'write' ? (
          <div className="space-y-4">
            <label className="block">
              <span className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-muted">
                Note title
              </span>
              <input
                value={noteTitle}
                onChange={(event) => setNoteTitle(event.target.value)}
                placeholder="e.g. Returns policy"
                maxLength={200}
                disabled={noteCreated}
                className="h-10 w-full rounded-xl border border-border bg-canvas px-3 text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 disabled:opacity-60"
              />
            </label>
            <div>
              <div className="mb-1.5 flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted">
                  Markdown
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-subtle">
                    saved as .md · {formatBytes(new Blob([noteContent]).size)}
                  </span>
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
              </div>
              {notePreview ? (
                <div className="md-preview min-h-[16rem] w-full overflow-y-auto rounded-xl border border-border bg-canvas px-4 py-3 scrollbar-thin">
                  {noteContent.trim() ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {noteContent}
                    </ReactMarkdown>
                  ) : (
                    <p className="text-sm text-subtle">
                      Nothing to preview yet.
                    </p>
                  )}
                </div>
              ) : (
                <textarea
                  value={noteContent}
                  onChange={(event) => setNoteContent(event.target.value)}
                  rows={12}
                  disabled={noteCreated}
                  placeholder={'# Heading\n\nWrite the knowledge here. Markdown is supported.'}
                  className="w-full resize-y rounded-xl border border-border bg-canvas px-3 py-2.5 font-mono text-[13px] leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 disabled:opacity-60 scrollbar-thin"
                />
              )}
            </div>

            <div className="rounded-xl border border-border bg-raised/30">
              <button
                type="button"
                onClick={() => setShowNoteTags((value) => !value)}
                className="flex w-full items-center justify-between px-3.5 py-2.5 text-left"
              >
                <span className="text-sm font-medium text-foreground">
                  Metadata tags
                  {noteTags.length > 0 ? (
                    <span className="ml-2 text-xs text-subtle">
                      {noteTags.length}/{MAX_TAGS_PER_DOCUMENT}
                    </span>
                  ) : null}
                </span>
                {showNoteTags ? (
                  <ChevronDown className="h-4 w-4 text-subtle" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-subtle" />
                )}
              </button>
              {showNoteTags ? (
                <div className="border-t border-border p-3.5">
                  <TagEditor
                    tags={noteTags}
                    onChange={setNoteTags}
                    disabled={noteCreated}
                  />
                </div>
              ) : null}
            </div>
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
                {staged.map((item) => {
                  const isExpanded = expanded.includes(item.id)
                  return (
                    <li
                      key={item.id}
                      className="rounded-xl border border-border bg-raised/40"
                    >
                      <div className="flex items-center gap-3 px-3.5 py-3">
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
                            onClick={() => toggleExpanded(item.id)}
                            className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-raised hover:text-foreground"
                            aria-label="Toggle tags"
                          >
                            <ChevronDown
                              className={`h-4 w-4 transition-transform ${isExpanded ? '' : '-rotate-90'}`}
                            />
                          </button>
                          <button
                            type="button"
                            onClick={() => removeStaged(item.id)}
                            disabled={submitting || item.status === 'uploading'}
                            className="rounded-lg p-1.5 text-subtle transition-colors hover:bg-raised hover:text-warning disabled:opacity-40"
                            aria-label="Remove file"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </div>
                      {isExpanded ? (
                        <div className="border-t border-border p-3.5">
                          <TagEditor
                            tags={item.tags}
                            onChange={(tags) =>
                              setStaged((current) =>
                                current.map((value) =>
                                  value.id === item.id
                                    ? { ...value, tags }
                                    : value,
                                ),
                              )
                            }
                            disabled={submitting || item.status === 'done'}
                          />
                        </div>
                      ) : null}
                    </li>
                  )
                })}
              </ul>
            ) : null}
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 text-xs text-subtle">
          <Badge variant={totalCount >= MAX_FILES_PER_KB ? 'warning' : 'default'}>
            {totalCount}/{MAX_FILES_PER_KB} files
          </Badge>
          <span>
            Max {formatBytes(MAX_FILE_BYTES)} per file · up to{' '}
            {MAX_TAGS_PER_DOCUMENT} tags per file (each needs a{' '}
            {MIN_TAG_DESCRIPTION_LENGTH}+ character description)
          </span>
        </div>
      </div>
    </Dialog>
  )
}

import { useEffect, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertCircle, Check, Eye, Loader2, PenLine } from 'lucide-react'
import { Dialog } from '../ui/Dialog'
import { Button } from '../ui/Button'
import { McpServerMultiSelect } from './McpServerMultiSelect'
import { useApiClient } from '../../lib/api'
import {
  MAX_ALLOWED_TOOLS,
  MAX_DESCRIPTION_LENGTH,
  MAX_SKILL_CONTENT_BYTES,
  SKILL_NAME_MAX,
  createAgentSkill,
  fetchAgentSkill,
  invalidateAgentSkills,
  skillContentBytes,
  updateAgentSkill,
  useMcpServers,
  validateSkillName,
} from '../../lib/agentSkills'

type SkillEditorDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** When set, the dialog edits this skill instead of creating a new one. */
  skillId?: string | null
  onSaved?: () => void
}

export function SkillEditorDialog({
  open,
  onOpenChange,
  skillId,
  onSaved,
}: SkillEditorDialogProps) {
  const api = useApiClient()
  const { servers: availableServers, refetch: refetchServers } = useMcpServers()
  const editing = Boolean(skillId)

  const [name, setName] = useState('')
  const [nameInvalid, setNameInvalid] = useState(false)
  const [description, setDescription] = useState('')
  const [allowedTools, setAllowedTools] = useState<string[]>([])
  const [content, setContent] = useState('')
  const [preview, setPreview] = useState(false)
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!open) return
    refetchServers()
    setName('')
    setNameInvalid(false)
    setDescription('')
    setAllowedTools([])
    setContent('')
    setPreview(false)
    setError(null)
    setSubmitting(false)

    if (!skillId) {
      setLoading(false)
      return
    }

    let cancelled = false
    setLoading(true)
    ;(async () => {
      try {
        const detail = await fetchAgentSkill(api, skillId)
        if (cancelled) return
        setName(detail.name)
        setDescription(detail.description)
        setAllowedTools(detail.allowedTools)
        setContent(detail.content)
      } catch (loadError) {
        if (!cancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Could not load skill',
          )
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [open, skillId, api, refetchServers])

  const handleSubmit = async () => {
    setError(null)
    setNameInvalid(false)
    const nameError = validateSkillName(name)
    if (nameError) {
      setNameInvalid(true)
      setError(nameError)
      return
    }
    if (!description.trim()) {
      setError('Description is required — it tells the agent when to use this skill')
      return
    }
    if (description.trim().length > MAX_DESCRIPTION_LENGTH) {
      setError(`Description must be at most ${MAX_DESCRIPTION_LENGTH} characters`)
      return
    }
    if (!content.trim()) {
      setError('Skill instructions are required')
      return
    }
    if (skillContentBytes(content) > MAX_SKILL_CONTENT_BYTES) {
      setError('Skill instructions exceed the 100 KB limit')
      return
    }
    if (allowedTools.length > MAX_ALLOWED_TOOLS) {
      setError(`At most ${MAX_ALLOWED_TOOLS} servers can be selected`)
      return
    }

    setSubmitting(true)
    try {
      const payload = {
        name: name.trim(),
        description: description.trim(),
        allowedTools,
        content,
        source: 'write' as const,
      }
      if (skillId) await updateAgentSkill(api, skillId, payload)
      else await createAgentSkill(api, payload)
      invalidateAgentSkills()
      onSaved?.()
      onOpenChange(false)
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : 'Could not save skill',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      size="lg"
      title={editing ? 'Edit skill' : 'New agent skill'}
      description="Fill in the fields below. The agent uses the name and description to pick the skill, then follows the instructions."
      banner={
        error ? (
          <div className="flex items-start gap-2.5 rounded-md border border-warning/30 bg-warning-soft/50 px-3.5 py-2.5">
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
            disabled={submitting || loading}
            icon={
              submitting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : editing ? (
                <Check className="h-4 w-4" />
              ) : (
                <PenLine className="h-4 w-4" />
              )
            }
          >
            {submitting
              ? 'Saving…'
              : editing
                ? 'Save changes'
                : 'Create skill'}
          </Button>
        </>
      }
    >
      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-5 w-5 animate-spin text-accent" />
        </div>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="mb-1.5 flex items-center justify-between text-xs font-semibold tracking-wide text-muted uppercase">
                <span>Name</span>
                <span className="normal-case text-subtle">
                  {name.length}/{SKILL_NAME_MAX}
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
                placeholder="e.g. pdf-processing"
                maxLength={SKILL_NAME_MAX}
                className={`h-10 w-full rounded-md border bg-canvas px-3 font-mono text-sm text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 ${
                  nameInvalid ? 'border-warning' : 'border-border'
                }`}
              />
              <p className="mt-1.5 text-[11px] text-subtle">
                Lowercase letters, numbers and hyphens.
              </p>
            </label>

            <label className="block">
              <span className="mb-1.5 flex items-center justify-between text-xs font-semibold tracking-wide text-muted uppercase">
                <span>Allowed MCP Servers</span>
                <span className="normal-case text-subtle">optional</span>
              </span>
              <McpServerMultiSelect
                servers={availableServers}
                value={allowedTools}
                onChange={setAllowedTools}
                disabled={submitting}
              />
              <p className="mt-1.5 text-[11px] text-subtle">
                Servers the agent may use while running this skill.
              </p>
            </label>
          </div>

          <label className="block">
            <span className="mb-1.5 flex items-center justify-between text-xs font-semibold tracking-wide text-muted uppercase">
              <span>Description</span>
              <span className="normal-case text-subtle">
                {description.length}/{MAX_DESCRIPTION_LENGTH}
              </span>
            </span>
            <textarea
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="Extract text and tables from PDF files"
              rows={3}
              maxLength={MAX_DESCRIPTION_LENGTH}
              className="min-h-[4.5rem] w-full resize-y rounded-md border border-border bg-canvas px-3 py-2 text-sm leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 scrollbar-thin"
            />
            <p className="mt-1.5 text-[11px] text-subtle">
              Shown to the agent for routing — be specific about when to
              use this skill.
            </p>
          </label>

          <div className="block">
            <span className="mb-1.5 flex items-center justify-between text-xs font-semibold tracking-wide text-muted uppercase">
              <span className="inline-flex items-center gap-2">
                Skill instructions
                {preview ? (
                  <span className="inline-flex items-center gap-1 normal-case text-subtle">
                    <Eye className="h-3 w-3" /> Previewing rendered markdown
                  </span>
                ) : null}
              </span>
              <span className="flex items-center gap-2">
                <span className="normal-case text-subtle">
                  {skillContentBytes(content).toLocaleString()} /{' '}
                  {MAX_SKILL_CONTENT_BYTES.toLocaleString()} B
                </span>
                <span className="inline-flex rounded-lg border border-border bg-raised/40 p-0.5">
                  {(
                    [
                      { id: false, label: 'Edit' },
                      { id: true, label: 'Preview' },
                    ] as const
                  ).map((option) => (
                    <button
                      key={option.label}
                      type="button"
                      onClick={() => setPreview(option.id)}
                      className={`rounded-md px-2.5 py-1 text-xs font-semibold transition-colors ${
                        preview === option.id
                          ? 'bg-accent-soft text-accent'
                          : 'text-muted hover:text-foreground'
                      }`}
                    >
                      {option.label}
                    </button>
                  ))}
                </span>
              </span>
            </span>
            {preview ? (
              <div className="md-preview min-h-64 w-full overflow-y-auto rounded-md border border-border bg-canvas px-4 py-3 scrollbar-thin">
                {content.trim() ? (
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>
                    {content}
                  </ReactMarkdown>
                ) : (
                  <p className="text-sm text-subtle">Nothing to preview yet.</p>
                )}
              </div>
            ) : (
              <textarea
                value={content}
                onChange={(event) => setContent(event.target.value)}
                rows={12}
                placeholder={'You are a PDF processing expert. When asked to extract content from a PDF:\n\n1. Run the extraction step\n2. Review the output\n3. Summarize the findings'}
                className="min-h-64 w-full resize-y rounded-md border border-border bg-canvas px-3 py-2.5 text-[13px] leading-relaxed text-foreground outline-none transition-colors placeholder:text-subtle focus:border-accent/50 scrollbar-thin"
              />
            )}
            <p className="mt-1.5 text-[11px] text-subtle">
              Write in markdown and flip to Preview to see it rendered, just
              like knowledge notes. No markdown files needed.
            </p>
          </div>
        </div>
      )}
    </Dialog>
  )
}

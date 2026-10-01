import { useEffect, useState } from 'react'
import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { Dialog } from '../ui/Dialog'
import { Button } from '../ui/Button'
import { useApiClient } from '../../lib/api'
import {
  FEEDBACK_REASONS,
  submitFeedback,
  type Feedback,
  type FeedbackInput,
  type FeedbackValue,
} from '../../lib/feedback'

type RunFeedbackProps = {
  runId: string
  feedback?: Feedback | null
  traceId?: string | null
  conversationId?: number
  agentId?: string
  onChange?: (feedback: Feedback) => void
}

/** Thumbs up/down with a details dialog (predefined reasons + free text). */
export function RunFeedback({
  runId,
  feedback = null,
  traceId,
  conversationId,
  agentId,
  onChange,
}: RunFeedbackProps) {
  const api = useApiClient()
  const [value, setValue] = useState<FeedbackValue | null>(feedback?.value ?? null)
  const [comment, setComment] = useState(feedback?.comment ?? '')
  const [categories, setCategories] = useState<string[]>(feedback?.categories ?? [])
  const [open, setOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setValue(feedback?.value ?? null)
    setComment(feedback?.comment ?? '')
    setCategories(feedback?.categories ?? [])
  }, [feedback])

  async function persist(input: FeedbackInput) {
    setSaving(true)
    try {
      const saved = await submitFeedback(api, runId, input)
      onChange?.(saved)
    } catch {
      // Feedback is best-effort; keep the optimistic local state.
    } finally {
      setSaving(false)
    }
  }

  function pick(next: FeedbackValue) {
    if (value === next) {
      // Toggling the same thumb off clears the feedback.
      setValue(null)
      setComment('')
      setCategories([])
      void persist({ value: null, traceId })
      return
    }
    setValue(next)
    setOpen(true)
  }

  function toggleCategory(category: string) {
    setCategories((current) =>
      current.includes(category)
        ? current.filter((entry) => entry !== category)
        : [...current, category],
    )
  }

  async function save() {
    await persist({ value, comment, categories, traceId, conversationId, agentId })
    setOpen(false)
  }

  async function clear() {
    setValue(null)
    setComment('')
    setCategories([])
    await persist({ value: null, traceId })
    setOpen(false)
  }

  const reasons = value ? FEEDBACK_REASONS[value] : []

  return (
    <>
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          aria-label="Good response"
          title="Good response"
          onClick={() => pick('up')}
          className={`rounded-md p-1 transition-colors ${
            value === 'up' ? 'text-success' : 'text-subtle hover:text-foreground'
          }`}
        >
          <ThumbsUp className="size-3.5" strokeWidth={1.9} />
        </button>
        <button
          type="button"
          aria-label="Bad response"
          title="Bad response"
          onClick={() => pick('down')}
          className={`rounded-md p-1 transition-colors ${
            value === 'down' ? 'text-accent' : 'text-subtle hover:text-foreground'
          }`}
        >
          <ThumbsDown className="size-3.5" strokeWidth={1.9} />
        </button>
      </div>

      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={value === 'down' ? 'What went wrong?' : 'What went well?'}
        description="Optional details help improve this agent."
        size="md"
        footer={
          <>
            <Button variant="ghost" size="sm" onClick={clear} disabled={saving}>
              Clear
            </Button>
            <Button size="sm" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {reasons.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {reasons.map((reason) => {
                const on = categories.includes(reason)
                return (
                  <button
                    key={reason}
                    type="button"
                    onClick={() => toggleCategory(reason)}
                    className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      on
                        ? 'border-accent bg-accent-soft text-accent'
                        : 'border-border text-muted hover:text-foreground'
                    }`}
                  >
                    {reason}
                  </button>
                )
              })}
            </div>
          ) : null}
          <textarea
            value={comment}
            onChange={(event) => setComment(event.target.value)}
            rows={4}
            maxLength={2000}
            placeholder="Add any details (optional)…"
            className="w-full resize-none rounded-lg border border-border bg-canvas px-3 py-2 text-[13px] text-foreground placeholder:text-subtle focus:border-accent/50 focus:outline-none"
          />
        </div>
      </Dialog>
    </>
  )
}

import { useState } from 'react'
import { Check, ThumbsDown, ThumbsUp } from 'lucide-react'

import type { AiAssistantFeedbackValue } from '../../lib/ai-assistant'

/**
 * AI Assistant's thumb control.
 *
 * Only rendered for a **signed-in** caller on a settled answer: a guest's rating
 * has no account to attach to and is discarded server-side, so offering one would
 * be a lie. The thumb registers on click (an optimistic mark that does not seem
 * to take gets pressed twice) and the optional note — offered on a 👎, where the
 * "why" is what actually helps — updates the same item, because feedback is keyed
 * by `runId` and the write is an upsert.
 */
export function AiAssistantFeedback({
  feedback,
  onRate,
}: {
  feedback?: { value: AiAssistantFeedbackValue; comment?: string }
  onRate: (value: AiAssistantFeedbackValue, comment?: string) => void
}) {
  const [noteOpen, setNoteOpen] = useState(false)
  const [note, setNote] = useState(feedback?.comment ?? '')

  const pick = (value: AiAssistantFeedbackValue) => {
    // Keep an existing note when re-affirming the same thumb; drop it when the
    // verdict flips, since "what was wrong" no longer applies to a 👍.
    onRate(value, value === feedback?.value ? (feedback?.comment ?? '') : '')
    if (value === 'down') setNoteOpen(true)
  }

  const sendNote = () => {
    if (!feedback?.value) return
    onRate(feedback.value, note.trim())
    setNoteOpen(false)
  }

  const buttonClass = (active: boolean) =>
    `grid size-6 place-items-center rounded-md transition-colors focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none ${
      active ? 'bg-raised text-accent' : 'text-muted hover:bg-raised hover:text-foreground'
    }`

  return (
    <div className="mt-1.5">
      <div className="flex items-center gap-0.5">
        <button
          type="button"
          aria-label="Good answer"
          title="Good answer"
          aria-pressed={feedback?.value === 'up'}
          onClick={() => pick('up')}
          className={buttonClass(feedback?.value === 'up')}
        >
          <ThumbsUp className="size-3.5" strokeWidth={1.9} />
        </button>
        <button
          type="button"
          aria-label="Bad answer"
          title="Bad answer"
          aria-pressed={feedback?.value === 'down'}
          onClick={() => pick('down')}
          className={buttonClass(feedback?.value === 'down')}
        >
          <ThumbsDown className="size-3.5" strokeWidth={1.9} />
        </button>
        {feedback?.value && !noteOpen && (
          <span className="ml-1 inline-flex items-center gap-1 text-[10.5px] text-muted">
            <Check className="size-3 text-accent" />
            Thanks
            {!feedback.comment && (
              <button
                type="button"
                onClick={() => setNoteOpen(true)}
                className="text-accent hover:underline"
              >
                · add a note
              </button>
            )}
          </span>
        )}
      </div>

      {noteOpen && (
        <div className="mt-1.5 flex items-end gap-1.5">
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            rows={2}
            maxLength={500}
            placeholder="What was wrong? (optional)"
            aria-label="Feedback note"
            className="scrollbar-thin max-h-24 min-h-8 flex-1 resize-none rounded-lg border border-border-strong bg-transparent px-2 py-1 text-[11.5px] leading-relaxed text-foreground placeholder:text-muted focus-visible:border-accent/60 focus-visible:outline-none"
          />
          <button
            type="button"
            onClick={sendNote}
            className="h-8 shrink-0 rounded-md border border-border-strong px-2 text-[11.5px] font-medium text-foreground transition-colors hover:border-accent/50 hover:text-accent"
          >
            Send
          </button>
        </div>
      )}
    </div>
  )
}

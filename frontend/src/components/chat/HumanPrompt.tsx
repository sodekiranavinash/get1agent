import { useState } from 'react'
import { MessageCircleQuestion, Send } from 'lucide-react'
import { Button } from '../ui/Button'
import type { ChatQuestion } from '../../lib/chat'

/**
 * A Copilot-style clarifying-question card.
 *
 * The agent pauses mid-run to ask the user; they pick an option or type their
 * own answer. Once answered the card shows what was chosen and the run resumes.
 */
export function HumanPrompt({
  question,
  disabled,
  onSubmit,
}: {
  question: ChatQuestion
  disabled?: boolean
  onSubmit: (answer: string) => void
}) {
  const [custom, setCustom] = useState('')
  const answered = Boolean(question.answer)

  return (
    <div className="rounded-xl border border-accent/30 bg-accent-soft/40 p-3">
      <div className="flex items-start gap-2.5">
        <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-md bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
          <MessageCircleQuestion className="size-3.5" strokeWidth={1.9} />
        </span>

        <div className="min-w-0 flex-1 space-y-2.5">
          <p className="text-[12.5px] leading-snug font-medium text-foreground">
            {question.question}
          </p>

          {answered ? (
            <p className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-[12px] text-muted">
              {question.answer}
            </p>
          ) : (
            <>
              {question.options.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {question.options.map((option) => (
                    <button
                      key={option}
                      type="button"
                      disabled={disabled}
                      onClick={() => onSubmit(option)}
                      className="rounded-lg border border-border bg-surface px-2.5 py-1.5 text-left text-[12px] font-medium text-foreground transition-colors hover:border-accent/40 hover:bg-raised disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {option}
                    </button>
                  ))}
                </div>
              ) : null}

              {question.allowCustom ? (
                <div className="flex items-center gap-2">
                  <input
                    value={custom}
                    disabled={disabled}
                    onChange={(event) => setCustom(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' && custom.trim() && !disabled) {
                        event.preventDefault()
                        onSubmit(custom.trim())
                      }
                    }}
                    placeholder="Or type your own answer…"
                    className="h-8 min-w-0 flex-1 rounded-md border border-border bg-canvas px-2.5 text-[12px] text-foreground outline-none placeholder:text-subtle focus:border-accent/50 disabled:opacity-60"
                  />
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<Send className="size-3.5" />}
                    disabled={disabled || !custom.trim()}
                    onClick={() => onSubmit(custom.trim())}
                  >
                    Answer
                  </Button>
                </div>
              ) : null}

              <p className="text-[10.5px] text-subtle">
                The agent paused for your input. Turn on Auto-approve to let it assume the best
                option instead.
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { ArrowRight, GitCompareArrows, Loader2, RotateCcw, Send, Sparkles } from 'lucide-react'

import { Button } from '../ui/Button'
import { lineDiffStats, type PlaygroundMessage } from '../../lib/playground'

const EXAMPLE_PROMPTS = [
  'A tool that converts a temperature between Celsius, Fahrenheit and Kelvin',
  'Summarize a block of text into at most 3 bullet points',
  'Validate and normalize an email address, returning the domain',
]

function ChangeCard({
  message,
  onReview,
}: {
  message: PlaygroundMessage
  onReview: (message: PlaygroundMessage) => void
}) {
  const generated = message.generated!
  const stats = lineDiffStats(message.baseCode ?? '', generated.code)
  return (
    <div className="mt-2 overflow-hidden rounded-xl border border-border bg-surface">
      <button
        type="button"
        onClick={() => onReview(message)}
        className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-raised/60"
      >
        <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent">
          <GitCompareArrows className="size-4" strokeWidth={1.9} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-[12px] font-medium text-foreground">
            {generated.name}
          </span>
          <span className="mt-0.5 flex items-center gap-2 text-[11px]">
            <span className="text-success">+{stats.added}</span>
            <span className="text-rose">-{stats.removed}</span>
            <span className="text-subtle">view changes</span>
          </span>
        </span>
        <ArrowRight className="size-3.5 shrink-0 text-subtle" />
      </button>
    </div>
  )
}

export function PlaygroundChat({
  messages,
  sending,
  disabled,
  disabledHint,
  onSend,
  onReview,
  onRestore,
}: {
  messages: PlaygroundMessage[]
  sending: boolean
  disabled: boolean
  disabledHint?: string
  onSend: (prompt: string) => void
  onReview: (message: PlaygroundMessage) => void
  /** Restore the editor to the code captured before a given change. */
  onRestore: (message: PlaygroundMessage) => void
}) {
  const [value, setValue] = useState('')
  const scrollRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const element = scrollRef.current
    if (element) element.scrollTop = element.scrollHeight
  }, [messages, sending])

  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, 160)}px`
  }, [value])

  const canSend = value.trim().length > 0 && !disabled && !sending
  const submit = () => {
    if (!canSend) return
    onSend(value.trim())
    setValue('')
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div ref={scrollRef} className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        {messages.length === 0 && !sending ? (
          <div className="flex h-full flex-col items-center justify-center px-4 text-center">
            <span className="flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
              <Sparkles className="size-5" strokeWidth={1.75} />
            </span>
            <p className="mt-3 text-[13px] font-medium text-foreground">
              Describe the tool you want
            </p>
            <p className="mt-1 max-w-xs text-[11.5px] leading-relaxed text-subtle">
              AI writes the Python, then you refine it by chatting. Every change shows up as a
              diff you can accept or discard.
            </p>
            <div className="mt-4 flex w-full max-w-sm flex-col gap-1.5">
              {EXAMPLE_PROMPTS.map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => setValue(example)}
                  className="rounded-lg border border-border bg-raised/40 px-3 py-2 text-left text-[11.5px] leading-snug text-muted transition-colors hover:border-border-strong hover:text-foreground"
                >
                  {example}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        {messages.map((message) =>
          message.role === 'user' ? (
            <div key={message.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-accent px-3.5 py-2 text-[12.5px] leading-relaxed whitespace-pre-wrap text-white shadow-control">
                {message.text}
              </div>
            </div>
          ) : (
            <div key={message.id} className="flex gap-2.5">
              <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft font-mono text-[11px] font-semibold text-accent ring-1 ring-inset ring-accent/20">
                AI
              </span>
              <div className="min-w-0 flex-1 pt-0.5">
                {message.status === 'error' ? (
                  <div className="rounded-lg border border-warning/30 bg-warning-soft/50 px-3 py-2 text-[12px] leading-relaxed text-warning">
                    {message.text}
                  </div>
                ) : message.status === 'generating' ? (
                  <p className="flex items-center gap-2 pt-1.5 text-[12px] text-subtle">
                    <Loader2 className="size-3.5 animate-spin" />
                    Writing the tool…
                  </p>
                ) : (
                  <>
                    <p className="text-[12.5px] leading-relaxed text-muted">{message.text}</p>
                    {message.generated ? (
                      <>
                        <ChangeCard message={message} onReview={onReview} />
                        {message.baseCode !== undefined ? (
                          <button
                            type="button"
                            onClick={() => onRestore(message)}
                            title="Restore the code to before this change"
                            className="mt-1.5 inline-flex items-center gap-1 rounded-md border border-transparent px-1.5 py-0.5 text-[11px] text-subtle transition-colors hover:border-border hover:bg-raised hover:text-foreground"
                          >
                            <RotateCcw className="size-3" />
                            Restore checkpoint
                          </button>
                        ) : null}
                      </>
                    ) : null}
                  </>
                )}
              </div>
            </div>
          ),
        )}

        {sending ? (
          <div className="flex gap-2.5">
            <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
              <Loader2 className="size-3.5 animate-spin" />
            </span>
            <p className="pt-1.5 text-[12px] text-subtle">Writing the tool…</p>
          </div>
        ) : null}
      </div>

      <div className="shrink-0 border-t border-border/60 p-3">
        {disabled && disabledHint ? (
          <p className="mb-2 rounded-md bg-raised/60 px-2.5 py-1.5 text-[11px] text-subtle">
            {disabledHint}
          </p>
        ) : null}
        <div className="rounded-xl border border-border-strong/70 bg-canvas transition-colors focus-within:border-accent/50 focus-within:ring-2 focus-within:ring-accent/15">
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault()
                submit()
              }
            }}
            disabled={disabled}
            placeholder={disabled ? disabledHint ?? 'Finish reviewing first…' : 'Describe a change…'}
            className="scrollbar-thin max-h-40 w-full resize-none bg-transparent px-3 py-2.5 text-[12.5px] leading-relaxed text-foreground outline-none placeholder:text-subtle disabled:opacity-60"
          />
          <div className="flex items-center justify-end px-2 pb-2">
            <Button
              size="sm"
              onClick={submit}
              disabled={!canSend}
              icon={sending ? <Loader2 className="size-3.5 animate-spin" /> : <Send className="size-3.5" />}
            >
              {sending ? 'Working' : 'Send'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

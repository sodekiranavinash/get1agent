import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ExternalLink, User } from 'lucide-react'

import { AiAssistantMark } from './AiAssistantMark'

import { AiAssistantFeedback } from './AiAssistantFeedback'
import { ChatAnswer } from '../chat/ChatAnswer'
import type { AiAssistantFeedbackValue, AviStage, AviWidgetTurn } from '../../lib/ai-assistant'

/**
 * One AI Assistant turn: the user's question, then the answer as it streams.
 *
 * Both sides carry an avatar — a **user** mark on the question, the **AI** mark on
 * the answer — so who said what is legible at a glance without relying on colour
 * or alignment alone.
 *
 * The answer renders through the **same** `ChatAnswer` the chat screen uses, so
 * markdown, inline `[n]` citation badges and streaming caret behave identically
 * without a second renderer to maintain — in its `compact` form, because the
 * widget is ~380px wide and the wide-surface format header is just noise there.
 */

/** A source's in-app route; sources are documentation pages, never off-site. */
function routeFor(source: { route?: unknown; url?: unknown }): string {
  const raw = String(source.route || source.url || '').trim()
  return raw.startsWith('/') ? raw : ''
}

/**
 * The shape of the coming answer: three lines of pills that fill the **full
 * width**, one line at a time, then clear together and start again.
 *
 * Weights rather than pixel widths, because the pills have to span whatever the
 * panel is — 380px on a desktop sheet, the whole screen on a phone — while still
 * looking like words of different lengths.
 */
const LOADING_ROWS: number[][] = [
  [3, 2, 4, 2],
  [2, 4, 3],
  [4, 2, 3, 2],
]

/** How many tints the theme provides (see `.ai-assistant-pill[data-tint]`). */
const PILL_TINTS = 5

/**
 * Every pill in reading order, with the tint it lights up in.
 *
 * Built once at module scope: the running index is what keeps the fill
 * continuous *across* rows (line 2 picks up where line 1 stopped), and deriving
 * it while rendering would be a mutation during render.
 */
const LOADING_PILLS: { weight: number; tint: number; order: number }[][] = (() => {
  let order = 0
  return LOADING_ROWS.map((row, rowIndex) =>
    row.map((weight, index) => ({
      weight,
      tint: (rowIndex + index) % PILL_TINTS,
      order: order++,
    })),
  )
})()

const PILL_COUNT = LOADING_PILLS.reduce((total, row) => total + row.length, 0)

/** One pill per beat, then a hold while the block is full, then a beat of rest. */
const PILL_STEP_MS = 130
const PILL_HOLD_MS = 550
const PILL_GAP_MS = 180

/**
 * How many pills are lit, advancing one per beat and then dropping to zero.
 *
 * The sequence lives here rather than in CSS because the behaviour is
 * asymmetric — **fill one at a time, clear all at once** — and a CSS
 * `animation-delay` cannot express that: it staggers the `off` as well as the
 * `on`, so the pills drained one by one and the block never looked like it was
 * filling. Only the colour change is CSS.
 */
function useFillProgress(count: number): number {
  const [lit, setLit] = useState(0)

  useEffect(() => {
    let timer = 0
    let next = 0

    const schedule = (delay: number) => {
      timer = window.setTimeout(tick, delay)
    }

    const tick = () => {
      if (next >= count) {
        // Full: hold, then clear the whole block in one step and start over.
        next = 0
        setLit(0)
        schedule(PILL_GAP_MS)
        return
      }
      next += 1
      setLit(next)
      schedule(next >= count ? PILL_HOLD_MS : PILL_STEP_MS)
    }

    schedule(PILL_STEP_MS)
    return () => window.clearTimeout(timer)
  }, [count])

  return lit
}

function ThinkingSkeleton({ stages }: { stages: AviStage[] }) {
  const lit = useFillProgress(PILL_COUNT)

  return (
    <div className="space-y-3" role="status" aria-live="polite">
      {stages.length > 0 && (
        <ol>
          {stages.map((stage, index) => {
            const active = index === stages.length - 1
            const text = stage.detail ? `${stage.label} · ${stage.detail}` : stage.label
            return (
              // Every step stays mounted so it can animate *out*; only the newest
              // holds space. React cannot animate an unmounted element, and a
              // timer to unmount it would be state we do not need.
              <li
                key={`${stage.key}-${index}`}
                aria-hidden={!active}
                className={`ai-assistant-event overflow-hidden transition-all duration-300 ease-out ${
                  active ? 'max-h-6 opacity-100' : 'max-h-0 -translate-y-1 opacity-0'
                }`}
              >
                <div className="flex items-start gap-1.5 text-[11.5px] leading-snug">
                  <span
                    aria-hidden
                    className="mt-[5px] size-1.5 shrink-0 animate-pulse rounded-full bg-accent"
                  />
                  <span className="min-w-0 truncate text-foreground" title={text}>
                    {stage.label}
                    {stage.detail && <span className="text-subtle"> · {stage.detail}</span>}
                  </span>
                </div>
              </li>
            )
          })}
        </ol>
      )}
      <div className="w-full space-y-2" aria-hidden>
        {LOADING_PILLS.map((row, rowIndex) => (
          <div key={rowIndex} className="flex w-full items-center gap-1.5">
            {row.map((pill, index) => (
              <span
                key={index}
                data-lit={pill.order < lit}
                data-tint={pill.tint}
                style={{ flex: pill.weight }}
                className="ai-assistant-pill h-2 rounded-full"
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

export function AiAssistantMessage({
  turn,
  onExample,
  canRate,
  onRate,
}: {
  turn: AviWidgetTurn
  onExample: (question: string) => void
  /** Signed-in only; a guest's rating has nowhere to go. */
  canRate: boolean
  onRate: (value: AiAssistantFeedbackValue, comment?: string) => void
}) {
  const { run, intent, question } = turn
  const refused = intent?.kind === 'off_topic' || intent?.kind === 'unsafe'
  const streaming = run.status === 'streaming'
  const examples = intent?.examples ?? []
  const settled = !streaming && run.status !== 'error' && Boolean(run.runId)

  return (
    <div className="space-y-3">
      {/* The question, with the user's mark on the outside. */}
      <div className="flex items-start justify-end gap-2">
        <p className="max-w-[82%] rounded-lg rounded-br-sm bg-accent px-3 py-1.5 text-[12.5px] leading-snug break-words text-white">
          {question}
        </p>
        <span
          className="mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border border-border bg-raised text-muted"
          title="You"
          aria-label="You"
        >
          <User className="size-3" />
        </span>
      </div>

      {/* The answer, with AI Assistant's mark on the outside. */}
      <div className="flex items-start gap-2">
        <AiAssistantMark className="mt-0.5 size-6 rounded-md" />
        <div className="min-w-0 flex-1 pt-0.5">
          {run.answer ? (
            <ChatAnswer
              content={run.answer}
              format="markdown"
              status={run.status}
              turnId={turn.id}
              compact
            />
          ) : streaming ? (
            <ThinkingSkeleton stages={turn.stages ?? []} />
          ) : run.status === 'stopped' ? (
            <p className="text-[12.5px] text-muted">Stopped.</p>
          ) : run.status === 'error' ? (
            <p className="text-[12.5px] text-warning">
              {run.error || 'I could not answer that one.'}
            </p>
          ) : (
            <p className="text-[12.5px] text-muted">
              I couldn&apos;t put an answer together for that one. Try asking it another way.
            </p>
          )}

          {/* Example questions on a refusal: one tap re-asks, which is what makes
              a decline a way forward rather than a dead end. */}
          {refused && !streaming && examples.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {examples.slice(0, 4).map((example) => (
                <button
                  key={example}
                  type="button"
                  onClick={() => onExample(example)}
                  className="rounded-full border border-border-strong px-2.5 py-1 text-left text-[11.5px] text-foreground transition-colors hover:border-accent/50 hover:bg-raised hover:text-accent focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
                >
                  {example}
                </button>
              ))}
            </div>
          )}

          {/* Sources, labelled by what they are. A citation used to be a bare
              title with a number that matched nothing in this widget, so a live
              app page and a documentation section looked identical and the reader
              had no way to tell which one they were about to open. */}
          {!streaming && (run.sources?.length ?? 0) > 0 && (
            <ul className="mt-2 space-y-1">
              {run.sources.slice(0, 5).map((source, index) => {
                const path = routeFor(source) || '/docs'
                const isDocs = path.startsWith('/docs')
                const label =
                  source.title || (isDocs ? 'Documentation' : 'Platform page')
                return (
                  <li key={`${source.index ?? index}-${label}`} className="text-[11.5px]">
                    <Link
                      to={path}
                      title={path}
                      className="inline-flex max-w-full items-center gap-1.5 rounded-md px-1 py-0.5 text-muted transition-colors hover:bg-raised hover:text-accent"
                    >
                      <span
                        className={`shrink-0 rounded px-1 py-px text-[9px] font-semibold tracking-wide uppercase ${
                          isDocs ? 'bg-info-soft text-info' : 'bg-accent-soft text-accent'
                        }`}
                      >
                        {isDocs ? 'Docs' : 'Page'}
                      </span>
                      <span className="truncate">{label}</span>
                      <ExternalLink className="size-3 shrink-0 opacity-60" />
                    </Link>
                  </li>
                )
              })}
            </ul>
          )}

          {canRate && settled && <AiAssistantFeedback feedback={turn.feedback} onRate={onRate} />}
        </div>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Bot, Check, Database, FileText, Globe, Loader2, Sparkles } from 'lucide-react'

type Step = {
  id: string
  kind: 'plan' | 'tool' | 'answer'
  label: string
  detail: string
  duration: string
  icon: LucideIcon
}

const STEPS: Step[] = [
  {
    id: 'plan',
    kind: 'plan',
    label: 'Planning',
    detail: '2 sub-queries · 3 tool steps',
    duration: '0.6s',
    icon: Sparkles,
  },
  {
    id: 'kb',
    kind: 'tool',
    label: 'search-user-knowledge-bases',
    detail: '6 chunks · 3 knowledge bases',
    duration: '0.9s',
    icon: Database,
  },
  {
    id: 'web',
    kind: 'tool',
    label: 'web-search',
    detail: '5 results · highlights only',
    duration: '1.1s',
    icon: Globe,
  },
  {
    id: 'answer',
    kind: 'answer',
    label: 'Compose the answer',
    detail: 'grounded · cited',
    duration: '2.3s',
    icon: Sparkles,
  },
]

const SOURCES = [
  { icon: FileText, title: 'q3-release-notes.pdf', meta: 'page 4' },
  { icon: Globe, title: 'marketwatch.com', meta: 'Q3 earnings' },
]

function Citation({ n }: { n: number }) {
  return (
    <span className="mx-0.5 inline-flex size-4 items-center justify-center rounded-full bg-accent-soft align-middle text-[9px] font-semibold text-accent">
      {n}
    </span>
  )
}

/**
 * Self-playing agent run — planning, knowledge + web tool calls, a typed answer
 * with citations, then its sources and context meter. Decorative: cycles on a
 * timer and loops.
 */
export function AgentRunPreview() {
  const [active, setActive] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(
      () => setActive((current) => (current >= STEPS.length ? 0 : current + 1)),
      1900,
    )
    return () => window.clearInterval(timer)
  }, [])

  const done = active >= STEPS.length
  const answerIndex = STEPS.length - 1
  const answerStarted = active >= answerIndex
  const contextPct = done ? 68 : Math.min(66, 18 + active * 14)

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/70 to-transparent"
      />

      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-violet text-white shadow-control">
            <Bot className="size-4" />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[12.5px] leading-tight font-semibold text-foreground">
              research-agent
            </span>
            <span className="block truncate font-mono text-[10.5px] text-subtle">
              Nova 2 Lite · run 8f3a19
            </span>
          </span>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${
            done
              ? 'border-success/40 bg-success-soft text-success'
              : 'border-accent/40 bg-accent-soft text-accent'
          }`}
        >
          <span className="relative flex size-1.5">
            {!done ? (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-70" />
            ) : null}
            <span
              className={`relative inline-flex size-1.5 rounded-full ${done ? 'bg-success' : 'bg-accent'}`}
            />
          </span>
          {done ? 'Complete' : 'Streaming'}
        </span>
      </div>

      {/* Timeline */}
      <div className="mt-4 space-y-1.5">
        {STEPS.map((step, index) => {
          const isDone = done || index < active
          const isActive = !done && index === active
          const Icon = step.icon
          return (
            <div
              key={step.id}
              className={[
                'flex items-center gap-3 rounded-xl border px-3 py-2 transition-all duration-300',
                isActive
                  ? 'border-accent/40 bg-accent-soft'
                  : done || index < active
                    ? 'border-transparent bg-raised/40'
                    : 'border-transparent opacity-45',
              ].join(' ')}
            >
              <span
                className={[
                  'flex size-7 shrink-0 items-center justify-center rounded-lg border bg-canvas',
                  isActive
                    ? 'border-accent/40 text-accent'
                    : isDone
                      ? 'border-success/40 text-success'
                      : 'border-border text-muted',
                ].join(' ')}
              >
                {isActive ? (
                  <Loader2 className="size-3.5 animate-spin" />
                ) : isDone ? (
                  <Check className="size-3.5" />
                ) : (
                  <Icon className="size-3.5" />
                )}
              </span>

              <span className="min-w-0 flex-1">
                <span className="flex items-center justify-between gap-2">
                  <span className="truncate font-mono text-[11.5px] text-foreground">
                    {step.label}
                  </span>
                  {isDone || isActive ? (
                    <span className="shrink-0 font-mono text-[10px] text-subtle">
                      {step.duration}
                    </span>
                  ) : null}
                </span>
                {isActive || isDone ? (
                  <span className="mt-0.5 block truncate text-[10.5px] text-subtle">
                    {step.detail}
                  </span>
                ) : null}
              </span>
            </div>
          )
        })}
      </div>

      {/* Answer (reserves space, types out when reached) */}
      <div className="mt-2 min-h-[58px] rounded-xl border border-border bg-canvas/60 p-3">
        <p
          className={`text-[12px] leading-relaxed text-foreground ${
            answerStarted ? 'animate-reveal-x' : 'invisible'
          }`}
        >
          Q3 revenue grew 18% QoQ to $4.2M, led by Northwind <Citation n={1} />.
          Retention held at 94% <Citation n={2} />.
        </p>
      </div>

      {/* Sources (reserve space, fade in when the run completes) */}
      <div className="mt-2 grid min-h-[52px] grid-cols-2 gap-2">
        {SOURCES.map(({ icon: Icon, title, meta }, index) => (
          <div
            key={title}
            className={`flex items-center gap-2 rounded-lg border border-border bg-canvas/60 px-2.5 py-2 ${
              done ? 'animate-rise' : 'opacity-0'
            }`}
            style={done ? { animationDelay: `${index * 90}ms` } : undefined}
          >
            <span className="flex size-6 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
              <Icon className="size-3" />
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[11px] font-medium text-foreground">
                {title}
              </span>
              <span className="block truncate text-[10px] text-subtle">{meta}</span>
            </span>
          </div>
        ))}
      </div>

      {/* Context meter */}
      <div className="mt-3 border-t border-border pt-3">
        <div className="flex items-center justify-between text-[10.5px] text-subtle">
          <span>Context</span>
          <span className="font-mono">{done ? '87k' : '—'} / 128k</span>
        </div>
        <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-raised">
          <span
            className="block h-full rounded-full bg-gradient-to-r from-accent via-violet to-teal transition-[width] duration-700 ease-out"
            style={{ width: `${contextPct}%` }}
          />
        </span>
      </div>
    </div>
  )
}

import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Activity,
  Coins,
  Database,
  Globe,
  Hash,
  ListTree,
  Link2,
  RotateCcw,
  Sparkles,
  ThumbsUp,
  Timer,
  Wrench,
} from 'lucide-react'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useInView } from '../../hooks/useInView'

type Span = {
  name: string
  kind: 'root' | 'span' | 'tool' | 'gen'
  /** Timeline geometry in percent of the run. */
  left: number
  width: number
  ms: string
  icon: LucideIcon
  /** Event logged as this span starts streaming. */
  event: string
}

const SPANS: Span[] = [
  {
    name: 'run · research-agent',
    kind: 'root',
    left: 0,
    width: 100,
    ms: '4.2s',
    icon: Activity,
    event: 'run.started · agent=research-agent',
  },
  {
    name: 'plan',
    kind: 'span',
    left: 0,
    width: 14,
    ms: '0.6s',
    icon: ListTree,
    event: 'plan · 2 sub-queries · 3 tool calls',
  },
  {
    name: 'search-user-knowledge-bases',
    kind: 'tool',
    left: 14,
    width: 22,
    ms: '0.9s',
    icon: Database,
    event: 'tool.start · search-user-knowledge-bases',
  },
  {
    name: 'web-search',
    kind: 'tool',
    left: 36,
    width: 26,
    ms: '1.1s',
    icon: Globe,
    event: 'tool.result · 5 results · highlights',
  },
  {
    name: 'generation · deepseek.v3.2',
    kind: 'gen',
    left: 62,
    width: 38,
    ms: '2.3s',
    icon: Sparkles,
    event: 'generation · deepseek.v3.2 · 6.4k tokens',
  },
]

const KIND_STYLE: Record<Span['kind'], string> = {
  root: 'bg-accent',
  span: 'bg-violet',
  tool: 'bg-teal',
  gen: 'bg-info',
}

const STATS = [
  { icon: Timer, label: 'Latency', value: '4.2s' },
  { icon: Hash, label: 'Tokens', value: '7.6k' },
  { icon: Coins, label: 'Cost', value: '$0.004' },
  { icon: ThumbsUp, label: 'Feedback', value: '+1' },
]

const LAST_EVENT = 'run.completed · 4.2s · answer cited [1][2]'

/**
 * A live trace waterfall — the OpenTelemetry run the runtime exports to
 * CloudWatch and X-Ray, replayed span by span. The playhead sweeps the timeline
 * as each observation starts, the event log narrates the span, and the run ends
 * as a shareable, public trace. Loops while in view.
 */
export function TracePreview() {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 })
  // Under reduced motion the trace is simply shown complete.
  const [step, setStep] = useState(() => (reduced ? SPANS.length : 0))

  useEffect(() => {
    if (reduced || !inView) return
    let cancelled = false
    let handle = 0
    let current = 0
    const run = () => {
      if (cancelled) return
      current += 1
      if (current > SPANS.length) {
        handle = window.setTimeout(() => {
          if (cancelled) return
          current = 0
          setStep(0)
          handle = window.setTimeout(run, 500)
        }, 2600)
        return
      }
      setStep(current)
      handle = window.setTimeout(run, 950)
    }
    handle = window.setTimeout(run, 450)
    return () => {
      cancelled = true
      window.clearTimeout(handle)
    }
  }, [inView, reduced])

  const done = step >= SPANS.length
  // Playhead sits at the end of the last revealed span (0 while only `run` is up).
  const lastShown = SPANS[Math.max(step, 1) - 1]
  const progress = step <= 1 ? 0 : Math.min(100, lastShown.left + lastShown.width)
  const activeIndex = done ? -1 : step - 1
  const event = done ? LAST_EVENT : SPANS[Math.max(0, step - 1)]?.event

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Activity className="size-3.5 shrink-0 text-accent" />
          <span className="truncate font-mono text-[12px] text-foreground">
            trace · 8f3a19
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
          {done ? 'Complete' : 'Live'}
        </span>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="rounded-md border border-border bg-canvas/60 px-1.5 py-0.5 font-mono text-[9.5px] text-subtle">
          research-agent
        </span>
        <span className="rounded-md border border-border bg-canvas/60 px-1.5 py-0.5 font-mono text-[9.5px] text-subtle">
          deepseek.v3.2
        </span>
        <span className="inline-flex items-center gap-1 rounded-md border border-success/40 bg-success-soft px-1.5 py-0.5 text-[9.5px] font-medium text-success">
          <Link2 className="size-2.5" />
          public link
        </span>
      </div>

      {/* Waterfall */}
      <div className="mt-4 flex gap-3">
        <div className="flex w-[5.5rem] shrink-0 flex-col gap-2 sm:w-28">
          {SPANS.map((span, index) => {
            const visible = index < step
            const Icon = span.icon
            return (
              <div
                key={span.name}
                className={`flex h-5 items-center justify-between gap-1 transition-opacity duration-300 ${
                  visible ? 'opacity-100' : 'opacity-40'
                }`}
              >
                <span className="flex min-w-0 items-center gap-1.5">
                  <span className="flex size-3.5 shrink-0 items-center justify-center text-subtle">
                    <Icon className="size-3" />
                  </span>
                  <span
                    className="truncate text-[10.5px] text-foreground"
                    title={span.name}
                  >
                    {span.name.replace(' · ', '·')}
                  </span>
                </span>
                <span className="shrink-0 font-mono text-[9.5px] text-subtle">
                  {visible ? span.ms : ''}
                </span>
              </div>
            )
          })}
        </div>

        <div className="relative flex-1">
          <div className="flex flex-col gap-2">
            {SPANS.map((span, index) => {
              const visible = index < step
              const active = index === activeIndex
              return (
                <div key={span.name} className="flex h-5 items-center">
                  <span className="relative h-2 w-full overflow-hidden rounded-full bg-raised/70">
                    <span
                      className={`absolute inset-y-0 rounded-full ${KIND_STYLE[span.kind]} transition-all duration-500 ease-out ${
                        active ? 'animate-pulse' : ''
                      }`}
                      style={{
                        left: visible ? `${span.left}%` : '0%',
                        width: visible ? `${span.width}%` : '0%',
                      }}
                    />
                  </span>
                </div>
              )
            })}
          </div>
          {/* Playhead */}
          {!reduced ? (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute -top-1 -bottom-1 w-px bg-accent/70 transition-[left] duration-500 ease-out"
              style={{ left: `${progress}%` }}
            >
              <span className="absolute -top-0.5 -left-[2.5px] size-1.5 rounded-full bg-accent" />
            </span>
          ) : null}
        </div>
      </div>

      {/* Live event log */}
      <div className="mt-3 flex items-center gap-2 overflow-hidden rounded-lg border border-border bg-canvas/70 px-2.5 py-1.5">
        <Wrench className="size-3 shrink-0 text-accent" />
        <span
          key={`${step}-${done}`}
          className="animate-pop min-w-0 truncate font-mono text-[10px] text-muted"
        >
          {event}
        </span>
      </div>

      {/* Stats */}
      <div className="mt-3 grid grid-cols-2 gap-2 border-t border-border pt-3 sm:grid-cols-4">
        {STATS.map(({ icon: Icon, label, value }) => (
          <div key={label} className="flex items-center gap-2">
            <Icon className="size-3.5 shrink-0 text-muted" />
            <span className="min-w-0">
              <span className="block text-[9.5px] tracking-wide text-subtle uppercase">
                {label}
              </span>
              <span className="block truncate text-[11.5px] font-semibold text-foreground">
                {value}
              </span>
            </span>
          </div>
        ))}
      </div>

      <div className="mt-3 flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-canvas/60 px-2 py-1 text-[11px] text-muted">
          <RotateCcw className="size-3" />
          Replay in Playground
        </span>
        <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-canvas/60 px-2 py-1 text-[11px] text-muted">
          <Database className="size-3" />
          Add to dataset
        </span>
      </div>
    </div>
  )
}

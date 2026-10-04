import {
  Activity,
  Coins,
  Database,
  Link2,
  RotateCcw,
  ThumbsUp,
  Timer,
} from 'lucide-react'
import { useInView } from '../../hooks/useInView'

type Span = {
  name: string
  kind: 'root' | 'span' | 'tool' | 'gen'
  left: number
  width: number
  ms: string
  tokens?: string
}

const SPANS: Span[] = [
  { name: 'run', kind: 'root', left: 0, width: 100, ms: '4.2s' },
  { name: 'plan', kind: 'span', left: 0, width: 14, ms: '0.6s', tokens: '1.2k' },
  {
    name: 'tool · search-user-knowledge-bases',
    kind: 'tool',
    left: 14,
    width: 22,
    ms: '0.9s',
  },
  { name: 'tool · web-search', kind: 'tool', left: 36, width: 26, ms: '1.1s' },
  {
    name: 'generation · deepseek.v3.2',
    kind: 'gen',
    left: 62,
    width: 38,
    ms: '2.3s',
    tokens: '6.4k',
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
  { icon: Coins, label: 'Cost', value: '$0.004' },
  { icon: ThumbsUp, label: 'Feedback', value: '+1' },
]

/**
 * A AWS-style (CloudWatch) trace waterfall — the observability surface every run emits.
 * Bars grow in when the section scrolls into view.
 */
export function TracePreview() {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 })

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
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-success/40 bg-success-soft px-2 py-0.5 text-[10.5px] font-semibold text-success">
          <Link2 className="size-3" />
          Public
        </span>
      </div>

      <div className="mt-4 space-y-2.5">
        {SPANS.map((span, index) => (
          <div key={span.name} className="grid grid-cols-[minmax(0,1fr)_3.5rem] items-center gap-3">
            <span className="min-w-0">
              <span className="flex items-baseline justify-between gap-2">
                <span className="truncate font-mono text-[11.5px] text-foreground">
                  {span.name}
                </span>
                {span.tokens ? (
                  <span className="shrink-0 text-[10.5px] text-subtle">{span.tokens}</span>
                ) : null}
              </span>
              <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-raised/70">
                <span
                  className={`block h-full rounded-full ${KIND_STYLE[span.kind]} transition-[width,margin] duration-700 ease-out`}
                  style={{
                    width: inView ? `${span.width}%` : '0%',
                    marginLeft: inView ? `${span.left}%` : '0%',
                    transitionDelay: `${index * 110}ms`,
                  }}
                />
              </span>
            </span>
            <span className="text-right font-mono text-[10.5px] text-subtle">
              {span.ms}
            </span>
          </div>
        ))}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2 border-t border-border pt-3">
        {STATS.map(({ icon: Icon, label, value }) => (
          <div key={label} className="flex items-center gap-2">
            <Icon className="size-3.5 shrink-0 text-muted" />
            <span className="min-w-0">
              <span className="block text-[10px] tracking-wide text-subtle uppercase">
                {label}
              </span>
              <span className="block text-[12px] font-semibold text-foreground">
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

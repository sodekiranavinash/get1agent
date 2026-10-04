import { FlaskConical, GitCompare } from 'lucide-react'
import { useInView } from '../../hooks/useInView'

const METRICS = [
  { label: 'Faithfulness', value: 94 },
  { label: 'Context relevance', value: 88 },
  { label: 'Answer correctness', value: 91 },
  { label: 'Context recall', value: 86 },
]

const MODELS = [
  { name: 'deepseek.v3.2', score: 91, latency: '1.6s' },
  { name: 'Nova 2 Lite', score: 89, latency: '1.4s' },
  { name: 'Qwen3 Next 80B', score: 86, latency: '1.9s' },
  { name: 'GLM 4.7 Flash', score: 83, latency: '1.2s' },
]

/** Ragas-aligned judge scores for a RAG run — bars grow in on scroll. */
export function EvalPreview() {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.25 })

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <FlaskConical className="size-3.5 shrink-0 text-accent" />
          <span className="text-[12px] font-semibold text-foreground">RAG evaluation</span>
        </div>
        <span className="rounded-full border border-border bg-canvas/60 px-2 py-0.5 text-[10.5px] font-medium text-muted">
          golden dataset
        </span>
      </div>

      <div className="mt-4 space-y-3">
        {METRICS.map((metric, index) => (
          <div key={metric.label}>
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-[12px] text-muted">{metric.label}</span>
              <span className="font-mono text-[12px] font-semibold text-foreground">
                {(metric.value / 100).toFixed(2)}
              </span>
            </div>
            <span className="mt-1.5 block h-1.5 overflow-hidden rounded-full bg-raised/70">
              <span
                className="block h-full rounded-full bg-gradient-to-r from-accent via-violet to-teal transition-[width] duration-700 ease-out"
                style={{
                  width: inView ? `${metric.value}%` : '0%',
                  transitionDelay: `${index * 110}ms`,
                }}
              />
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/** A/B: up to four models replayed in parallel from a real trace. */
export function AbTestPreview() {
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.25 })

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <GitCompare className="size-3.5 shrink-0 text-accent" />
          <span className="text-[12px] font-semibold text-foreground">A/B testing</span>
        </div>
        <span className="rounded-full border border-border bg-canvas/60 px-2 py-0.5 text-[10.5px] font-medium text-muted">
          4 models · parallel
        </span>
      </div>

      <div className="mt-4 space-y-2.5">
        {MODELS.map((model, index) => (
          <div key={model.name} className="grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-3">
            <span className="min-w-0">
              <span className="block truncate font-mono text-[11.5px] text-foreground">
                {model.name}
              </span>
              <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-raised/70">
                <span
                  className="block h-full rounded-full bg-accent transition-[width] duration-700 ease-out"
                  style={{
                    width: inView ? `${model.score}%` : '0%',
                    transitionDelay: `${index * 110}ms`,
                  }}
                />
              </span>
            </span>
            <span className="text-right font-mono text-[10.5px] text-subtle">
              {model.latency}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

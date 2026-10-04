import { useMemo, useState } from 'react'
import { DiagramCanvas } from '../blueprint/DiagramCanvas'
import { layoutDiagram } from '../blueprint/engine'
import { pipelineToDiagram } from '../blueprint/pipeline'
import type { RequestFlow } from '../blueprint/diagrams'

function FlowChips({
  flows,
  active,
  onSelect,
}: {
  flows: RequestFlow[]
  active: string
  onSelect: (id: string) => void
}) {
  return (
    <div className="scrollbar-thin -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      {flows.map((flow) => {
        const Icon = flow.icon
        const selected = flow.id === active
        return (
          <button
            key={flow.id}
            type="button"
            onClick={() => onSelect(flow.id)}
            className={`flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-1.5 text-[12px] font-medium transition-colors ${
              selected
                ? 'border-accent/50 bg-accent-soft text-accent'
                : 'border-border bg-surface/60 text-muted hover:border-border-strong hover:text-foreground'
            }`}
          >
            <Icon className="size-3.5" strokeWidth={1.9} />
            {flow.label}
          </button>
        )
      })}
    </div>
  )
}

/**
 * A tab that walks one journey at a time as a vertical, numbered flow, with a
 * chip per journey. Consecutive steps in the same environment share a dotted
 * boundary — the same layered language the map tabs use.
 */
export function PipelinesTab({
  title,
  blurb,
  flows,
}: {
  title: string
  blurb: string
  flows: RequestFlow[]
}) {
  const [activeId, setActiveId] = useState(flows[0].id)
  const flow = flows.find((f) => f.id === activeId) ?? flows[0]
  const layout = useMemo(
    () => layoutDiagram(pipelineToDiagram(flow.spec)),
    [flow],
  )
  const legend = useMemo(
    () => Array.from(new Set(flow.spec.envs.map((env) => env.tone))),
    [flow],
  )

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-[16px] font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        <p className="mt-1.5 max-w-4xl text-[12.5px] leading-relaxed text-muted">
          {blurb}
        </p>
      </header>

      {flows.length > 1 ? (
        <FlowChips flows={flows} active={flow.id} onSelect={setActiveId} />
      ) : null}

      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-canvas text-accent">
              <flow.icon className="size-4" strokeWidth={1.8} />
            </span>
            <div>
              <h3 className="text-[14px] font-semibold text-foreground">
                {flow.label}
              </h3>
              <p className="mt-1 max-w-4xl text-[12.5px] leading-relaxed text-muted">
                {flow.summary}
              </p>
            </div>
          </div>
          <span className="rounded-full border border-border bg-canvas/60 px-2.5 py-1 font-mono text-[10.5px] text-subtle">
            {flow.spec.steps.length} steps
          </span>
        </div>

        <DiagramCanvas key={flow.id} layout={layout} legend={legend} />
      </div>
    </div>
  )
}

import { useMemo, useState } from 'react'
import { FlowCanvas } from '../blueprint/FlowCanvas'
import { layoutFlow } from '../blueprint/flow'
import { journeyTones, type Journey } from '../blueprint/journeys'

function JourneyChips({
  journeys,
  active,
  onSelect,
}: {
  journeys: Journey[]
  active: string
  onSelect: (id: string) => void
}) {
  return (
    <div className="scrollbar-thin -mx-1 flex gap-2 overflow-x-auto px-1 pb-1">
      {journeys.map((journey) => {
        const Icon = journey.icon
        const selected = journey.id === active
        return (
          <button
            key={journey.id}
            type="button"
            onClick={() => onSelect(journey.id)}
            className={`flex shrink-0 items-center gap-2 rounded-full border px-3.5 py-1.5 text-[12px] font-medium transition-colors ${
              selected
                ? 'border-accent/50 bg-accent-soft text-accent'
                : 'border-border bg-surface/60 text-muted hover:border-border-strong hover:text-foreground'
            }`}
          >
            <Icon className="size-3.5" strokeWidth={1.9} />
            {journey.label}
          </button>
        )
      })}
    </div>
  )
}

/**
 * A tab that walks one journey at a time as the same composed map the overview
 * sheet uses: stages left → right on one row, and — where the flow is a round
 * trip — a single labelled return edge travelling back along the top to the
 * client. A dot travels every connector in the direction of data flow.
 */
export function JourneysTab({
  title,
  blurb,
  journeys,
}: {
  title: string
  blurb: string
  journeys: Journey[]
}) {
  const [activeId, setActiveId] = useState(journeys[0].id)
  const journey = journeys.find((j) => j.id === activeId) ?? journeys[0]
  const layout = useMemo(() => layoutFlow(journey.spec), [journey])
  const legend = useMemo(() => journeyTones(journey), [journey])

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

      {journeys.length > 1 ? (
        <JourneyChips journeys={journeys} active={journey.id} onSelect={setActiveId} />
      ) : null}

      <div className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-canvas text-accent">
              <journey.icon className="size-4" strokeWidth={1.8} />
            </span>
            <div>
              <h3 className="text-[14px] font-semibold text-foreground">
                {journey.label}
              </h3>
              <p className="mt-1 max-w-4xl text-[12.5px] leading-relaxed text-muted">
                {journey.summary}
              </p>
            </div>
          </div>
          <span className="rounded-full border border-border bg-canvas/60 px-2.5 py-1 font-mono text-[10.5px] text-subtle">
            {journey.spec.sections.length} stages · read left to right
          </span>
        </div>

        <FlowCanvas key={journey.id} layout={layout} legend={legend} />
      </div>
    </div>
  )
}

import { useMemo, type ReactNode } from 'react'
import { FlowCanvas } from '../blueprint/FlowCanvas'
import { layoutFlow, type FlowSpec } from '../blueprint/flow'
import type { ArchEdgeTone } from '../blueprint/theme'

/**
 * A tab that is a single composed map: groups of services on one sheet, the flow
 * traced element to element, and a dot travelling each connector in the
 * direction of data flow.
 */
export function FlowTab({
  title,
  blurb,
  spec,
  legend,
  note,
}: {
  title: string
  /** Optional lead-in copy under the title. */
  blurb?: string
  spec: FlowSpec
  legend: ArchEdgeTone[]
  note?: ReactNode
}) {
  const layout = useMemo(() => layoutFlow(spec), [spec])

  return (
    <div className="space-y-4">
      <header>
        <h2 className="text-[16px] font-semibold tracking-tight text-foreground">
          {title}
        </h2>
        {blurb ? (
          <p className="mt-1.5 max-w-4xl text-[12.5px] leading-relaxed text-muted">
            {blurb}
          </p>
        ) : null}
      </header>
      <FlowCanvas layout={layout} legend={legend} note={note} />
    </div>
  )
}

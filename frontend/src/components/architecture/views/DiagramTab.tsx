import { useMemo, type ReactNode } from 'react'
import { DiagramCanvas } from '../blueprint/DiagramCanvas'
import { layoutDiagram, type DiagramSpec } from '../blueprint/engine'
import type { ArchEdgeTone } from '../blueprint/theme'

/**
 * A tab that is a single layered boundary diagram: a short heading + blurb, then
 * the full-width overview scaled to fit the page.
 */
export function DiagramTab({
  title,
  blurb,
  spec,
  legend,
  note,
}: {
  title: string
  blurb: string
  spec: DiagramSpec
  legend: ArchEdgeTone[]
  note?: ReactNode
}) {
  const layout = useMemo(() => layoutDiagram(spec), [spec])

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
      <DiagramCanvas layout={layout} legend={legend} note={note} />
    </div>
  )
}

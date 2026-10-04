import type { ReactNode } from 'react'
import { BAND_LABEL_W, type Layout } from './engine'
import { ARCH_TONES, toneAlpha, type ArchEdgeTone } from './theme'
import { EdgeLabels, EdgeLayer, FitToWidth, Legend, NodeSymbol } from './parts'

type DiagramCanvasProps = {
  layout: Layout
  legend: ArchEdgeTone[]
  /** Extra note pinned to the right of the legend. */
  note?: ReactNode
}

/**
 * Renders a layered boundary diagram directly in the page flow: dotted
 * environment frames with their titles in the left gutter, optional per-row
 * captions, an orthogonal connector layer, and fixed-size symbols. It is scaled
 * to the available width, so the page keeps a single natural scrollbar.
 */
export function DiagramCanvas({ layout, legend, note }: DiagramCanvasProps) {
  return (
    <div className="space-y-3">
      <Legend tones={legend} note={note} />

      <FitToWidth width={layout.width} height={layout.height}>
        {/* Environment boundaries + their gutter labels */}
        {layout.bands.map((band) => {
          const color = ARCH_TONES[band.tone].color
          return (
            <div key={band.id}>
              <div
                className="absolute rounded-2xl"
                style={{
                  left: band.x,
                  top: band.y,
                  width: band.w,
                  height: band.h,
                  background: `linear-gradient(180deg, ${toneAlpha(
                    band.tone,
                    0.06,
                  )}, transparent 42%)`,
                }}
              />
              {/* An SVG stroke gives an evenly spaced dotted boundary, unlike a
                  CSS dotted border whose dots drift with the box size. */}
              <svg
                className="pointer-events-none absolute"
                style={{ left: band.x, top: band.y }}
                width={band.w}
                height={band.h}
                aria-hidden="true"
              >
                <rect
                  x={0.75}
                  y={0.75}
                  width={band.w - 1.5}
                  height={band.h - 1.5}
                  rx={16}
                  fill="none"
                  stroke={toneAlpha(band.tone, 0.55)}
                  strokeWidth={1.5}
                  strokeDasharray="0.5 8"
                  strokeLinecap="round"
                />
              </svg>
              <div
                className="absolute flex flex-col items-end justify-center gap-0.5 pr-5 text-right"
                style={{ left: 0, top: band.y, width: BAND_LABEL_W, height: band.h }}
              >
                <span className="flex items-center gap-1.5">
                  <span className="font-mono text-[10px] text-subtle">
                    {String(band.index + 1).padStart(2, '0')}
                  </span>
                  <span
                    className="size-1.5 rounded-full"
                    style={{ background: color }}
                  />
                </span>
                <span
                  className="text-[12px] leading-tight font-semibold tracking-[0.13em] uppercase"
                  style={{ color }}
                >
                  {band.title}
                </span>
                {band.hint ? (
                  <span className="max-w-[150px] text-[10.5px] leading-snug text-subtle">
                    {band.hint}
                  </span>
                ) : null}
              </div>
            </div>
          )
        })}

        {/* Per-row captions inside a boundary */}
        {layout.captions.map((caption) => (
          <div
            key={caption.id}
            className="absolute flex items-center gap-2"
            style={{ left: caption.x, top: caption.y, width: caption.w, height: 22 }}
          >
            <span
              className="h-px flex-1"
              style={{ background: toneAlpha(caption.tone, 0.35) }}
            />
            <span className="flex items-center gap-1.5">
              <span
                className="size-1.5 rounded-full"
                style={{ background: ARCH_TONES[caption.tone].color }}
              />
              <span className="text-[10.5px] font-semibold tracking-[0.14em] text-subtle uppercase">
                {caption.text}
              </span>
            </span>
            <span
              className="h-px flex-1"
              style={{ background: toneAlpha(caption.tone, 0.35) }}
            />
          </div>
        ))}

        <EdgeLayer
          edges={layout.edges}
          width={layout.width}
          height={layout.height}
        />
        <EdgeLabels edges={layout.edges} />

        {layout.nodes.map((node) => (
          <NodeSymbol key={node.id} node={node} />
        ))}
      </FitToWidth>
    </div>
  )
}

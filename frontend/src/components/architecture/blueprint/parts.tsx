import type { ReactNode } from 'react'
import { ARCH_TONES, toneAlpha, type ArchEdgeTone } from './theme'

/** Defs shared by every canvas: an arrow head per tone. */
export function MarkerDefs({
  tones,
  scale = 1,
}: {
  tones: ArchEdgeTone[]
  /** Bigger heads where connectors are short and need to read at a glance. */
  scale?: number
}) {
  return (
    <defs>
      {tones.map((tone) => {
        const color = ARCH_TONES[tone].color
        return (
          <marker
            key={`arrow-${tone}`}
            id={`bp-arrow-${tone}`}
            viewBox="0 0 10 10"
            refX="7.5"
            refY="5"
            markerWidth={7 * scale}
            markerHeight={7 * scale}
            orient="auto-start-reverse"
          >
            <path
              d="M1.5,1.5 L8,5 L1.5,8.5"
              fill="none"
              stroke={color}
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </marker>
        )
      })}
    </defs>
  )
}

/** The minimum a connector needs to carry a floating chip. */
export type LabelledEdge = {
  id: string
  tone: ArchEdgeTone
  label?: string
  labelX?: number
  labelY?: number
}

/** Floating connector captions, kept on their own non-interactive layer. */
export function EdgeLabels({ edges }: { edges: LabelledEdge[] }) {
  return (
    <div className="pointer-events-none absolute inset-0">
      {edges
        .filter((edge) => edge.label && edge.labelX != null && edge.labelY != null)
        .map((edge) => (
          <span
            key={edge.id}
            className="absolute -translate-x-1/2 -translate-y-1/2 rounded-full border px-1.5 py-px font-mono text-[9px] leading-none whitespace-nowrap"
            style={{
              left: edge.labelX,
              top: edge.labelY,
              color: ARCH_TONES[edge.tone].color,
              borderColor: toneAlpha(edge.tone, 0.4),
              background: 'color-mix(in srgb, var(--app-canvas) 85%, transparent)',
              backdropFilter: 'blur(4px)',
            }}
          >
            {edge.label}
          </span>
        ))}
    </div>
  )
}

/** The key shown beneath a diagram. */
export function Legend({
  tones,
  note,
}: {
  tones: ArchEdgeTone[]
  note?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <span className="flex items-center gap-1.5">
        <span
          className="size-3 rounded-[3px] border-[1.5px] border-dotted"
          style={{ borderColor: 'var(--app-border-strong)' }}
        />
        <span className="text-[10.5px] font-medium text-muted">Isolated boundary</span>
      </span>
      <span className="h-3.5 w-px bg-border" />
      {tones.map((tone) => (
        <span key={tone} className="flex items-center gap-1.5">
          <span
            className="h-0.5 w-5 rounded-full"
            style={{ background: ARCH_TONES[tone].color }}
          />
          <span className="text-[10.5px] font-medium text-muted">
            {ARCH_TONES[tone].label}
          </span>
        </span>
      ))}
      {note ? <span className="ml-auto text-[10.5px] text-subtle">{note}</span> : null}
    </div>
  )
}

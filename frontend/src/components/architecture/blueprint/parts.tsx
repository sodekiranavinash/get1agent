import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  ARCH_TONES,
  KIND_META,
  SYMBOL_COLORS,
  toneAlpha,
  type ArchEdgeTone,
  type ArchNodeKind,
} from './theme'
import { AWS_ICONS, type AwsIconId } from './awsIcons'
import type { LaidEdge } from './engine'

export type SymbolNode = {
  x: number
  y: number
  w: number
  h: number
  kind: ArchNodeKind
  title: string
  subtitle?: string
  code?: string
  icon?: LucideIcon
  aws?: AwsIconId
  badge?: number
}

/** Defs shared by every canvas: an arrow head per tone. */
export function MarkerDefs({ tones }: { tones: ArchEdgeTone[] }) {
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
            markerWidth="7"
            markerHeight="7"
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

/** The SVG connector layer for one diagram. */
export function EdgeLayer({
  edges,
  width,
  height,
}: {
  edges: LaidEdge[]
  width: number
  height: number
}) {
  const tones = Array.from(new Set(edges.map((e) => e.tone)))
  return (
    <svg
      className="pointer-events-none absolute inset-0"
      width={width}
      height={height}
      aria-hidden="true"
    >
      <MarkerDefs tones={tones} />
      {edges.map((edge) => {
        const color = ARCH_TONES[edge.tone].color
        return (
          <g key={edge.id}>
            <path
              d={edge.d}
              fill="none"
              stroke={color}
              strokeWidth={1.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              className={edge.dashed ? 'bp-line bp-line--still' : 'bp-line'}
              markerEnd={`url(#bp-arrow-${edge.tone})`}
            />
            <circle cx={edge.sx} cy={edge.sy} r={2.6} fill={color} />
          </g>
        )
      })}
    </svg>
  )
}

/** Floating connector captions, kept on their own non-interactive layer. */
export function EdgeLabels({ edges }: { edges: LaidEdge[] }) {
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

/**
 * A service symbol: an AWS-style coloured tile with the service name in full
 * beneath it. No card chrome, so the map reads as a set of services rather than
 * a wall of boxes.
 */
export function NodeSymbol({
  node,
  numbered,
}: {
  node: SymbolNode
  numbered?: number
}) {
  const Icon = node.icon ?? KIND_META[node.kind].icon
  const AwsIcon = node.aws ? AWS_ICONS[node.aws] : undefined
  const color = SYMBOL_COLORS[node.kind]
  const badge = numbered ?? node.badge
  return (
    <div
      className="absolute flex flex-col items-center text-center"
      style={{ left: node.x, top: node.y, width: node.w, height: node.h }}
    >
      <span className="relative flex size-[52px] shrink-0 items-center justify-center overflow-hidden rounded-2xl ring-1 ring-inset ring-white/25">
        {AwsIcon ? (
          <AwsIcon width={52} height={52} className="size-[52px]" />
        ) : (
          <span
            className="flex size-full items-center justify-center"
            style={{ background: color }}
          >
            <Icon className="size-6 text-white" strokeWidth={1.9} />
          </span>
        )}
        {badge != null ? (
          <span className="absolute top-0.5 left-0.5 flex size-5 items-center justify-center rounded-full border border-border bg-canvas font-mono text-[9px] font-semibold text-foreground">
            {badge}
          </span>
        ) : null}
      </span>
      <span className="mt-2 text-[12px] leading-tight font-semibold tracking-tight text-foreground">
        {node.title}
      </span>
      {node.subtitle ? (
        <span className="mt-0.5 text-[10.5px] leading-snug text-muted">
          {node.subtitle}
        </span>
      ) : null}
      {node.code ? (
        <span className="mt-0.5 font-mono text-[9.5px] leading-none text-subtle">
          {node.code}
        </span>
      ) : null}
    </div>
  )
}

/**
 * Scales a fixed-width canvas down to the available width so the whole diagram
 * is visible with the page's single scrollbar — no nested scroll panes.
 */
export function FitToWidth({
  width,
  height,
  maxScale = 1,
  children,
}: {
  width: number
  height: number
  maxScale?: number
  children: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(maxScale)

  useLayoutEffect(() => {
    const el = ref.current
    if (!el) return
    const update = () => {
      const w = el.clientWidth
      if (w > 0) setScale(Math.min(maxScale, w / width))
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [width, maxScale])

  return (
    <div
      ref={ref}
      className="mx-auto w-full"
      style={{ maxWidth: width, height: Math.round(height * scale) }}
    >
      <div
        className="relative"
        style={{
          width,
          height,
          transform: `scale(${scale})`,
          transformOrigin: 'top left',
        }}
      >
        {children}
      </div>
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

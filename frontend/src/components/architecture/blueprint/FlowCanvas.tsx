import { useLayoutEffect, useRef, useState, type ReactNode } from 'react'
import {
  ARCH_TONES,
  KIND_META,
  SYMBOL_COLORS,
  toneAlpha,
  type ArchEdgeTone,
} from './theme'
import { AWS_ICONS } from './awsIcons'
import type { FlowLayout, LaidFlowEdge } from './flow'
import { EdgeLabels, Legend, MarkerDefs } from './parts'

/* -------------------------------------------------------------------------- */
/* Travelling dot                                                              */
/* -------------------------------------------------------------------------- */

/**
 * A dot rides each connector from its source to its target, so the direction of
 * data flow is legible without reading a legend. The path *is* the connector,
 * so the dot can never drift off the line; `delay` staggers the starts across
 * the map. Motion is dropped entirely when the reader asks for it.
 */
function FlowDot({ edge, moving }: { edge: LaidFlowEdge; moving: boolean }) {
  if (edge.still) return null
  const color = ARCH_TONES[edge.tone].color
  if (!moving) {
    return <circle cx={edge.sx} cy={edge.sy} r={3} fill={color} opacity={0.9} />
  }
  return (
    <g>
      <circle r={7} fill={color} opacity={0.16}>
        <animateMotion
          dur={`${edge.dur}s`}
          begin={`${-edge.delay}s`}
          repeatCount="indefinite"
          path={edge.d}
        />
      </circle>
      <circle r={2.7} fill={color}>
        <animateMotion
          dur={`${edge.dur}s`}
          begin={`${-edge.delay}s`}
          repeatCount="indefinite"
          path={edge.d}
        />
        <animate
          attributeName="opacity"
          values="0;1;1;0.9;0"
          keyTimes="0;0.08;0.86;0.94;1"
          dur={`${edge.dur}s`}
          begin={`${-edge.delay}s`}
          repeatCount="indefinite"
        />
      </circle>
    </g>
  )
}

/** The connector layer: one orthogonal path per edge, arrow at the target. */
function FlowEdgeLayer({
  layout,
  moving,
}: {
  layout: FlowLayout
  moving: boolean
}) {
  const tones = Array.from(new Set(layout.edges.map((e) => e.tone)))
  return (
    <svg
      className="pointer-events-none absolute inset-0"
      width={layout.width}
      height={layout.height}
      aria-hidden="true"
    >
      <MarkerDefs tones={tones} scale={1.25} />
      {layout.edges.map((edge) => {
        const color = ARCH_TONES[edge.tone].color
        return (
          <g key={edge.id}>
            <path
              d={edge.d}
              fill="none"
              stroke={color}
              strokeWidth={1.7}
              strokeOpacity={edge.still ? 1 : 0.6}
              strokeLinecap="round"
              strokeLinejoin="round"
              className={edge.still ? 'bp-line bp-line--still' : undefined}
              markerEnd={`url(#bp-arrow-${edge.tone})`}
            />
            {!edge.still ? (
              <circle cx={edge.sx} cy={edge.sy} r={2.8} fill={color} />
            ) : null}
            <FlowDot edge={edge} moving={moving} />
          </g>
        )
      })}
    </svg>
  )
}

/* -------------------------------------------------------------------------- */
/* Service: an icon block with a little text                                  */
/* -------------------------------------------------------------------------- */

/** One service — a 46px AWS-style tile, its name, and one micro line. */
function FlowTile({ node }: { node: FlowLayout['nodes'][number] }) {
  const Icon = node.icon ?? KIND_META[node.kind].icon
  const AwsIcon = node.aws ? AWS_ICONS[node.aws] : undefined
  return (
    <div
      className="absolute flex flex-col items-center text-center"
      style={{ left: node.x, top: node.y, width: node.w, height: node.h }}
      title={node.code ? `${node.title} — ${node.code}` : node.title}
    >
      <span className="relative flex size-[40px] shrink-0 items-center justify-center overflow-hidden rounded-xl ring-1 ring-inset ring-white/25">
        {AwsIcon ? (
          <AwsIcon width={40} height={40} className="size-[40px]" />
        ) : (
          <span
            className="flex size-full items-center justify-center"
            style={{ background: SYMBOL_COLORS[node.kind] }}
          >
            <Icon className="size-[18px] text-white" strokeWidth={1.9} />
          </span>
        )}
      </span>
      <span className="mt-1 line-clamp-2 w-full px-0.5 text-[10px] leading-tight font-semibold tracking-tight text-foreground">
        {node.title}
      </span>
      {node.code ? (
        <span className="mt-0.5 w-full truncate px-0.5 font-mono text-[8.5px] leading-none text-subtle">
          {node.code}
        </span>
      ) : null}
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Group box                                                                   */
/* -------------------------------------------------------------------------- */

/** A group of services: a dotted box with its number, title and hint on top. */
function GroupBox({ section }: { section: FlowLayout['sections'][number] }) {
  const color = ARCH_TONES[section.tone].color
  return (
    <div
      className="absolute rounded-2xl"
      style={{
        left: section.x,
        top: section.y,
        width: section.w,
        height: section.h,
        background: `linear-gradient(160deg, ${toneAlpha(section.tone, 0.07)}, transparent 46%)`,
      }}
    >
      <svg
        className="pointer-events-none absolute inset-0"
        width={section.w}
        height={section.h}
        aria-hidden="true"
      >
        <rect
          x={0.75}
          y={0.75}
          width={section.w - 1.5}
          height={section.h - 1.5}
          rx={16}
          fill="none"
          stroke={toneAlpha(section.tone, 0.5)}
          strokeWidth={1.5}
          strokeDasharray="0.5 8"
          strokeLinecap="round"
        />
      </svg>
      <div className="absolute inset-x-0 top-0 px-3 pt-1.5">
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[10px] leading-none text-subtle">
            {String(section.index + 1).padStart(2, '0')}
          </span>
          <span className="size-1.5 shrink-0 rounded-full" style={{ background: color }} />
          <span
            className="min-w-0 truncate text-[11px] leading-none font-semibold tracking-[0.13em] uppercase"
            style={{ color }}
          >
            {section.title}
          </span>
        </div>
        {section.hint ? (
          <p className="mt-1 truncate text-[10px] leading-none text-subtle">
            {section.hint}
          </p>
        ) : null}
      </div>
    </div>
  )
}

/* -------------------------------------------------------------------------- */
/* Canvas                                                                      */
/* -------------------------------------------------------------------------- */

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false)
  useLayoutEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)')
    const update = () => setReduced(query.matches)
    update()
    query.addEventListener('change', update)
    return () => query.removeEventListener('change', update)
  }, [])
  return reduced
}

/**
 * The composed map: groups of services placed on one sheet, the flow traced
 * service to service, and a dot travelling every connector in the direction of
 * data flow. Always scaled to the page width — one sheet, no panning.
 */
export function FlowCanvas({
  layout,
  legend,
  note,
}: {
  layout: FlowLayout
  legend: ArchEdgeTone[]
  note?: ReactNode
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [scale, setScale] = useState(1)
  const reduced = usePrefersReducedMotion()

  useLayoutEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const update = () => {
      const w = el.clientWidth
      if (w > 0) setScale(Math.min(1, w / layout.width))
    }
    update()
    const observer = new ResizeObserver(update)
    observer.observe(el)
    return () => observer.disconnect()
  }, [layout.width])

  const s = scale

  return (
    <div className="space-y-3">
      <Legend tones={legend} note={note} />

      <div className="flex flex-wrap items-center gap-1.5 text-[10.5px] text-subtle">
        <span className="relative flex size-2.5 items-center justify-center">
          <span
            className="absolute size-2.5 rounded-full opacity-25"
            style={{ background: 'var(--app-accent)' }}
          />
          <span
            className="size-1.5 rounded-full"
            style={{ background: 'var(--app-accent)' }}
          />
        </span>
        The flow is traced service to service · the dot travels in the direction
        of data flow
      </div>

      <div ref={wrapRef}>
        <div
          className="relative mx-auto"
          style={{
            width: Math.round(layout.width * s),
            height: Math.round(layout.height * s),
          }}
        >
          <div
            className="relative"
            style={{
              width: layout.width,
              height: layout.height,
              transform: s === 1 ? undefined : `scale(${s})`,
              transformOrigin: 'top left',
            }}
          >
            {layout.sections.map((section) => (
              <GroupBox key={section.id} section={section} />
            ))}

            <FlowEdgeLayer layout={layout} moving={!reduced} />
            <EdgeLabels edges={layout.edges} />

            {layout.nodes.map((node) => (
              <FlowTile key={node.id} node={node} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

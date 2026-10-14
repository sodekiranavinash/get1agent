import type { LucideIcon } from 'lucide-react'
import type { ArchEdgeTone, ArchNodeKind } from './theme'
import type { AwsIconId } from './awsIcons'

/* -------------------------------------------------------------------------- */
/* Spec                                                                        */
/* -------------------------------------------------------------------------- */

/** One service — an icon block with a little text, nothing more. */
export type FlowNodeSpec = {
  id: string
  kind: ArchNodeKind
  title: string
  /** A single micro line under the name (kept very short). */
  code?: string
  /** Explicit `[col, row]` inside the group (defaults to reading order). */
  at?: [number, number]
  icon?: LucideIcon
  /** Use the official AWS service icon instead of the neutral symbol. */
  aws?: AwsIconId
}

/**
 * A group of services on the canvas. Its position is authored, not derived:
 * groups are placed to fill the sheet, and the flow reads through them.
 */
export type FlowSectionSpec = {
  id: string
  title: string
  hint?: string
  tone: ArchEdgeTone
  /** Icon blocks per row inside the group. */
  cols: number
  x: number
  y: number
  /** Fixed width (the full-width strips); otherwise sized by `cols`. */
  w?: number
  /** Distribute this group's services evenly across `w` in one row — used for a
   *  shared shelf that every column above writes into. */
  spread?: boolean
  nodes: FlowNodeSpec[]
}

export type FlowRoute =
  /** Pick the exit/entry sides from the relative position. */
  | 'auto'
  /** Leave the bottom at `fromX`, run across at `viaY`, enter the target's top. */
  | 'drop'
  /** Leave the bottom, run across under the target at `viaY`, enter its bottom. */
  | 'belly'
  /** Leave the right at the group's mid-height, run over the top at `viaY`. */
  | 'over'
  /** Leave the right, drop down `viaX` at `viaY`, enter the target's right edge. */
  | 'rise'
  /** Leave the bottom at `fromX`, run to `viaX`, drop to the target's mid-line and
   *  enter its **left** edge — the clean way into a group's row. */
  | 'channelLeft'
  /** Leave the right at `viaY`, drop down `viaX`, enter the target's right edge. */
  | 'channelRight'
  /** Leave the right edge, descend a channel at `viaX` to `viaY`, then drop into
   *  the target's column from above. */
  | 'descend'

export type FlowEdgeSpec = {
  id?: string
  /** A node id, or `@<sectionId>` for the group as a whole. */
  from: string
  to: string
  tone: ArchEdgeTone
  label?: string
  route?: FlowRoute
  /** Vertical channel x (`margin`, `elbow`) and horizontal channel y (`drop`, `belly`, `over`, `elbow`). */
  viaX?: number
  viaY?: number
  /** Where the connector leaves the source — drops several lines out of one group. */
  fromX?: number
  /** Cross-cutting relationship: dotted, with no travelling dot. */
  still?: boolean
}

export type FlowSpec = {
  id: string
  sections: FlowSectionSpec[]
  edges: FlowEdgeSpec[]
}

/* -------------------------------------------------------------------------- */
/* Geometry                                                                    */
/* -------------------------------------------------------------------------- */

/** One icon block: a 40px tile with a name and one micro line under it. */
export const TILE_W = 104
export const TILE_H = 80
const TILE_GAP_X = 24
const TILE_GAP_Y = 22
/** Group chrome. */
const PAD_X = 12
const PAD_TOP = 6
const PAD_BOTTOM = 12
const HEAD_H = 52
/** Sheet margin. */
export const MARGIN = 24

export type Rect = {
  x: number
  y: number
  w: number
  h: number
  cx: number
  cy: number
}

export type LaidFlowSection = {
  id: string
  title: string
  hint?: string
  tone: ArchEdgeTone
  index: number
  x: number
  y: number
  w: number
  h: number
  cx: number
  cy: number
}

export type LaidFlowNode = FlowNodeSpec & {
  section: number
  index: number
  x: number
  y: number
  w: number
  h: number
  cx: number
  cy: number
}

export type LaidFlowEdge = {
  id: string
  tone: ArchEdgeTone
  d: string
  sx: number
  sy: number
  still?: boolean
  label?: string
  labelX?: number
  labelY?: number
  dur: number
  delay: number
}

export type FlowLayout = {
  width: number
  height: number
  sections: LaidFlowSection[]
  nodes: LaidFlowNode[]
  edges: LaidFlowEdge[]
}

type Pt = { x: number; y: number }

/** Size of a group: as many icon-block rows as its services need. */
export function sectionSize(spec: FlowSectionSpec) {
  const rows = spec.spread ? 1 : Math.max(1, Math.ceil(spec.nodes.length / spec.cols))
  const contentW = spec.cols * TILE_W + (spec.cols - 1) * TILE_GAP_X
  const contentH = rows * TILE_H + (rows - 1) * TILE_GAP_Y
  return {
    w: spec.w ?? contentW + 2 * PAD_X,
    h: HEAD_H + PAD_TOP + contentH + PAD_BOTTOM,
  }
}

/* -------------------------------------------------------------------------- */
/* Layout                                                                      */
/* -------------------------------------------------------------------------- */

/**
 * Lays the groups out where the spec puts them and routes every connector
 * between them. Nothing here re-flows the map: the composition is authored, so
 * the sheet is used deliberately and the flow is drawn, not stacked.
 */
export function layoutFlow(spec: FlowSpec): FlowLayout {
  const sections: LaidFlowSection[] = spec.sections.map((s, i) => {
    const size = sectionSize(s)
    return {
      id: s.id,
      title: s.title,
      hint: s.hint,
      tone: s.tone,
      index: i,
      x: s.x,
      y: s.y,
      w: size.w,
      h: size.h,
      cx: s.x + size.w / 2,
      cy: s.y + size.h / 2,
    }
  })
  const sectionById = new Map(spec.sections.map((s, i) => [s.id, i]))

  const nodes: LaidFlowNode[] = []
  spec.sections.forEach((s, si) => {
    const rect = sections[si]
    const contentW = s.cols * TILE_W + (s.cols - 1) * TILE_GAP_X
    const originX = rect.x + (rect.w - contentW) / 2
    const spreadStep =
      spec.sections[si].spread && rect.w
        ? (rect.w - 2 * PAD_X - TILE_W) / Math.max(1, s.nodes.length - 1)
        : 0
    const originY = rect.y + HEAD_H + PAD_TOP
    const spreading = spec.sections[si].spread === true
    s.nodes.forEach((node, ni) => {
      const col = node.at ? node.at[0] : ni % s.cols
      const row = spreading ? 0 : node.at ? node.at[1] : Math.floor(ni / s.cols)
      const x = spreading
        ? rect.x + PAD_X + ni * spreadStep
        : originX + col * (TILE_W + TILE_GAP_X)
      const y = originY + row * (TILE_H + TILE_GAP_Y)
      nodes.push({
        ...node,
        section: si,
        index: ni,
        x,
        y,
        w: TILE_W,
        h: TILE_H,
        cx: x + TILE_W / 2,
        cy: y + TILE_H / 2,
      })
    })
  })
  const nodeById = new Map(nodes.map((n) => [n.id, n]))

  const width = Math.max(...sections.map((s) => s.x + s.w)) + MARGIN
  const routeYs = spec.edges
    .map((e) => e.viaY)
    .filter((y): y is number => typeof y === 'number')
  const height =
    Math.max(
      Math.max(...sections.map((s) => s.y + s.h)),
      routeYs.length ? Math.max(...routeYs) + 10 : 0,
    ) + MARGIN

  const edges: LaidFlowEdge[] = []
  spec.edges.forEach((edge, i) => {
    const id = edge.id ?? `e${i}`
    const fromNode = nodeById.get(edge.from)
    const toNode = nodeById.get(edge.to)
    const fromSection = edge.from.startsWith('@')
      ? sectionById.get(edge.from.slice(1))
      : undefined
    const toSection = edge.to.startsWith('@')
      ? sectionById.get(edge.to.slice(1))
      : undefined
    const a: Rect | undefined =
      fromNode ?? (fromSection != null ? sections[fromSection] : undefined)
    const b: Rect | undefined =
      toNode ?? (toSection != null ? sections[toSection] : undefined)
    if (!a || !b) return

    const pts = route(a, b, edge)
    if (pts.length < 2) return
    const d = pts
      .map((p, k) => `${k === 0 ? 'M' : 'L'} ${round(p.x)} ${round(p.y)}`)
      .join(' ')
    const label = labelPoint(pts, edge.label)
    let length = 0
    for (let k = 0; k < pts.length - 1; k += 1) {
      length += Math.hypot(pts[k + 1].x - pts[k].x, pts[k + 1].y - pts[k].y)
    }
    edges.push({
      id,
      tone: edge.tone,
      d,
      sx: pts[0].x,
      sy: pts[0].y,
      still: edge.still,
      label: edge.label,
      labelX: label?.x,
      labelY: label?.y,
      dur: Math.min(5.2, Math.max(1.8, round(length / 260))),
      delay: round(((i * 7) % 11) * 0.21),
    })
  })

  return { width, height, sections, nodes, edges }
}

/* -------------------------------------------------------------------------- */
/* Routing                                                                     */
/* -------------------------------------------------------------------------- */

/** Where two rectangles sit relative to each other. */
function relation(a: Rect, b: Rect): 'right' | 'left' | 'below' | 'above' {
  const dy = b.cy - a.cy
  const gapX = b.x - (a.x + a.w)
  const gapY = b.y - (a.y + a.h)
  const overlapY = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y)
  const overlapX = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)
  if (overlapY > 8) return b.cx >= a.cx ? 'right' : 'left'
  if (overlapX > 8) return dy >= 0 ? 'below' : 'above'
  if (gapX > 0) return 'right'
  if (b.x + b.w < a.x) return 'left'
  if (gapY > 0) return 'below'
  return 'above'
}

function route(a: Rect, b: Rect, edge: FlowEdgeSpec): Pt[] {
  const pts: Pt[] = []
  const push = (p: Pt) => {
    const last = pts[pts.length - 1]
    if (last && Math.abs(last.x - p.x) <= 0.5 && Math.abs(last.y - p.y) <= 0.5) return
    if (pts.length >= 2) {
      const prev = pts[pts.length - 2]
      const sameX = Math.abs(prev.x - last.x) <= 0.5 && Math.abs(last.x - p.x) <= 0.5
      const sameY = Math.abs(prev.y - last.y) <= 0.5 && Math.abs(last.y - p.y) <= 0.5
      if (sameX || sameY) {
        pts[pts.length - 1] = p
        return
      }
    }
    pts.push(p)
  }
  const kind = edge.route ?? 'auto'
  const aBottom = a.y + a.h
  const bBottom = b.y + b.h

  if (kind === 'over') {
    const y = edge.viaY ?? a.y - 26
    const ex = edge.fromX ?? a.cx
    push({ x: ex, y: a.y })
    push({ x: ex, y })
    if (edge.viaX != null) {
      // …come back down the outer margin and enter the target's left edge.
      push({ x: edge.viaX, y })
      push({ x: edge.viaX, y: b.cy })
      push({ x: b.x, y: b.cy })
    } else {
      push({ x: b.cx, y })
      push({ x: b.cx, y: b.y })
    }
    return pts
  }

  if (kind === 'rise') {
    const y = edge.viaY ?? a.y - 26
    const cx = edge.viaX ?? b.x + b.w + 56
    push({ x: a.x + a.w, y: a.cy })
    push({ x: a.x + a.w, y })
    push({ x: cx, y })
    push({ x: cx, y: b.cy })
    push({ x: b.x + b.w, y: b.cy })
    return pts
  }

  if (kind === 'channelRight') {
    const cx = edge.viaX ?? Math.max(a.x + a.w, b.x + b.w) + 40
    push({ x: a.x + a.w, y: edge.viaY ?? a.cy })
    push({ x: cx, y: edge.viaY ?? a.cy })
    push({ x: cx, y: b.cy })
    push({ x: b.x + b.w, y: b.cy })
    return pts
  }

  if (kind === 'descend') {
    const y = edge.viaY ?? aBottom + 30
    const cx = edge.viaX ?? a.x + a.w + 24
    push({ x: a.x + a.w, y: a.cy })
    push({ x: cx, y: a.cy })
    push({ x: cx, y })
    push({ x: b.cx, y })
    push({ x: b.cx, y: b.y })
    return pts
  }

  if (kind === 'channelLeft') {
    const y = edge.viaY ?? aBottom + 30
    const cx = edge.viaX ?? a.x - 40
    const ex = edge.fromX ?? a.cx
    push({ x: ex, y: aBottom })
    push({ x: ex, y })
    push({ x: cx, y })
    push({ x: cx, y: b.cy })
    push({ x: b.x, y: b.cy })
    return pts
  }

  if (kind === 'drop' || kind === 'belly') {
    const y = edge.viaY ?? (aBottom + b.y) / 2
    const ex = edge.fromX ?? a.cx
    push({ x: ex, y: aBottom })
    push({ x: ex, y })
    push({ x: b.cx, y })
    push({ x: b.cx, y: kind === 'belly' ? bBottom : b.y })
    return pts
  }

  const rel = relation(a, b)
  if (rel === 'right') {
    const x = (a.x + a.w + b.x) / 2
    push({ x: a.x + a.w, y: a.cy })
    push({ x, y: a.cy })
    push({ x, y: b.cy })
    push({ x: b.x, y: b.cy })
  } else if (rel === 'left') {
    const x = (b.x + b.w + a.x) / 2
    push({ x: a.x, y: a.cy })
    push({ x, y: a.cy })
    push({ x, y: b.cy })
    push({ x: b.x + b.w, y: b.cy })
  } else if (rel === 'below') {
    const y = (aBottom + b.y) / 2
    push({ x: a.cx, y: aBottom })
    push({ x: a.cx, y })
    push({ x: b.cx, y })
    push({ x: b.cx, y: b.y })
  } else {
    const y = (bBottom + a.y) / 2
    push({ x: a.cx, y: a.y })
    push({ x: a.cx, y })
    push({ x: b.cx, y })
    push({ x: b.cx, y: bBottom })
  }
  return pts
}

function round(n: number): number {
  return Math.round(n * 10) / 10
}

/**
 * Puts a chip on the longest run that can hold it: a long horizontal, then a
 * tall vertical, then any short run — a chip carries an opaque background, so a
 * connector between two neighbouring groups can still be labelled.
 */
function labelPoint(pts: Pt[], label?: string): Pt | undefined {
  if (!label || pts.length < 2) return undefined
  const w = label.length * 5.4 + 12
  let bestH: { x: number; y: number; len: number } | undefined
  let bestV: { x: number; y: number; len: number } | undefined
  for (let i = 0; i < pts.length - 1; i += 1) {
    const a = pts[i]
    const b = pts[i + 1]
    const dx = Math.abs(b.x - a.x)
    const dy = Math.abs(b.y - a.y)
    const len = Math.hypot(dx, dy)
    const mid = { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, len }
    if (dy < 0.75 && dx > (bestH?.len ?? 0)) bestH = mid
    if (dx < 0.75 && dy > (bestV?.len ?? 0)) bestV = mid
  }
  if (bestH && bestH.len >= w) return { x: bestH.x, y: bestH.y }
  if (bestV && bestV.len >= 70) return { x: bestV.x + 5 + w / 2, y: bestV.y }
  if (bestH && bestH.len >= 30) return { x: bestH.x, y: bestH.y }
  if (bestV && bestV.len >= 30) return { x: bestV.x + 5 + w / 2, y: bestV.y }
  return undefined
}

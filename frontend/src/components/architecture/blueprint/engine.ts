import type { LucideIcon } from 'lucide-react'
import type { ArchEdgeTone, ArchNodeKind } from './theme'
import type { AwsIconId } from './awsIcons'

export type Side = 'top' | 'bottom' | 'left' | 'right'

export type NodeSpec = {
  id: string
  kind: ArchNodeKind
  /** Full service name, shown under the symbol. */
  title: string
  /** One short line of context. */
  subtitle?: string
  code?: string
  icon?: LucideIcon
  /** Use the official AWS service icon instead of the neutral symbol. */
  aws?: AwsIconId
  /** Optional step number shown on the tile (used by vertical flow diagrams). */
  badge?: number
}

export type BandSpec = {
  id: string
  /** Boundary label, rendered in the left gutter. */
  title: string
  hint?: string
  tone: ArchEdgeTone
  rows: NodeSpec[][]
  /** Optional caption above each row (lets one boundary hold several layers). */
  rowLabels?: (string | undefined)[]
}

export type EdgeSpec = {
  id?: string
  /**
   * A node id, or `@<bandId>` to connect the whole environment — used to keep
   * the map high level and the connector count low.
   */
  from: string
  to: string
  tone: ArchEdgeTone
  label?: string
  dashed?: boolean
}

export type DiagramSpec = {
  id: string
  bands: BandSpec[]
  edges: EdgeSpec[]
}

export type LaidNode = NodeSpec & {
  x: number
  y: number
  w: number
  h: number
  band: number
  row: number
  cx: number
  cy: number
}

export type LaidBand = {
  id: string
  title: string
  hint?: string
  tone: ArchEdgeTone
  index: number
  x: number
  y: number
  w: number
  h: number
}

export type LaidEdge = {
  id: string
  tone: ArchEdgeTone
  d: string
  sx: number
  sy: number
  dx: number
  dy: number
  dashed?: boolean
  label?: string
  labelX?: number
  labelY?: number
}

export type LaidCaption = {
  id: string
  text: string
  tone: ArchEdgeTone
  x: number
  y: number
  w: number
}

export type Layout = {
  width: number
  height: number
  bands: LaidBand[]
  nodes: LaidNode[]
  edges: LaidEdge[]
  captions: LaidCaption[]
}

/* -------------------------------------------------------------------------- */
/* Geometry constants — roomy symbol tiles                                     */
/* -------------------------------------------------------------------------- */

export const CANVAS_W = 1320
/** Left gutter that carries each boundary's title. */
export const BAND_LABEL_W = 168
const LABEL_W = BAND_LABEL_W
const TOP_PAD = 28
const ZONE_PAD_X = 40
const ZONE_PAD_Y = 32
const GAP_X = 34
const GAP_Y = 38
const NODE_H = 110
const MAX_NODE_W = 224
const MIN_GUTTER = 58
const TRACK = 18
/** Right safety margin used only when no in-band riser is available. */
const CHANNEL_W = 96
const CHANNEL_PAD = 22
/** Half-width of the virtual anchor used for `@band` connectors. */
const VIRTUAL_HALF = 120
/** Height reserved for an optional row caption inside a band. */
const CAPTION_H = 26
/** Minimum clearance between a riser / label and a symbol tile. */
const CLEAR = 8
/** Connectors stay within this window around a symbol's centre. */
const ANCHOR_SPREAD = 52

type Pt = { x: number; y: number }
type Interval = { a: number; b: number }

type Placement = {
  spec: NodeSpec
  band: number
  row: number
  col: number
}

type RouteKind =
  | 'sideBySide'
  | 'adjDown'
  | 'adjUp'
  | 'sameBand'
  | 'nonAdjDown'
  | 'nonAdjUp'

type Route = {
  edge: EdgeSpec
  id: string
  src: Placement
  dst: Placement
  kind: RouteKind
  srcSide: Side
  dstSide: Side
  gutters: number[]
}

/* -------------------------------------------------------------------------- */
/* Root layout                                                                 */
/* -------------------------------------------------------------------------- */

export function layoutDiagram(spec: DiagramSpec): Layout {
  const placements: Placement[] = []
  spec.bands.forEach((band, bi) =>
    band.rows.forEach((row, ri) =>
      row.forEach((node, ci) =>
        placements.push({ spec: node, band: bi, row: ri, col: ci }),
      ),
    ),
  )
  const placeById = new Map(placements.map((p) => [p.spec.id, p]))
  const bandIdToIndex = new Map(spec.bands.map((b, i) => [b.id, i]))
  const bandCount = spec.bands.length
  const gutterCount = Math.max(0, bandCount - 1)

  const virtualPlacement = (id: string): Placement | undefined => {
    if (!id.startsWith('@')) return undefined
    const bi = bandIdToIndex.get(id.slice(1))
    if (bi == null) return undefined
    return { spec: { id, kind: 'data', title: '' }, band: bi, row: 1, col: 0 }
  }
  const resolve = (id: string) => placeById.get(id) ?? virtualPlacement(id)

  /* ---- 1. classify edges ------------------------------------------------- */

  const routes: Route[] = []
  for (let i = 0; i < spec.edges.length; i += 1) {
    const edge = spec.edges[i]
    const src = resolve(edge.from)
    const dst = resolve(edge.to)
    if (!src || !dst) continue
    const bi = src.band
    const bj = dst.band
    const id = edge.id ?? `e${i}`
    let kind: RouteKind = 'adjDown'
    let srcSide: Side = 'bottom'
    let dstSide: Side = 'top'
    const gutters: number[] = []

    if (bi === bj) {
      const adjacent = src.row === dst.row && Math.abs(src.col - dst.col) === 1
      if (adjacent) {
        // Side-by-side symbols: connect the right of one to the left of the
        // other (or left→right when the target sits to the left).
        kind = 'sideBySide'
        const leftToRight = src.col < dst.col
        srcSide = leftToRight ? 'right' : 'left'
        dstSide = leftToRight ? 'left' : 'right'
      } else {
        kind = 'sameBand'
        const below = bi < gutterCount
        srcSide = below ? 'bottom' : 'top'
        dstSide = below ? 'bottom' : 'top'
        gutters.push(below ? bi : bi - 1)
      }
    } else if (bj === bi + 1) {
      kind = 'adjDown'
      srcSide = 'bottom'
      dstSide = 'top'
      gutters.push(bi)
    } else if (bj === bi - 1) {
      kind = 'adjUp'
      srcSide = 'top'
      dstSide = 'bottom'
      gutters.push(bj)
    } else if (bj > bi + 1) {
      kind = 'nonAdjDown'
      srcSide = 'bottom'
      dstSide = 'top'
      gutters.push(bi, bj - 1)
    } else {
      kind = 'nonAdjUp'
      srcSide = 'top'
      dstSide = 'bottom'
      gutters.push(bi - 1, bj)
    }
    routes.push({ edge, id, src, dst, kind, srcSide, dstSide, gutters })
  }

  const gutterUse = new Array(Math.max(1, gutterCount)).fill(0)
  routes.forEach((r) => r.gutters.forEach((g) => (gutterUse[g] += 1)))
  const zoneW = CANVAS_W - LABEL_W - CHANNEL_W
  const zoneRight = LABEL_W + zoneW
  const channelX = (slot: number) =>
    Math.max(zoneRight + CHANNEL_PAD, CANVAS_W - CHANNEL_PAD - slot * TRACK)

  /* ---- 2. band rectangles + gutter heights ------------------------------ */

  const gutterH = Array.from({ length: Math.max(0, gutterCount) }, (_, g) =>
    Math.max(MIN_GUTTER, gutterUse[g] * TRACK + 32),
  )

  const bands: LaidBand[] = []
  let cursorY = TOP_PAD
  spec.bands.forEach((band, bi) => {
    const rows = band.rows.length
    let contentH = 0
    for (let r = 0; r < rows; r += 1) {
      if (band.rowLabels?.[r]) contentH += CAPTION_H
      contentH += NODE_H
      if (r < rows - 1) contentH += GAP_Y
    }
    const h = 2 * ZONE_PAD_Y + contentH
    bands.push({
      id: band.id,
      title: band.title,
      hint: band.hint,
      tone: band.tone,
      index: bi,
      x: LABEL_W,
      y: cursorY,
      w: zoneW,
      h,
    })
    cursorY += h
    if (bi < gutterCount) cursorY += gutterH[bi]
  })

  const gutterTop = bands.map((b) => b.y + b.h)

  /* ---- 3. node rectangles — evenly spread rows, centred when small ------ */

  const nodes: LaidNode[] = []
  const byId = new Map<string, LaidNode>()
  const captions: LaidCaption[] = []
  spec.bands.forEach((band, bi) => {
    const rect = bands[bi]
    const innerW = zoneW - 2 * ZONE_PAD_X
    let rowTop = rect.y + ZONE_PAD_Y
    band.rows.forEach((row, ri) => {
      const label = band.rowLabels?.[ri]
      if (label) {
        captions.push({
          id: `${band.id}-cap-${ri}`,
          text: label,
          tone: band.tone,
          x: rect.x + ZONE_PAD_X,
          y: rowTop,
          w: innerW,
        })
        rowTop += CAPTION_H
      }
      const n = row.length
      const nodeW = Math.min(MAX_NODE_W, (innerW - (n - 1) * GAP_X) / n)
      const total = n * nodeW + (n - 1) * GAP_X
      let x = rect.x + ZONE_PAD_X + (innerW - total) / 2
      const y = rowTop
      row.forEach((specNode) => {
        const node: LaidNode = {
          ...specNode,
          x,
          y,
          w: nodeW,
          h: NODE_H,
          band: bi,
          row: ri,
          cx: x + nodeW / 2,
          cy: y + NODE_H / 2,
        }
        nodes.push(node)
        byId.set(specNode.id, node)
        x += nodeW + GAP_X
      })
      rowTop += NODE_H + GAP_Y
    })
  })

  bands.forEach((band) => {
    const id = `@${band.id}`
    if (!routes.some((r) => r.src.spec.id === id || r.dst.spec.id === id)) return
    byId.set(id, {
      id,
      kind: 'data',
      title: '',
      x: band.x + band.w / 2 - VIRTUAL_HALF,
      y: band.y,
      w: VIRTUAL_HALF * 2,
      h: band.h,
      band: band.index,
      row: 1,
      cx: band.x + band.w / 2,
      cy: band.y + band.h / 2,
    })
  })

  /* ---- 4. free column gaps, so a riser can pass *between* symbols ------- */

  const nodeRangesByBand: Interval[][] = bands.map((_, bi) =>
    nodes
      .filter((n) => n.band === bi)
      .map((n) => ({ a: n.x, b: n.x + n.w }))
      .sort((p, q) => p.a - q.a),
  )

  const isFreeInBand = (x: number, bi: number): boolean => {
    const band = bands[bi]
    if (x < band.x + CLEAR || x > band.x + band.w - CLEAR) return false
    return !nodeRangesByBand[bi].some(
      (r) => x > r.a - CLEAR && x < r.b + CLEAR,
    )
  }

  const freeIntervals = (bi: number): Interval[] => {
    const band = bands[bi]
    const out: Interval[] = []
    let cursor = band.x + CLEAR
    const limit = band.x + band.w - CLEAR
    for (const r of nodeRangesByBand[bi]) {
      if (r.a - CLEAR > cursor) out.push({ a: cursor, b: r.a - CLEAR })
      cursor = Math.max(cursor, r.b + CLEAR)
    }
    if (cursor < limit) out.push({ a: cursor, b: limit })
    return out.filter((iv) => iv.b - iv.a > 6)
  }

  /* ---- 5. anchor assignment (spread stubs so stubs never stack) --------- */

  const groups = new Map<
    string,
    { nodeId: string; side: Side; entries: { key: string; other: number }[] }
  >()
  const addAnchor = (nodeId: string, side: Side, key: string, other: number) => {
    const gk = `${nodeId}|${side}`
    let group = groups.get(gk)
    if (!group) {
      group = { nodeId, side, entries: [] }
      groups.set(gk, group)
    }
    group.entries.push({ key, other })
  }
  routes.forEach((r) => {
    const srcCx = byId.get(r.src.spec.id)?.cx ?? 0
    const dstCx = byId.get(r.dst.spec.id)?.cx ?? 0
    addAnchor(r.src.spec.id, r.srcSide, `${r.id}|src`, dstCx)
    addAnchor(r.dst.spec.id, r.dstSide, `${r.id}|dst`, srcCx)
  })
  const anchors = new Map<string, Pt>()
  groups.forEach((group) => {
    const node = byId.get(group.nodeId)
    if (!node) return
    group.entries.sort((a, b) => a.other - b.other || a.key.localeCompare(b.key))
    const n = group.entries.length
    const vertical = group.side === 'top' || group.side === 'bottom'
    // Symbols are 52px tiles; keep every stub on the tile so a connector never
    // appears to stop in the empty space beside it.
    const window = Math.min(vertical ? node.w : node.h, ANCHOR_SPREAD)
    const tileMidY = node.y + ANCHOR_SPREAD / 2
    const center = vertical ? node.cx : tileMidY
    group.entries.forEach((entry, i) => {
      const t = n === 1 ? 0.5 : i / (n - 1)
      const offset = center + (t - 0.5) * window
      const pt: Pt =
        group.side === 'bottom'
          ? { x: offset, y: node.y + node.h }
          : group.side === 'top'
            ? { x: offset, y: node.y }
            : group.side === 'right'
              ? { x: node.cx + ANCHOR_SPREAD / 2, y: offset }
              : { x: node.cx - ANCHOR_SPREAD / 2, y: offset }
      anchors.set(entry.key, pt)
    })
  })

  // Every edge's vertical stubs, so a riser never lands on top of another
  // edge's line. A stub runs from its anchor into the adjacent gutter.
  type VSeg = { edgeId: string; x: number; y0: number; y1: number }
  const verticals: VSeg[] = []
  routes.forEach((r) => {
    const g0 = r.gutters[0]
    const g1 = r.gutters[r.gutters.length - 1]
    const addStub = (pt: Pt | undefined, g: number | undefined) => {
      if (!pt) return
      let a = pt.y
      let b = pt.y
      if (g != null) {
        a = Math.min(pt.y, gutterTop[g])
        b = Math.max(pt.y, gutterTop[g] + gutterH[g])
      }
      if (Math.abs(b - a) > 2) {
        verticals.push({ edgeId: r.id, x: pt.x, y0: Math.min(a, b), y1: Math.max(a, b) })
      }
    }
    addStub(anchors.get(`${r.id}|src`), g0)
    addStub(anchors.get(`${r.id}|dst`), g1)
  })

  /* ---- 6. orthogonal paths through gutters and free column gaps --------- */

  const trackCursor = new Array(Math.max(0, gutterCount)).fill(0)
  const trackY = (g: number) => {
    const y = gutterTop[g] + 16 + trackCursor[g] * TRACK
    trackCursor[g] += 1
    return y
  }
  let channelSeq = 0

  const verticalConflict = (id: string, x: number, y0: number, y1: number) =>
    verticals.some(
      (v) =>
        v.edgeId !== id &&
        Math.abs(v.x - x) < 12 &&
        Math.min(y1, v.y1) - Math.max(y0, v.y0) > 4,
    )

  const riserFor = (
    id: string,
    sx: number,
    dx: number,
    lo: number,
    hi: number,
    py0: number,
    py1: number,
  ): number | null => {
    const intervening: number[] = []
    for (let b = lo + 1; b < hi; b += 1) intervening.push(b)
    if (!intervening.length) return null
    const avg = (sx + dx) / 2
    const candidates: number[] = [avg, sx, dx]
    intervening.forEach((b) =>
      freeIntervals(b).forEach((iv) => candidates.push((iv.a + iv.b) / 2)),
    )
    const seen = new Set<number>()
    const unique = candidates.filter((c) => {
      const k = Math.round(c)
      if (seen.has(k)) return false
      seen.add(k)
      return true
    })
    unique.sort((a, b) => Math.abs(a - avg) - Math.abs(b - avg))
    for (const c of unique) {
      if (verticalConflict(id, c, py0, py1)) continue
      if (intervening.every((b) => isFreeInBand(c, b))) return c
    }
    return null
  }

  const edges: LaidEdge[] = []
  routes.forEach((r) => {
    const s = anchors.get(`${r.id}|src`)
    const d = anchors.get(`${r.id}|dst`)
    if (!s || !d) return
    const pts: Pt[] = [s]
    const push = (p: Pt) => {
      const last = pts[pts.length - 1]
      if (Math.abs(last.x - p.x) > 0.5 || Math.abs(last.y - p.y) > 0.5) pts.push(p)
    }
    const srcBand = r.src.band
    const dstBand = r.dst.band
    const lo = Math.min(srcBand, dstBand)
    const hi = Math.max(srcBand, dstBand)
    const interveningFree = (x: number) => {
      for (let b = lo + 1; b < hi; b += 1) if (!isFreeInBand(x, b)) return false
      return true
    }

    if (r.kind === 'sideBySide') {
      // Straight horizontal between the two symbol tiles.
      push(d)
    } else if (r.kind === 'adjDown' || r.kind === 'adjUp') {
      if (Math.abs(s.x - d.x) < 0.75) {
        push(d)
      } else {
        const y = trackY(r.gutters[0])
        push({ x: s.x, y })
        push({ x: d.x, y })
        push(d)
      }
    } else if (r.kind === 'sameBand') {
      if (Math.abs(s.x - d.x) < 0.75) {
        push(d)
      } else {
        const y = trackY(r.gutters[0])
        push({ x: s.x, y })
        push({ x: d.x, y })
        push(d)
      }
    } else {
      // non-adjacent: straight (unlabelled only — a label needs a gutter to sit
      // in) if near-aligned and clear, else a riser through a free column gap of
      // every band in between, else the outer channel.
      const sx = (s.x + d.x) / 2
      if (
        Math.abs(s.x - d.x) < 6 &&
        !r.edge.label &&
        interveningFree(sx) &&
        !verticalConflict(r.id, sx, s.y, d.y)
      ) {
        push(d)
        verticals.push({
          edgeId: r.id,
          x: sx,
          y0: Math.min(s.y, d.y),
          y1: Math.max(s.y, d.y),
        })
      } else {
        const y1 = trackY(r.gutters[0])
        const y2 = trackY(r.gutters[1])
        const riser = riserFor(
          r.id,
          s.x,
          d.x,
          lo,
          hi,
          Math.min(y1, y2),
          Math.max(y1, y2),
        )
        const midX = riser ?? channelX(channelSeq++)
        push({ x: s.x, y: y1 })
        push({ x: midX, y: y1 })
        push({ x: midX, y: y2 })
        push({ x: d.x, y: y2 })
        push(d)
        verticals.push({
          edgeId: r.id,
          x: midX,
          y0: Math.min(y1, y2),
          y1: Math.max(y1, y2),
        })
      }
    }

    const d0 = pts
      .map((p, i) => `${i === 0 ? 'M' : 'L'} ${round(p.x)} ${round(p.y)}`)
      .join(' ')
    const label = labelPoint(pts)
    edges.push({
      id: r.id,
      tone: r.edge.tone,
      d: d0,
      sx: s.x,
      sy: s.y,
      dx: d.x,
      dy: d.y,
      dashed: r.edge.dashed,
      label: r.edge.label,
      labelX: label?.x,
      labelY: label?.y,
    })
  })

  return { width: CANVAS_W, height: cursorY + TOP_PAD, bands, nodes, edges, captions }
}

function round(n: number): number {
  return Math.round(n * 10) / 10
}

/**
 * The midpoint of the longest *horizontal* segment (those run in empty
 * gutters, so a chip there never lands on a symbol), falling back to the
 * longest segment when the connector is purely vertical.
 */
function labelPoint(pts: Pt[]): Pt | undefined {
  if (pts.length < 2) return undefined
  let bestH = -1
  let bestHIdx = -1
  let best = 0
  let bestLen = -1
  for (let i = 0; i < pts.length - 1; i += 1) {
    const dx = Math.abs(pts[i + 1].x - pts[i].x)
    const dy = Math.abs(pts[i + 1].y - pts[i].y)
    const len = Math.hypot(dx, dy)
    if (len > bestLen) {
      bestLen = len
      best = i
    }
    if (dy < 1.5 && dx > bestH) {
      bestH = dx
      bestHIdx = i
    }
  }
  if (bestHIdx >= 0) {
    const a = pts[bestHIdx]
    const b = pts[bestHIdx + 1]
    return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
  }
  // No horizontal segment — put the chip in the first gutter the path enters,
  // never mid-band where it could land on a symbol.
  if (pts.length >= 2) {
    return { x: (pts[0].x + pts[pts.length - 1].x) / 2, y: pts[1].y }
  }
  const a = pts[best]
  const b = pts[best + 1]
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
}

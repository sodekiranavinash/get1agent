import {
  sectionSize,
  type FlowEdgeSpec,
  type FlowSectionSpec,
  type FlowSpec,
} from './flow.ts'

/** A group with everything but its position — `row` assigns `x`. */
export type FlowGroupSpec = Omit<FlowSectionSpec, 'x' | 'y'>

/** Horizontal gap between consecutive groups of a composed journey. */
const GAP = 48
/** The row every journey sits on. */
const ROW_Y = 56
/** The lane a response travels back along. */
const RETURN_Y = 12

/**
 * Lays groups left → right from `startX`, spacing each by its rendered width, so
 * a journey is authored as an ordered list of stages and reads the same way in
 * every sheet.
 */
export function row(
  groups: FlowGroupSpec[],
  { y = ROW_Y, startX = 16, gap = GAP }: { y?: number; startX?: number; gap?: number } = {},
): FlowSectionSpec[] {
  let x = startX
  return groups.map((group) => {
    const placed: FlowSectionSpec = { ...group, x, y }
    x += sectionSize(placed).w + gap
    return placed
  })
}

/**
 * Composes a journey: the groups left → right on one row, a connector from each
 * group to the next, and any `returns` drawn back along the top. The request
 * travels right, the response comes back left.
 */
export function compose(
  id: string,
  groups: FlowGroupSpec[],
  returns: FlowEdgeSpec[] = [],
): FlowSpec {
  const sections = row(groups)
  const edges: FlowEdgeSpec[] = []
  for (let i = 1; i < sections.length; i += 1) {
    edges.push({
      from: `@${sections[i - 1].id}`,
      to: `@${sections[i].id}`,
      tone: sections[i].tone,
    })
  }
  edges.push(...returns)
  return { id, sections, edges }
}

/**
 * The return leg of a round trip: leaves `from` at the top, travels back along
 * the top lane and enters the left edge of `to` — the client — so the response
 * visibly returns to where the request started.
 */
export function back(
  from: string,
  to: string,
  label: string,
  tone: FlowEdgeSpec['tone'],
  viaY = RETURN_Y,
): FlowEdgeSpec {
  return { from: `@${from}`, to: `@${to}`, tone, label, route: 'over', viaY, viaX: 8 }
}

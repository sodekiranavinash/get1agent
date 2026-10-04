import { useMemo, useState } from 'react'
import {
  AlertTriangle,
  Box,
  ChevronDown,
  ChevronRight,
  Database,
  Search,
  Sparkles,
  Wrench,
  Zap,
} from 'lucide-react'
import {
  formatDurationMs,
  formatTokens,
  observationMeta,
  usageTotals,
  type TraceObservation,
} from '../../lib/lab'

export type TraceView = 'tree' | 'waterfall'

const TYPE_ICON: Record<string, typeof Sparkles> = {
  GENERATION: Sparkles,
  TOOL: Wrench,
  EVENT: Zap,
  RETRIEVER: Database,
  SPAN: Box,
}

type Node = {
  obs: TraceObservation
  children: Node[]
  depth: number
  hasChildren: boolean
}

function buildTree(observations: TraceObservation[]): Node[] {
  const byId = new Map<string, Node>()
  for (const obs of observations) {
    byId.set(obs.id, { obs, children: [], depth: 0, hasChildren: false })
  }
  const roots: Node[] = []
  for (const obs of observations) {
    const node = byId.get(obs.id)
    if (!node) continue
    const parent = obs.parentObservationId ? byId.get(obs.parentObservationId) : undefined
    if (parent && parent !== node) {
      parent.children.push(node)
      parent.hasChildren = true
    } else {
      roots.push(node)
    }
  }
  const assign = (nodes: Node[], depth: number) => {
    nodes.sort((a, b) => (a.obs.startTime ?? 0) - (b.obs.startTime ?? 0))
    for (const node of nodes) {
      node.depth = depth
      assign(node.children, depth + 1)
    }
  }
  assign(roots, 0)
  return roots
}

function flatten(nodes: Node[], collapsed: Set<string>, out: Node[] = []): Node[] {
  for (const node of nodes) {
    out.push(node)
    if (node.hasChildren && !collapsed.has(node.obs.id)) {
      flatten(node.children, collapsed, out)
    }
  }
  return out
}

function depthMap(roots: Node[]): Map<string, number> {
  const map = new Map<string, number>()
  const walk = (nodes: Node[]) => {
    for (const node of nodes) {
      map.set(node.obs.id, node.depth)
      walk(node.children)
    }
  }
  walk(roots)
  return map
}

function timeAxis(observations: TraceObservation[]) {
  const starts = observations
    .map((obs) => obs.startTime)
    .filter((value): value is number => typeof value === 'number')
  const ends = observations
    .map((obs) => obs.endTime)
    .filter((value): value is number => typeof value === 'number')
  const min = starts.length ? Math.min(...starts) : 0
  const max = ends.length ? Math.max(...ends) : min
  return { min, total: Math.max(max - min, 1) }
}

function TypeIcon({ type, error }: { type?: string; error: boolean }) {
  const Icon = TYPE_ICON[String(type || 'SPAN').toUpperCase()] ?? Box
  const meta = observationMeta(type)
  return (
    <Icon className={`size-3.5 shrink-0 ${error ? 'text-rose' : meta.text}`} strokeWidth={2} />
  )
}

function Timer({ obs }: { obs: TraceObservation }) {
  const tokens = usageTotals(obs.usage).total
  return (
    <span className="shrink-0 font-mono text-[10.5px] tabular-nums text-subtle">
      {tokens ? `${formatTokens(tokens)} · ` : ''}
      {formatDurationMs(obs.durationMs)}
    </span>
  )
}

function TreeRow({
  node,
  selectedId,
  collapsed,
  min,
  total,
  index,
  onSelect,
  onToggle,
}: {
  node: Node
  selectedId: string | null
  collapsed: Set<string>
  min: number
  total: number
  index: number
  onSelect: (obs: TraceObservation) => void
  onToggle: (id: string) => void
}) {
  const { obs } = node
  const meta = observationMeta(obs.type)
  const selected = obs.id === selectedId
  const isError = obs.level === 'ERROR'
  const duration = Math.max(obs.durationMs ?? 0, 0)
  const offset = Math.max(0, (obs.startTime ?? min) - min)
  const left = Math.min(100, (offset / total) * 100)
  const width = Math.max(0.8, Math.min(100 - left, (duration / total) * 100))

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onSelect(obs)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          onSelect(obs)
        }
      }}
      className={`animate-trace-row group relative flex w-full cursor-pointer items-center gap-2 py-2 pr-3 text-left transition-colors ${
        selected ? 'bg-accent-soft' : 'hover:bg-raised/50'
      }`}
      style={{
        paddingLeft: 10 + node.depth * 16,
        animationDelay: `${Math.min(index * 12, 200)}ms`,
      }}
    >
      {selected ? <span className="absolute inset-y-1 left-0 w-0.5 rounded-r bg-accent" /> : null}
      {node.hasChildren ? (
        <button
          type="button"
          tabIndex={-1}
          onClick={(event) => {
            event.stopPropagation()
            onToggle(obs.id)
          }}
          className="shrink-0 text-subtle transition-transform hover:text-foreground"
        >
          {collapsed.has(obs.id) ? (
            <ChevronRight className="size-3.5" />
          ) : (
            <ChevronDown className="size-3.5" />
          )}
        </button>
      ) : (
        <span className="w-3.5 shrink-0" />
      )}
      <TypeIcon type={obs.type} error={isError} />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-3">
          <span className="flex min-w-0 items-center gap-1.5">
            <span
              className={`truncate font-mono text-[12px] ${isError ? 'text-rose' : 'text-foreground'}`}
              title={obs.name}
            >
              {obs.name}
            </span>
            {isError ? <AlertTriangle className="size-3 shrink-0 text-rose" /> : null}
          </span>
          <Timer obs={obs} />
        </span>
        <span className="relative mt-1 block h-1.5 overflow-hidden rounded-full bg-raised/70">
          <span
            className={`absolute inset-y-0 rounded-full ${isError ? 'bg-rose' : meta.dot} opacity-90 transition-all duration-500 ease-out`}
            style={{ left: `${left}%`, width: `${width}%` }}
          />
        </span>
      </span>
    </div>
  )
}

function WaterfallView({
  observations,
  selectedId,
  onSelect,
}: {
  observations: TraceObservation[]
  selectedId: string | null
  onSelect: (obs: TraceObservation) => void
}) {
  const roots = useMemo(() => buildTree(observations), [observations])
  const depths = useMemo(() => depthMap(roots), [roots])
  const { min, total } = useMemo(() => timeAxis(observations), [observations])
  const rows = useMemo(
    () => [...observations].sort((a, b) => (a.startTime ?? 0) - (b.startTime ?? 0)),
    [observations],
  )
  const ticks = [0, 0.25, 0.5, 0.75, 1]

  return (
    <div className="flex flex-col">
      <div className="flex items-center border-b border-border bg-surface/60 py-1.5 pr-3 pl-3 text-[10px] text-subtle">
        <span className="w-[46%] shrink-0 font-semibold tracking-wider uppercase">Stage</span>
        <span className="relative h-4 flex-1">
          {ticks.map((fraction) => (
            <span
              key={fraction}
              className="absolute top-0 -translate-x-1/2 font-mono tabular-nums"
              style={{ left: `${fraction * 100}%` }}
            >
              {fraction === 0 ? '0' : formatDurationMs(total * fraction)}
            </span>
          ))}
        </span>
        <span className="w-14 shrink-0" />
      </div>
      <ul className="divide-y divide-border/30">
        {rows.map((obs, index) => {
          const depth = depths.get(obs.id) ?? 0
          const meta = observationMeta(obs.type)
          const isError = obs.level === 'ERROR'
          const selected = obs.id === selectedId
          const duration = Math.max(obs.durationMs ?? 0, 0)
          const offset = Math.max(0, (obs.startTime ?? min) - min)
          const left = Math.min(100, (offset / total) * 100)
          const width = Math.max(0.8, Math.min(100 - left, (duration / total) * 100))
          return (
            <li key={obs.id}>
              <button
                type="button"
                onClick={() => onSelect(obs)}
                className={`animate-trace-row flex w-full items-center py-1.5 pr-3 text-left transition-colors ${
                  selected ? 'bg-accent-soft' : 'hover:bg-raised/40'
                }`}
                style={{
                  paddingLeft: 12 + Math.min(depth, 3) * 10,
                  animationDelay: `${Math.min(index * 12, 200)}ms`,
                }}
              >
                <span className="flex w-[46%] shrink-0 items-center gap-1.5 pr-2">
                  <TypeIcon type={obs.type} error={isError} />
                  <span
                    className={`truncate font-mono text-[11.5px] ${isError ? 'text-rose' : 'text-foreground'}`}
                    title={obs.name}
                  >
                    {obs.name}
                  </span>
                </span>
                <span className="relative h-5 flex-1 rounded bg-raised/30">
                  {ticks.map((fraction) => (
                    <span
                      key={fraction}
                      className="absolute inset-y-0 w-px bg-border/50"
                      style={{ left: `${fraction * 100}%` }}
                    />
                  ))}
                  <span
                    className={`absolute inset-y-0.5 rounded ${isError ? 'bg-rose' : meta.dot} opacity-90 transition-all duration-500 ease-out`}
                    style={{ left: `${left}%`, width: `${width}%` }}
                    title={`${obs.name} · ${formatDurationMs(obs.durationMs)}`}
                  />
                </span>
                <span className="w-14 shrink-0 text-right font-mono text-[10.5px] tabular-nums text-subtle">
                  {formatDurationMs(obs.durationMs)}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export function ObservationList({
  observations,
  selectedId,
  onSelect,
  view,
}: {
  observations: TraceObservation[]
  selectedId: string | null
  onSelect: (obs: TraceObservation) => void
  view: TraceView
}) {
  const roots = useMemo(() => buildTree(observations), [observations])
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const [query, setQuery] = useState('')
  const { min, total } = useMemo(() => timeAxis(observations), [observations])

  const needle = query.trim().toLowerCase()
  const filtered = useMemo(
    () => (needle ? observations.filter((obs) => obs.name.toLowerCase().includes(needle)) : observations),
    [observations, needle],
  )
  // While filtering, show matches flat (no indentation for a missing parent).
  const rows = useMemo(
    () =>
      needle
        ? filtered.map((obs) => ({ obs, children: [], depth: 0, hasChildren: false }))
        : flatten(roots, collapsed),
    [needle, filtered, roots, collapsed],
  )

  function toggle(id: string) {
    setCollapsed((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (observations.length === 0) {
    return (
      <p className="px-4 py-6 text-[12.5px] text-subtle">
        No observations were recorded for this trace.
      </p>
    )
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-border px-3 py-2">
        <div className="relative">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-subtle" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter stages…"
            className="w-full rounded-md border border-border bg-canvas py-1.5 pr-2.5 pl-8 text-[12px] text-foreground outline-none placeholder:text-subtle focus:border-accent/50"
          />
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        {view === 'waterfall' ? (
          <WaterfallView
            observations={filtered}
            selectedId={selectedId}
            onSelect={onSelect}
          />
        ) : rows.length === 0 ? (
          <p className="px-4 py-6 text-[12.5px] text-subtle">No stages match “{query}”.</p>
        ) : (
          <ul className="py-1">
            {rows.map((node, index) => (
              <li key={node.obs.id}>
                <TreeRow
                  node={node}
                  selectedId={selectedId}
                  collapsed={collapsed}
                  min={min}
                  total={total}
                  index={index}
                  onSelect={onSelect}
                  onToggle={toggle}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

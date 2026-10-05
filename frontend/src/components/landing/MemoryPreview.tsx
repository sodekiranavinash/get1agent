import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Bot,
  Brain,
  Check,
  History,
  Lightbulb,
  MessagesSquare,
  Star,
} from 'lucide-react'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useInView } from '../../hooks/useInView'

type NodeId = 'chat' | 'memory' | 'agent'
type PhaseState = 'idle' | 'active' | 'done'

type NodeSpec = {
  id: NodeId
  label: string
  sub: string
  icon: LucideIcon
  /** Centre in the 460 × 240 viewBox. */
  cx: number
  cy: number
  /** Card width in viewBox units. */
  w: number
}

const NODES: NodeSpec[] = [
  {
    id: 'chat',
    label: 'Chat · today',
    sub: 'research agent',
    icon: MessagesSquare,
    cx: 58,
    cy: 120,
    w: 104,
  },
  {
    id: 'memory',
    label: 'Memory',
    sub: 'shared store',
    icon: Brain,
    cx: 230,
    cy: 120,
    w: 112,
  },
  {
    id: 'agent',
    label: 'New session',
    sub: 'support swarm',
    icon: Bot,
    cx: 402,
    cy: 120,
    w: 112,
  },
]

const STORE_EDGE = 'M110 120 L174 120'
const RECALL_EDGE = 'M286 120 L346 120'

const CHIPS = [
  { label: 'Facts', icon: Lightbulb },
  { label: 'Preferences', icon: Star },
  { label: 'Past decisions', icon: History },
]

// 0 start · 1 storing · 2 saved · 3 recalling · 4 recalled · 5 shared (hold).
const TOTAL = 5

const LOG = [
  'A new conversation starts.',
  'Storing facts, preferences and decisions…',
  '3 memories saved to the shared store.',
  'Recalling in a different session…',
  'Recalled · “prefers concise, cited answers”.',
  'Every agent and workflow shares the same memory.',
]

const MOBILE_STEPS = [
  { icon: MessagesSquare, text: 'A conversation extracts facts and preferences.' },
  { icon: Brain, text: 'They are saved to one shared, user-scoped memory.' },
  { icon: Bot, text: 'The next agent or swarm recalls them automatically.' },
  { icon: Check, text: 'Erase any record — or all of it — from the Memory page.' },
]

function MemoryNode({ node, state }: { node: NodeSpec; state: PhaseState }) {
  const Icon = node.icon
  return (
    <div
      className={`absolute flex -translate-x-1/2 -translate-y-1/2 items-center gap-2 rounded-xl border px-2.5 py-1.5 backdrop-blur transition-all duration-300 ${
        state === 'active'
          ? 'border-accent bg-accent-soft text-foreground shadow-[0_0_0_3px_var(--app-accent-soft)]'
          : state === 'done'
            ? 'border-success/40 bg-surface/90 text-foreground'
            : 'border-border bg-surface/80 text-muted'
      }`}
      style={{
        left: `${(node.cx / 460) * 100}%`,
        top: `${(node.cy / 240) * 100}%`,
        width: `${(node.w / 460) * 100}%`,
      }}
    >
      <span
        className={`flex size-5 shrink-0 items-center justify-center rounded-md ${
          state === 'active'
            ? 'text-accent'
            : state === 'done'
              ? 'text-success'
              : 'text-subtle'
        }`}
      >
        {state === 'done' ? <Check className="size-3" /> : <Icon className="size-3" />}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[10.5px] font-medium leading-tight">
          {node.label}
        </span>
        <span className="block truncate text-[9px] leading-tight text-subtle">
          {node.sub}
        </span>
      </span>
    </div>
  )
}

/**
 * Agent memory: a fact told in one conversation is stored in a single,
 * user-scoped memory and recalled later by a different agent. The dashed
 * connectors carry the flow, the memory node consolidates, and the chips show
 * what is kept. Self-playing and looping while in view.
 */
export function MemoryPreview() {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 })
  // Under reduced motion the flow is simply shown complete.
  const [tick, setTick] = useState(() => (reduced ? TOTAL : 0))

  useEffect(() => {
    if (reduced || !inView) return
    const delay = tick === 0 ? 600 : tick >= TOTAL ? 3000 : 900
    const handle = window.setTimeout(() => {
      setTick((current) => (current >= TOTAL ? 0 : current + 1))
    }, delay)
    return () => window.clearTimeout(handle)
  }, [tick, inView, reduced])

  const active = !reduced && inView
  const showStore = tick >= 1 && tick < TOTAL
  const showRecall = tick >= 3 && tick < TOTAL
  const chipsShown = tick >= 2
  const event = LOG[Math.min(tick, LOG.length - 1)]

  const stateOf = (id: NodeId): PhaseState => {
    if (id === 'chat') return tick === 0 ? 'active' : 'done'
    if (id === 'memory') return tick >= 4 ? 'done' : tick >= 1 ? 'active' : 'idle'
    return tick >= TOTAL ? 'done' : tick >= 3 ? 'active' : 'idle'
  }

  const edge = (d: string, flowing: boolean) => (
    <g key={d}>
      <path d={d} fill="none" stroke="var(--app-border)" strokeWidth={1.5} />
      <path
        d={d}
        fill="none"
        stroke="var(--app-accent)"
        strokeWidth={1.5}
        strokeDasharray="3 9"
        className={active ? 'animate-dash' : ''}
      />
      {active && flowing ? (
        <circle r="2.6" fill="var(--app-accent)">
          <animateMotion dur="1.5s" repeatCount="indefinite" path={d} />
        </circle>
      ) : null}
    </g>
  )

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-16 -left-16 size-44 rounded-full bg-violet-soft blur-3xl"
      />

      <div className="relative flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Brain className="size-3.5 shrink-0 text-accent" />
          <span className="truncate text-[12px] font-semibold text-foreground">
            Agent memory
          </span>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-violet/40 bg-violet-soft px-2 py-0.5 text-[10.5px] font-semibold text-violet">
          shared across agents
        </span>
      </div>

      {/* Desktop / tablet: memory map. */}
      <div className="app-grid-bg relative mt-4 hidden aspect-[460/240] overflow-hidden rounded-xl border border-border/70 bg-canvas/50 sm:block">
        <svg
          viewBox="0 0 460 240"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label="Memory stored in one conversation is recalled by another agent"
        >
          {edge(STORE_EDGE, showStore)}
          {edge(RECALL_EDGE, showRecall)}
        </svg>
        {NODES.map((node) => (
          <MemoryNode key={node.id} node={node} state={stateOf(node.id)} />
        ))}
      </div>

      {/* Phones: a compact list of the same flow. */}
      <ol className="mt-4 space-y-1.5 sm:hidden">
        {MOBILE_STEPS.map(({ icon: Icon, text }, index) => (
          <li
            key={text}
            className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 ${
              index <= tick
                ? 'border-accent/40 bg-accent-soft'
                : 'border-border/70 bg-canvas/50'
            }`}
          >
            <span
              className={`flex size-4 shrink-0 items-center justify-center rounded-full border ${
                index <= tick ? 'border-accent text-accent' : 'border-border text-subtle'
              }`}
            >
              <Icon className="size-2.5" />
            </span>
            <span className="text-[11px] leading-snug text-muted">{text}</span>
          </li>
        ))}
      </ol>

      {/* Category chips: what is kept. */}
      <div className="relative mt-3 flex flex-wrap items-center gap-1.5">
        {CHIPS.map(({ label, icon: Icon }, index) => (
          <span
            key={label}
            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10.5px] transition-all duration-300 ${
              chipsShown
                ? 'border-violet/40 bg-violet-soft text-violet'
                : 'border-border bg-raised/50 text-subtle opacity-60'
            }`}
            style={{ transitionDelay: `${index * 90}ms` }}
          >
            <Icon className="size-2.5" />
            {label}
          </span>
        ))}
        <span
          className={`ml-auto inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold transition-colors duration-300 ${
            chipsShown
              ? 'border-success/40 bg-success-soft text-success'
              : 'border-border bg-raised/50 text-subtle'
          }`}
        >
          {chipsShown ? <Check className="size-2.5" /> : null}
          {chipsShown ? '3 saved' : 'empty'}
        </span>
      </div>

      {/* Live event log. */}
      <div className="relative mt-3 flex items-center gap-2 overflow-hidden rounded-lg border border-border bg-canvas/70 px-2.5 py-1.5">
        <Brain className="size-3 shrink-0 text-accent" />
        <span key={tick} className="animate-pop min-w-0 truncate font-mono text-[10px] text-muted">
          {event}
        </span>
      </div>
    </div>
  )
}

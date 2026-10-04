import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Bot,
  Check,
  Database,
  GitMerge,
  Globe,
  Network,
  Sparkles,
} from 'lucide-react'
import { Segmented } from '../ui/Segmented'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useInView } from '../../hooks/useInView'

type Mode = 'Graph' | 'Swarm'

const MODES = ['Graph', 'Swarm'] as const

type NodeId = 'query' | 'host' | 'a' | 'b' | 'synth' | 'answer'

type NodeSpec = {
  id: NodeId
  label: string
  icon: LucideIcon
  /** Centre in the 460 × 200 viewBox. */
  cx: number
  cy: number
  /** Card width in viewBox units. */
  w: number
}

type Phase = {
  active: NodeId[]
  label: string
  detail: string
}

const GRAPH_NODES: NodeSpec[] = [
  { id: 'query', label: 'Query', icon: Sparkles, cx: 45, cy: 100, w: 74 },
  { id: 'a', label: 'Docs', icon: Database, cx: 222, cy: 40, w: 86 },
  { id: 'b', label: 'Market', icon: Globe, cx: 222, cy: 160, w: 86 },
  { id: 'synth', label: 'Synthesizer', icon: GitMerge, cx: 404, cy: 100, w: 104 },
]

const SWARM_NODES: NodeSpec[] = [
  { id: 'host', label: 'Host', icon: Bot, cx: 42, cy: 100, w: 72 },
  { id: 'a', label: 'Docs', icon: Database, cx: 162, cy: 100, w: 78 },
  { id: 'b', label: 'Market', icon: Globe, cx: 282, cy: 100, w: 78 },
  { id: 'answer', label: 'Answer', icon: Check, cx: 410, cy: 100, w: 88 },
]

const GRAPH_EDGES = [
  'M45 100 C118 100 140 40 222 40',
  'M45 100 C118 100 140 160 222 160',
  'M222 40 C300 40 322 100 404 100',
  'M222 160 C300 160 322 100 404 100',
]

const SWARM_EDGES = [
  'M42 100 L162 100',
  'M162 100 L282 100',
  'M282 100 L410 100',
]

const GRAPH_PHASES: Phase[] = [
  { active: ['query'], label: 'Dispatch', detail: 'The host sends one brief to both agents.' },
  { active: ['a', 'b'], label: 'Run in parallel', detail: 'Docs and Market work at the same time.' },
  { active: ['synth'], label: 'Synthesize', detail: 'The host merges both outputs into the answer.' },
]

const SWARM_PHASES: Phase[] = [
  { active: ['host'], label: 'Host starts', detail: 'The host owns the prompt and the question.' },
  { active: ['a'], label: 'Handoff → Docs', detail: 'Control passes with handoff_to_agent.' },
  { active: ['b'], label: 'Handoff → Market', detail: 'Docs passes control to Market.' },
  { active: ['answer'], label: 'Answer', detail: 'The last agent returns the final answer.' },
]

const MODE_MS = 7500
const STEP_MS = 1050

type PhaseState = 'idle' | 'active' | 'done'

function WorkflowNode({
  node,
  state,
}: {
  node: NodeSpec
  state: PhaseState
}) {
  const Icon = node.icon
  return (
    <div
      className={`absolute flex -translate-x-1/2 -translate-y-1/2 items-center justify-center gap-1.5 rounded-lg border px-2 py-1.5 backdrop-blur transition-all duration-300 ${
        state === 'active'
          ? 'border-accent bg-accent-soft text-foreground shadow-[0_0_0_3px_var(--app-accent-soft)]'
          : state === 'done'
            ? 'border-success/40 bg-surface/90 text-foreground'
            : 'border-border bg-surface/80 text-muted'
      }`}
      style={{
        left: `${(node.cx / 460) * 100}%`,
        top: `${(node.cy / 200) * 100}%`,
        width: `${(node.w / 460) * 100}%`,
      }}
    >
      {state === 'active' ? (
        <span className="absolute -inset-1 animate-pulse-soft rounded-xl border border-accent/50" />
      ) : null}
      <span
        className={`flex size-4 shrink-0 items-center justify-center rounded ${
          state === 'active'
            ? 'text-accent'
            : state === 'done'
              ? 'text-success'
              : 'text-subtle'
        }`}
      >
        {state === 'done' ? <Check className="size-3" /> : <Icon className="size-3" />}
      </span>
      <span className="truncate text-[10.5px] font-medium">{node.label}</span>
    </div>
  )
}

/**
 * A miniature workflow canvas showing the two orchestration modes the runtime
 * supports — deterministic **Graph** and dynamic **Swarm**. The mode switches
 * on its own so both are always seen, and each node lights up in sequence to
 * show how control actually moves. The segmented control still lets a visitor
 * drive it manually.
 */
export function WorkflowPreview() {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 })
  const [mode, setMode] = useState<Mode>('Graph')
  const flows = mode === 'Graph' ? GRAPH_PHASES : SWARM_PHASES
  // Under reduced motion both nodes and phases are shown complete.
  const [step, setStep] = useState(() => (reduced ? flows.length : 0))
  const nodes = mode === 'Graph' ? GRAPH_NODES : SWARM_NODES
  const edges = mode === 'Graph' ? GRAPH_EDGES : SWARM_EDGES

  // Rotate modes automatically; a manual pick resets this timer.
  useEffect(() => {
    if (reduced || !inView) return
    const timer = window.setTimeout(
      () => setMode((m) => (m === 'Graph' ? 'Swarm' : 'Graph')),
      MODE_MS,
    )
    return () => window.clearTimeout(timer)
  }, [mode, reduced, inView])

  // Walk the phases of the current mode, pausing on the finished state.
  useEffect(() => {
    if (reduced || !inView) return
    setStep(0)
    let cancelled = false
    let handle = 0
    let current = 0
    const run = () => {
      if (cancelled) return
      current += 1
      if (current > flows.length) {
        handle = window.setTimeout(() => {
          if (cancelled) return
          current = 0
          setStep(0)
          handle = window.setTimeout(run, 500)
        }, 1800)
        return
      }
      setStep(current)
      handle = window.setTimeout(run, STEP_MS)
    }
    handle = window.setTimeout(run, 450)
    return () => {
      cancelled = true
      window.clearTimeout(handle)
    }
  }, [mode, flows.length, reduced, inView])

  const finished = step >= flows.length
  const current = finished ? null : flows[step - 1]

  const stateOf = (id: NodeId): PhaseState => {
    if (finished) return 'done'
    const reachedAt = flows.findIndex((phase) => phase.active.includes(id))
    if (reachedAt === -1) return 'idle'
    if (flows[step - 1]?.active.includes(id)) return 'active'
    return reachedAt < step - 1 ? 'done' : 'idle'
  }

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2">
          <Network className="size-3.5 shrink-0 text-accent" />
          <span className="truncate text-[12px] font-semibold text-foreground">
            Multi-agent workflow
          </span>
          {!reduced ? (
            <span className="hidden shrink-0 items-center gap-1 rounded-full border border-border bg-canvas/60 px-1.5 py-0.5 text-[9.5px] font-medium text-subtle sm:inline-flex">
              <span className="size-1.5 animate-pulse rounded-full bg-accent" />
              auto
            </span>
          ) : null}
        </div>
        <Segmented options={MODES} value={mode} size="sm" onChange={setMode} />
      </div>

      {/* Desktop / tablet: node map. */}
      <div className="app-grid-bg relative mt-4 hidden aspect-[460/200] overflow-hidden rounded-xl border border-border/70 bg-canvas/50 sm:block">
        <svg
          viewBox="0 0 460 200"
          preserveAspectRatio="none"
          className="absolute inset-0 h-full w-full"
          role="img"
          aria-label={`${mode} mode workflow diagram`}
        >
          {edges.map((d) => (
            <g key={d}>
              <path d={d} fill="none" stroke="var(--app-border)" strokeWidth={1.5} />
              <path
                d={d}
                fill="none"
                stroke="var(--app-accent)"
                strokeWidth={1.5}
                strokeDasharray="3 9"
                className={reduced || !inView ? '' : 'animate-dash'}
              />
              {!reduced && inView ? (
                <circle r="2.4" fill="var(--app-accent)">
                  <animateMotion dur="1.6s" repeatCount="indefinite" path={d} />
                </circle>
              ) : null}
            </g>
          ))}
        </svg>
        {nodes.map((node) => (
          <WorkflowNode key={node.id} node={node} state={stateOf(node.id)} />
        ))}
      </div>

      {/* Phones: a compact vertical flow of the same phases. */}
      <ol className="mt-4 space-y-1.5 sm:hidden">
        {flows.map((phase, index) => {
          const active = !finished && index === step - 1
          const done = finished || index < step - 1
          return (
            <li
              key={phase.label}
              className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 transition-colors ${
                active
                  ? 'border-accent/40 bg-accent-soft'
                  : 'border-border/70 bg-canvas/50'
              }`}
            >
              <span
                className={`flex size-4 shrink-0 items-center justify-center rounded-full border text-[9px] font-semibold ${
                  active
                    ? 'border-accent text-accent'
                    : done
                      ? 'border-success/40 text-success'
                      : 'border-border text-subtle'
                }`}
              >
                {done ? <Check className="size-2.5" /> : index + 1}
              </span>
              <span className="min-w-0">
                <span className="block text-[11.5px] font-medium text-foreground">
                  {phase.label}
                </span>
                <span className="block text-[10.5px] leading-snug text-subtle">
                  {phase.detail}
                </span>
              </span>
            </li>
          )
        })}
      </ol>

      {/* Live status line. */}
      <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${
            finished
              ? 'border-success/40 bg-success-soft text-success'
              : 'border-accent/40 bg-accent-soft text-accent'
          }`}
        >
          <span className="relative flex size-1.5">
            {!finished ? (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-70" />
            ) : null}
            <span
              className={`relative inline-flex size-1.5 rounded-full ${finished ? 'bg-success' : 'bg-accent'}`}
            />
          </span>
          {finished ? 'Complete' : `${mode} · step ${step}/${flows.length}`}
        </span>
        <span className="min-w-0 truncate text-[11px] text-muted">
          {current
            ? `${current.label} — ${current.detail}`
            : finished
              ? 'The host synthesized the final answer.'
              : 'Preparing the run…'}
        </span>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Network } from 'lucide-react'
import { Segmented } from '../ui/Segmented'

type Mode = 'Graph' | 'Swarm'

const MODES = ['Graph', 'Swarm'] as const

const CAPTIONS: Record<Mode, string> = {
  Graph:
    'Deterministic pipeline — the host dispatches to agents in parallel, then synthesizes their outputs into the final answer.',
  Swarm:
    'Dynamic handoff — the host is the entry point and passes control to whichever teammate fits the task.',
}

type NodeSpec = {
  x: number
  y: number
  w: number
  label: string
  accent?: boolean
}

const GRAPH_NODES: NodeSpec[] = [
  { x: 6, y: 82, w: 78, label: 'Query' },
  { x: 172, y: 22, w: 96, label: 'Agent A' },
  { x: 172, y: 142, w: 96, label: 'Agent B' },
  { x: 356, y: 82, w: 100, label: 'Synthesizer', accent: true },
]

const SWARM_NODES: NodeSpec[] = [
  { x: 4, y: 82, w: 74, label: 'Host', accent: true },
  { x: 120, y: 82, w: 80, label: 'Agent A' },
  { x: 236, y: 82, w: 80, label: 'Agent B' },
  { x: 352, y: 82, w: 104, label: 'Answer' },
]

const GRAPH_EDGES = [
  'M84 100 C126 100 132 40 172 40',
  'M84 100 C126 100 132 160 172 160',
  'M268 40 C312 40 318 100 356 100',
  'M268 160 C312 160 318 100 356 100',
]

const SWARM_EDGES = [
  'M78 100 L120 100',
  'M200 100 L236 100',
  'M316 100 L352 100',
]

const NODE_H = 36

function WorkflowNode({ x, y, w, label, accent }: NodeSpec) {
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={w}
        height={NODE_H}
        rx={8}
        fill="var(--app-surface)"
        stroke={accent ? 'var(--app-accent)' : 'var(--app-border)'}
        strokeWidth={1.5}
      />
      <text
        x={x + w / 2}
        y={y + NODE_H / 2 + 4}
        textAnchor="middle"
        fill="var(--app-foreground)"
        fontSize={11}
        fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
      >
        {label}
      </text>
    </g>
  )
}

function WorkflowEdge({ d }: { d: string }) {
  return (
    <>
      <path d={d} fill="none" stroke="var(--app-border)" strokeWidth={1.5} />
      <path
        d={d}
        fill="none"
        stroke="var(--app-accent)"
        strokeWidth={1.5}
        strokeDasharray="3 9"
        className="animate-dash"
      />
    </>
  )
}

/**
 * A miniature workflow canvas with the two orchestration modes the runtime
 * supports: deterministic **Graph** and dynamic **Swarm**. Edges carry flowing
 * dashes to show direction.
 */
export function WorkflowPreview() {
  const [mode, setMode] = useState<Mode>('Graph')
  const nodes = mode === 'Graph' ? GRAPH_NODES : SWARM_NODES
  const edges = mode === 'Graph' ? GRAPH_EDGES : SWARM_EDGES

  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Network className="size-3.5 shrink-0 text-accent" />
          <span className="text-[12px] font-semibold text-foreground">Workflow</span>
        </div>
        <Segmented options={MODES} value={mode} size="sm" onChange={setMode} />
      </div>

      <div className="app-grid-bg mt-4 rounded-xl border border-border/70 bg-canvas/50 p-2">
        <svg viewBox="0 0 460 200" className="h-auto w-full" role="img" aria-label={`${mode} mode workflow diagram`}>
          {edges.map((d) => (
            <WorkflowEdge key={d} d={d} />
          ))}
          {nodes.map((node) => (
            <WorkflowNode key={node.label} {...node} />
          ))}
        </svg>
      </div>

      <p className="mt-3 text-[11.5px] leading-relaxed text-subtle">{CAPTIONS[mode]}</p>
    </div>
  )
}

import { useEffect, useMemo, useState } from 'react'
import {
  ArrowRight,
  Check,
  ChevronDown,
  Circle,
  Crown,
  Loader2,
  TriangleAlert,
  Wrench,
} from 'lucide-react'
import { Badge } from '../ui/Badge'
import { agentModelLabel } from '../../lib/agents'
import { formatDuration } from '../../lib/chat'
import type {
  WorkflowNodeRun,
  WorkflowRunFields,
  WorkflowToolCall,
} from '../../lib/workflowRun'
import type { WorkflowMode } from '../../lib/workflows'

function StatusIcon({ status }: { status: WorkflowNodeRun['status'] }) {
  if (status === 'running') return <Loader2 className="size-3.5 animate-spin text-accent" />
  if (status === 'done') return <Check className="size-3.5 text-success" />
  if (status === 'error') return <TriangleAlert className="size-3.5 text-accent" />
  return <Circle className="size-3.5 text-subtle" />
}

function ToolRow({ tool }: { tool: WorkflowToolCall }) {
  const [open, setOpen] = useState(false)
  const hasDetail = Boolean(tool.input || tool.output)
  return (
    <div className="rounded-lg border border-border bg-canvas/60">
      <button
        type="button"
        onClick={() => hasDetail && setOpen((value) => !value)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left"
      >
        <Wrench className="size-3 shrink-0 text-subtle" />
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-foreground">
          {tool.name}
        </span>
        {tool.status === 'running' ? (
          <Loader2 className="size-3 animate-spin text-accent" />
        ) : tool.status === 'error' ? (
          <TriangleAlert className="size-3 text-accent" />
        ) : (
          <Check className="size-3 text-success" />
        )}
        {hasDetail ? (
          <ChevronDown
            className={`size-3 shrink-0 text-subtle transition-transform ${open ? 'rotate-180' : ''}`}
          />
        ) : null}
      </button>
      {open && hasDetail ? (
        <div className="space-y-2 border-t border-border px-2.5 py-2">
          {tool.input ? (
            <div>
              <p className="mb-1 text-[9.5px] font-semibold tracking-wider text-subtle uppercase">
                Arguments
              </p>
              <pre className="scrollbar-thin max-h-40 overflow-auto rounded-md bg-surface p-2 text-[10.5px] leading-relaxed text-muted">
                {tool.input}
              </pre>
            </div>
          ) : null}
          {tool.output ? (
            <div>
              <p className="mb-1 text-[9.5px] font-semibold tracking-wider text-subtle uppercase">
                Response
              </p>
              <pre className="scrollbar-thin max-h-48 overflow-auto rounded-md bg-surface p-2 text-[10.5px] leading-relaxed text-muted">
                {tool.output}
              </pre>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

const STAGE_SUBTITLE: Record<NonNullable<WorkflowNodeRun['stage']>, string> = {
  dispatch: 'Plans and dispatches the work',
  host: 'Leads the team',
  synthesis: 'Combines the results',
}

/** Names for the id-based handoff frames, with duplicates disambiguated. */
function buildDisplayNames(nodes: WorkflowNodeRun[]): Map<string, string> {
  const counts = new Map<string, number>()
  for (const node of nodes) {
    counts.set(node.agentName, (counts.get(node.agentName) ?? 0) + 1)
  }
  const seen = new Map<string, number>()
  const names = new Map<string, string>()
  for (const node of nodes) {
    if ((counts.get(node.agentName) ?? 1) <= 1) {
      names.set(node.id, node.agentName)
      continue
    }
    const index = (seen.get(node.agentName) ?? 0) + 1
    seen.set(node.agentName, index)
    names.set(node.id, `${node.agentName} #${index}`)
  }
  return names
}

function NodeCard({
  node,
  handoffs,
  mode,
  nameFor,
}: {
  node: WorkflowNodeRun
  handoffs: WorkflowRunFields['handoffs']
  mode: WorkflowMode
  nameFor: (id: string) => string
}) {
  const isHost = node.role === 'host'
  const [open, setOpen] = useState(node.status === 'running' || node.status === 'error')
  const [touched, setTouched] = useState(false)
  useEffect(() => {
    if (node.status === 'error' && !touched) setOpen(true)
  }, [node.status, touched])

  const inbound = handoffs.filter((handoff) => handoff.to.includes(node.id))
  // The node card is process only (status, tools, timing). An intermediate
  // agent's text is not surfaced here — only the host's final answer is, in chat.
  const hasDetail = node.tools.length > 0
  const stageText = node.stage ? STAGE_SUBTITLE[node.stage] : null

  return (
    <div className="relative pl-7">
      <span className="absolute top-3 left-[9px] flex size-4 items-center justify-center rounded-full bg-surface">
        <StatusIcon status={node.status} />
      </span>
      <span className="absolute top-9 bottom-[-14px] left-[16px] w-px bg-border last:hidden" />

      {inbound.map((handoff) => {
        const from = handoff.from.map(nameFor).join(', ')
        const swarm = mode === 'swarm'
        return (
          <div
            key={handoff.id}
            className={`mb-1.5 inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-medium ${
              swarm
                ? 'border-violet/25 bg-violet-soft text-violet'
                : 'border-border bg-raised text-muted'
            }`}
          >
            <ArrowRight className="size-3" />
            {swarm ? `Handoff from ${from}` : `From ${from}`}
            {handoff.message ? (
              <span className={swarm ? 'text-violet/80' : 'text-subtle'}>· {handoff.message}</span>
            ) : null}
          </div>
        )
      })}

      <div className="mb-3 overflow-hidden rounded-xl border border-border bg-surface/70">
        <button
          type="button"
          onClick={() => {
            setTouched(true)
            setOpen((value) => !value)
          }}
          className="flex w-full items-center gap-2.5 px-3 py-2 text-left"
        >
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5">
              <span className="truncate text-[12.5px] font-semibold text-foreground">
                {nameFor(node.id)}
              </span>
              {isHost ? (
                <Badge variant="accent">
                  <Crown className="size-2.5" /> Host
                </Badge>
              ) : null}
            </span>
            <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[10.5px] text-subtle">
              {stageText ? <span>{stageText}</span> : null}
              {node.model ? <span>{agentModelLabel(node.model)}</span> : null}
              {node.tools.length > 0 ? (
                <span>
                  {node.tools.length} tool call{node.tools.length === 1 ? '' : 's'}
                </span>
              ) : null}
              {node.endedAt && node.startedAt ? (
                <span>{formatDuration(node.startedAt, node.endedAt)}</span>
              ) : null}
            </span>
          </span>
          {hasDetail ? (
            <ChevronDown
              className={`size-3.5 shrink-0 text-subtle transition-transform ${open ? 'rotate-180' : ''}`}
            />
          ) : null}
        </button>

        {open && hasDetail ? (
          <div className="space-y-1.5 border-t border-border px-3 py-2.5">
            {node.tools.map((tool) => (
              <ToolRow key={tool.id} tool={tool} />
            ))}
          </div>
        ) : null}
      </div>
    </div>
  )
}

export function WorkflowRunTimeline({ run }: { run: WorkflowRunFields }) {
  const swarm = run.mode === 'swarm'

  // The synthesizer host only produces the final answer — never render it as a
  // step, or it reads as a second "Host". Detect it by stage (new frame) or by
  // its reserved id (older transcripts).
  const steps = useMemo(
    () =>
      run.nodes.filter(
        (node) => node.stage !== 'synthesis' && node.id !== 'host-synth',
      ),
    [run.nodes],
  )
  const names = useMemo(() => buildDisplayNames(steps), [steps])
  const nameFor = (id: string) => names.get(id) ?? id

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-subtle">
        <Badge variant={swarm ? 'accent' : 'info'}>{swarm ? 'Swarm' : 'Graph'}</Badge>
        {swarm && run.handoffs.length > 0 ? (
          <span>
            {run.handoffs.length} handoff{run.handoffs.length === 1 ? '' : 's'}
          </span>
        ) : null}
        {!swarm && steps.length > 0 ? (
          <span>
            {steps.length} step{steps.length === 1 ? '' : 's'}
          </span>
        ) : null}
        {run.endedAt ? <span>{formatDuration(run.startedAt, run.endedAt)}</span> : null}
        {run.usage?.totalTokens ? (
          <span>{run.usage.totalTokens.toLocaleString()} tokens</span>
        ) : null}
      </div>

      {run.nodes.length === 0 ? (
        <p className="flex items-center gap-2 text-[12px] text-subtle">
          <Loader2 className="size-3.5 animate-spin" /> Starting the workflow…
        </p>
      ) : (
        <div>
          {steps.map((node) => (
            <NodeCard
              key={node.id}
              node={node}
              handoffs={run.handoffs}
              mode={run.mode}
              nameFor={nameFor}
            />
          ))}
        </div>
      )}

      {run.status === 'error' && run.error ? (
        <p className="flex items-center gap-2 text-[12px] text-accent">
          <TriangleAlert className="size-3.5 shrink-0" /> {run.error}
        </p>
      ) : null}
    </div>
  )
}

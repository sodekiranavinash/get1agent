import { useMemo, useState } from 'react'
import { Bot, GripVertical, Plus, Search } from 'lucide-react'
import { agentModelLabel, resolveAgentModel, type Agent } from '../../lib/agents'

export const AGENT_DND_TYPE = 'application/x-workflow-agent'

export function AgentPalette({
  agents,
  loading,
  onAdd,
}: {
  agents: Agent[]
  loading?: boolean
  onAdd: (agent: Agent) => void
}) {
  const [query, setQuery] = useState('')
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return agents
    return agents.filter(
      (agent) =>
        agent.name.toLowerCase().includes(needle) ||
        agent.description?.toLowerCase().includes(needle),
    )
  }, [agents, query])

  return (
    <aside className="flex w-[268px] shrink-0 flex-col border-r border-border bg-surface/40">
      <div className="shrink-0 border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <h2 className="text-[13px] font-semibold text-foreground">Agents</h2>
          <span className="rounded-full bg-raised px-1.5 py-0.5 text-[10px] font-medium text-muted">
            {agents.length}
          </span>
        </div>
        <p className="mt-0.5 text-[11px] leading-relaxed text-subtle">
          Drag an agent onto the canvas, or click to add.
        </p>
        <div className="relative mt-2.5">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-subtle" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search agents"
            className="w-full rounded-md border border-border-strong bg-canvas py-1.5 pr-2.5 pl-8 text-[12.5px] text-foreground outline-none placeholder:text-subtle focus-visible:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/25"
          />
        </div>
      </div>

      <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto p-2">
        {loading ? (
          <div className="space-y-2 p-1">
            {[0, 1, 2, 3].map((index) => (
              <div key={index} className="skeleton h-[52px] rounded-xl" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <p className="px-2 py-6 text-center text-[12px] text-subtle">
            {agents.length === 0 ? 'No agents yet. Build one first.' : 'No agents match.'}
          </p>
        ) : (
          <ul className="space-y-1">
            {filtered.map((agent) => (
              <li key={agent.id}>
                <div
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData(AGENT_DND_TYPE, agent.id)
                    event.dataTransfer.effectAllowed = 'copy'
                  }}
                  className="group flex cursor-grab items-center gap-2.5 rounded-xl border border-transparent bg-surface/60 px-2.5 py-2 transition-colors hover:border-border hover:bg-raised/70 active:cursor-grabbing"
                >
                  <GripVertical className="size-3.5 shrink-0 text-subtle" />
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
                    <Bot className="size-4" strokeWidth={1.9} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[12.5px] font-medium text-foreground">
                      {agent.name}
                    </span>
                    <span className="block truncate text-[10.5px] text-subtle">
                      {agentModelLabel(resolveAgentModel(agent.model))}
                    </span>
                  </span>
                  <button
                    type="button"
                    title={`Add ${agent.name}`}
                    onClick={() => onAdd(agent)}
                    className="flex size-6 shrink-0 items-center justify-center rounded-md border border-border bg-surface text-subtle opacity-0 transition-opacity group-hover:opacity-100 hover:text-accent"
                  >
                    <Plus className="size-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}

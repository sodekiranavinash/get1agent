import { useMemo, type ReactNode } from 'react'
import {
  Bot,
  CalendarClock,
  Cpu,
  Crown,
  FileStack,
  FileText,
  MessageSquare,
  Plug,
  RotateCcw,
  Sparkles,
} from 'lucide-react'
import { ScheduleFields } from '../agent-builder/AgentNodeDialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select'
import {
  AGENT_MODELS,
  AGENT_OUTPUT_FORMATS,
  DEFAULT_AGENT_MODEL,
  DEFAULT_AGENT_SCHEDULE,
  agentModelLabel,
  resolveAgentModel,
  useAgentDetail,
  type Agent,
  type AgentOutputFormat,
  type AgentSchedule,
  type AgentServerSelection,
} from '../../lib/agents'
import type { WorkflowFlowNode } from './WorkflowNode'
import { useWorkflowBuilder } from './WorkflowBuilderContext'

const INHERIT = '__inherit__'

function Section({
  icon,
  title,
  hint,
  children,
}: {
  icon: ReactNode
  title: string
  hint?: string
  children: ReactNode
}) {
  return (
    <section className="border-b border-border px-4 py-3.5">
      <div className="flex items-center gap-2">
        <span className="flex size-6 items-center justify-center rounded-md bg-raised text-muted">
          {icon}
        </span>
        <h3 className="text-[12px] font-semibold tracking-tight text-foreground">{title}</h3>
      </div>
      {hint ? <p className="mt-1 text-[11px] leading-relaxed text-subtle">{hint}</p> : null}
      <div className="mt-2.5">{children}</div>
    </section>
  )
}

function Chip({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-2.5 py-1 text-[11px] font-medium transition-colors ${
        active
          ? 'border-accent/40 bg-accent-soft text-accent'
          : 'border-border bg-surface text-subtle hover:text-foreground'
      }`}
    >
      {label}
    </button>
  )
}

function EmptyHint({
  hasSchedule,
  onAddSchedule,
}: {
  hasSchedule: boolean
  onAddSchedule: () => void
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <span className="flex size-11 items-center justify-center rounded-2xl bg-raised text-subtle">
        <Bot className="size-5" strokeWidth={1.8} />
      </span>
      <h3 className="mt-3 text-[13px] font-semibold text-foreground">Nothing selected</h3>
      <p className="mt-1 max-w-[220px] text-[11.5px] leading-relaxed text-subtle">
        Click a node on the canvas to configure it here.
      </p>
      {!hasSchedule ? (
        <button
          type="button"
          onClick={onAddSchedule}
          className="mt-4 inline-flex items-center gap-1.5 rounded-lg border border-border bg-surface px-3 py-1.5 text-[11.5px] font-medium text-muted transition-colors hover:border-border-strong hover:text-foreground"
        >
          <CalendarClock className="size-3.5" /> Add schedule
        </button>
      ) : null}
    </div>
  )
}

function AgentInspector({
  node,
  agents,
  skills,
  knowledgeBases,
}: {
  node: WorkflowFlowNode
  agents: Agent[]
  skills: { id: string; name: string }[]
  knowledgeBases: { id: string; name: string }[]
}) {
  const { updateNodeData } = useWorkflowBuilder()
  const agent = agents.find((entry) => entry.id === node.data.agentId) ?? null
  const detail = useAgentDetail(node.data.agentId ?? null)
  const overrides = node.data.overrides ?? {}

  const inheritedModel = resolveAgentModel(agent?.model)
  const effectiveModel = overrides.model ?? inheritedModel
  const agentServers: AgentServerSelection[] = detail.data?.config?.servers ?? []
  const effectiveServers = overrides.servers ?? agentServers
  const effectiveSkillIds = overrides.skillIds ?? detail.data?.config?.skillIds ?? []
  const knowledgeBaseIds = detail.data?.config?.knowledgeBaseIds ?? []

  const setOverrides = (patch: Record<string, unknown>) => {
    const next = { ...overrides, ...patch }
    for (const key of Object.keys(next) as (keyof typeof next)[]) {
      if (next[key] === undefined || next[key] === null) delete next[key]
    }
    updateNodeData(node.id, { overrides: next })
  }

  const toggleServer = (server: AgentServerSelection) => {
    const has = effectiveServers.some((entry) => entry.id === server.id)
    const next = has
      ? effectiveServers.filter((entry) => entry.id !== server.id)
      : [...effectiveServers, server]
    setOverrides({ servers: next })
  }

  const toggleSkill = (skillId: string) => {
    const has = effectiveSkillIds.includes(skillId)
    const next = has
      ? effectiveSkillIds.filter((id) => id !== skillId)
      : [...effectiveSkillIds, skillId]
    setOverrides({ skillIds: next })
  }

  return (
    <>
      <div className="shrink-0 border-b border-border px-4 py-3.5">
        <div className="flex items-start gap-3">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent ring-1 ring-inset ring-accent/25">
            <Bot className="size-4.5" strokeWidth={1.9} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-1.5">
              <h2 className="truncate text-[13.5px] font-semibold text-foreground">
                {agent?.name ?? node.data.agentName ?? 'Agent'}
              </h2>
            </div>
            <p className="mt-0.5 line-clamp-2 text-[11px] leading-relaxed text-subtle">
              {agent?.description ?? 'This agent is no longer available.'}
            </p>
          </div>
        </div>
      </div>

      <Section icon={<Sparkles className="size-3.5" />} title="Model" hint="Override the model for this workflow only.">
        <Select
          value={overrides.model ?? INHERIT}
          onValueChange={(value) => setOverrides({ model: value === INHERIT ? null : value })}
        >
          <SelectTrigger size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={INHERIT}>Inherit · {agentModelLabel(inheritedModel)}</SelectItem>
            {AGENT_MODELS.map((model) => (
              <SelectItem key={model.id} value={model.id}>
                {model.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {overrides.model ? (
          <button
            type="button"
            onClick={() => setOverrides({ model: null })}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-subtle hover:text-accent"
          >
            <RotateCcw className="size-3" /> Reset to inherited
          </button>
        ) : null}
        <p className="mt-2 text-[10.5px] text-subtle">
          Effective model: <span className="text-muted">{agentModelLabel(effectiveModel)}</span>
        </p>
      </Section>

      <Section
        icon={<MessageSquare className="size-3.5" />}
        title="System prompt"
        hint="Replace this agent's prompt for this workflow only."
      >
        <textarea
          value={overrides.prompt ?? ''}
          onChange={(event) => setOverrides({ prompt: event.target.value })}
          placeholder={detail.data?.config?.prompt || 'Inherited from the agent'}
          rows={5}
          className="w-full resize-y rounded-md border border-border-strong bg-canvas px-2.5 py-2 text-[12px] leading-relaxed text-foreground outline-none placeholder:text-subtle focus-visible:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/25"
        />
        {overrides.prompt !== undefined ? (
          <button
            type="button"
            onClick={() => setOverrides({ prompt: null })}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-subtle hover:text-accent"
          >
            <RotateCcw className="size-3" /> Reset to inherited
          </button>
        ) : null}
      </Section>

      <Section
        icon={<FileStack className="size-3.5" />}
        title="Knowledge"
        hint="Knowledge bases are inherited from the agent."
      >
        {knowledgeBaseIds.length === 0 ? (
          <p className="text-[11.5px] text-subtle">No knowledge bases attached.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {knowledgeBaseIds.map((id) => (
              <span
                key={id}
                className="rounded-full border border-teal/25 bg-teal-soft px-2.5 py-1 text-[11px] font-medium text-teal"
              >
                {knowledgeBases.find((kb) => kb.id === id)?.name ?? `${id.slice(0, 8)}…`}
              </span>
            ))}
          </div>
        )}
      </Section>

      <Section
        icon={<Plug className="size-3.5" />}
        title="MCP servers"
        hint="Enable or disable this agent's tools for this workflow."
      >
        {agentServers.length === 0 ? (
          <p className="text-[11.5px] text-subtle">No MCP servers attached.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {agentServers.map((server) => (
              <Chip
                key={server.id}
                label={server.name}
                active={effectiveServers.some((entry) => entry.id === server.id)}
                onClick={() => toggleServer(server)}
              />
            ))}
          </div>
        )}
        {overrides.servers ? (
          <button
            type="button"
            onClick={() => setOverrides({ servers: null })}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-subtle hover:text-accent"
          >
            <RotateCcw className="size-3" /> Reset to inherited
          </button>
        ) : null}
      </Section>

      <Section
        icon={<Sparkles className="size-3.5" />}
        title="Skills"
        hint="Enable or disable skills for this workflow."
      >
        {skills.length === 0 ? (
          <p className="text-[11.5px] text-subtle">No skills available.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {skills.map((skill) => (
              <Chip
                key={skill.id}
                label={skill.name}
                active={effectiveSkillIds.includes(skill.id)}
                onClick={() => toggleSkill(skill.id)}
              />
            ))}
          </div>
        )}
        {overrides.skillIds ? (
          <button
            type="button"
            onClick={() => setOverrides({ skillIds: null })}
            className="mt-2 inline-flex items-center gap-1 text-[11px] text-subtle hover:text-accent"
          >
            <RotateCcw className="size-3" /> Reset to inherited
          </button>
        ) : null}
      </Section>

    </>
  )
}

function HostInspector({ node }: { node: WorkflowFlowNode }) {
  const { updateNodeData } = useWorkflowBuilder()
  return (
    <>
      <div className="shrink-0 border-b border-border px-4 py-3.5">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-xl bg-accent-soft text-accent ring-1 ring-inset ring-accent/25">
            <Crown className="size-4.5" strokeWidth={1.9} />
          </span>
          <div>
            <div className="flex items-center gap-1.5">
              <h2 className="text-[13.5px] font-semibold text-foreground">Query</h2>
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-accent-soft px-1.5 py-0.5 text-[9px] font-semibold text-accent">
                <Crown className="size-2.5" />
                Host
              </span>
            </div>
            <p className="text-[11px] text-subtle">
              The workflow host — sets the query, prompt and model.
            </p>
          </div>
        </div>
      </div>

      <Section
        icon={<Cpu className="size-3.5" />}
        title="Model"
        hint="The model that coordinates the workflow."
      >
        <Select
          value={node.data.model ?? DEFAULT_AGENT_MODEL}
          onValueChange={(value) => updateNodeData(node.id, { model: value })}
        >
          <SelectTrigger size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AGENT_MODELS.map((model) => (
              <SelectItem key={model.id} value={model.id}>
                {model.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Section>

      <Section
        icon={<MessageSquare className="size-3.5" />}
        title="System prompt"
        hint="The workflow's instructions: how the host should coordinate the agents."
      >
        <textarea
          value={node.data.prompt ?? ''}
          onChange={(event) => updateNodeData(node.id, { prompt: event.target.value })}
          placeholder="e.g. You are the research lead. Break the request down and delegate to your team, then write the final report."
          rows={6}
          className="w-full resize-y rounded-md border border-border-strong bg-canvas px-2.5 py-2 text-[12px] leading-relaxed text-foreground outline-none placeholder:text-subtle focus-visible:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/25"
        />
      </Section>

      <p className="rounded-lg border border-border bg-canvas/50 px-3 py-2 text-[11.5px] leading-relaxed text-muted">
        The question is asked when you run the workflow (Run tab) and is never saved
        with it.
      </p>
    </>
  )
}

function OutputInspector({ node }: { node: WorkflowFlowNode }) {
  const { updateNodeData } = useWorkflowBuilder()
  return (
    <>
      <div className="shrink-0 border-b border-border px-4 py-3.5">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-xl bg-success-soft text-success ring-1 ring-inset ring-success/25">
            <FileText className="size-4.5" strokeWidth={1.9} />
          </span>
          <div>
            <h2 className="text-[13.5px] font-semibold text-foreground">Output</h2>
            <p className="text-[11px] text-subtle">How the final answer is shaped.</p>
          </div>
        </div>
      </div>
      <Section icon={<FileText className="size-3.5" />} title="Format">
        <Select
          value={node.data.format ?? 'markdown'}
          onValueChange={(value) =>
            updateNodeData(node.id, { format: value as AgentOutputFormat })
          }
        >
          <SelectTrigger size="sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {AGENT_OUTPUT_FORMATS.map((format) => (
              <SelectItem key={format} value={format}>
                {format === 'markdown' ? 'Markdown' : format === 'json' ? 'JSON' : 'Plain text'}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Section>
      <Section
        icon={<FileText className="size-3.5" />}
        title="Instructions"
        hint="Appended to the final agent's prompt for this workflow."
      >
        <textarea
          value={node.data.instructions ?? ''}
          onChange={(event) => updateNodeData(node.id, { instructions: event.target.value })}
          placeholder="e.g. End with a one-line summary."
          rows={4}
          className="w-full resize-y rounded-md border border-border-strong bg-canvas px-2.5 py-2 text-[12px] leading-relaxed text-foreground outline-none placeholder:text-subtle focus-visible:border-accent/50 focus-visible:ring-2 focus-visible:ring-accent/25"
        />
      </Section>
    </>
  )
}

function ScheduleInspector({ node }: { node: WorkflowFlowNode }) {
  const { updateNodeData } = useWorkflowBuilder()
  const schedule: AgentSchedule = node.data.schedule ?? { ...DEFAULT_AGENT_SCHEDULE }
  return (
    <>
      <div className="shrink-0 border-b border-border px-4 py-3.5">
        <div className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-xl bg-rose-soft text-rose ring-1 ring-inset ring-rose/25">
            <CalendarClock className="size-4.5" strokeWidth={1.9} />
          </span>
          <div>
            <h2 className="text-[13.5px] font-semibold text-foreground">Schedule</h2>
            <p className="text-[11px] text-subtle">When this workflow should run on its own.</p>
          </div>
        </div>
      </div>
      <div className="px-4 py-3.5">
        <ScheduleFields
          schedule={schedule}
          onChange={(patch) =>
            updateNodeData(node.id, { schedule: { ...schedule, ...patch } })
          }
        />
      </div>
    </>
  )
}

export function WorkflowInspector({
  node,
  agents,
  skills,
  knowledgeBases,
  hasSchedule,
  onAddSchedule,
}: {
  node: WorkflowFlowNode | null
  agents: Agent[]
  skills: { id: string; name: string }[]
  knowledgeBases: { id: string; name: string }[]
  hasSchedule: boolean
  onAddSchedule: () => void
}) {
  const body = useMemo(() => {
    if (!node) return <EmptyHint hasSchedule={hasSchedule} onAddSchedule={onAddSchedule} />
    if (node.data.kind === 'input') return <HostInspector node={node} />
    if (node.data.kind === 'output') return <OutputInspector node={node} />
    if (node.data.kind === 'schedule') return <ScheduleInspector node={node} />
    return (
      <AgentInspector node={node} agents={agents} skills={skills} knowledgeBases={knowledgeBases} />
    )
  }, [node, agents, skills, knowledgeBases, hasSchedule, onAddSchedule])

  return <div className="scrollbar-thin min-h-0 flex-1 overflow-y-auto">{body}</div>
}

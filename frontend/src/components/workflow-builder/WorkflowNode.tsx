import {
  ArrowDown,
  ArrowRight,
  Bot,
  CalendarClock,
  Crown,
  FileText,
  MessageSquare,
  X,
  type LucideIcon,
} from 'lucide-react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import {
  agentModelLabel,
  describeSchedule,
  resolveAgentModel,
  type Agent,
} from '../../lib/agents'
import {
  WORKFLOW_HANDLE,
  type WorkflowNodeData,
  type WorkflowNodeKind,
} from '../../lib/workflows'
import { useWorkflowBuilder } from './WorkflowBuilderContext'

export type WorkflowFlowNode = Node<WorkflowNodeData>

type KindMeta = {
  icon: LucideIcon
  strip: string
  tile: string
}

const KIND_META: Record<WorkflowNodeKind, KindMeta> = {
  input: {
    icon: MessageSquare,
    strip: 'bg-info',
    tile: 'bg-info-soft text-info ring-info/25',
  },
  agent: {
    icon: Bot,
    strip: 'bg-accent',
    tile: 'bg-accent-soft text-accent ring-accent/30',
  },
  output: {
    icon: FileText,
    strip: 'bg-success',
    tile: 'bg-success-soft text-success ring-success/25',
  },
  schedule: {
    icon: CalendarClock,
    strip: 'bg-rose',
    tile: 'bg-rose-soft text-rose ring-rose/25',
  },
}

const FORMAT_LABELS: Record<string, string> = {
  markdown: 'Markdown',
  text: 'Plain text',
  json: 'JSON',
}

function agentSubtitle(agent: Agent | null, data: WorkflowNodeData): string {
  if (!agent) return 'Agent no longer available'
  const model = agentModelLabel(data.overrides?.model ?? resolveAgentModel(agent.model))
  const parts: string[] = [model]
  if (agent.knowledgeBaseCount > 0) parts.push(`${agent.knowledgeBaseCount} KB`)
  if (agent.skillCount > 0) parts.push(`${agent.skillCount} skill${agent.skillCount === 1 ? '' : 's'}`)
  if (agent.serverCount > 0) parts.push(`${agent.serverCount} MCP`)
  const overridden = Object.keys(data.overrides ?? {}).length > 0
  if (overridden) parts.push('customized')
  return parts.join(' · ')
}

export function WorkflowNodeView({ id, data, selected }: NodeProps<WorkflowFlowNode>) {
  const { agents, mode, order, openNode, removeNode } = useWorkflowBuilder()
  const meta = KIND_META[data.kind] ?? KIND_META.agent
  const Icon = meta.icon
  const orderNo = data.kind === 'agent' && mode === 'graph' ? order[id] : undefined

  const agent =
    data.kind === 'agent'
      ? agents.find((entry) => entry.id === data.agentId) ?? null
      : null

  const title =
    data.kind === 'input'
      ? 'Query'
      : data.kind === 'output'
        ? 'Output'
        : data.kind === 'schedule'
          ? 'Schedule'
          : agent?.name ?? data.agentName ?? 'Agent'

  const subtitle =
    data.kind === 'input'
      ? data.prompt?.trim() || 'Workflow host · asked at run time'
      : data.kind === 'output'
        ? FORMAT_LABELS[data.format ?? 'markdown'] ?? 'Markdown'
        : data.kind === 'schedule'
          ? data.schedule?.enabled && data.schedule.cron
            ? describeSchedule(data.schedule.cron)
            : 'Not scheduled'
          : agentSubtitle(agent, data)

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Edit ${title}`}
      onClick={() => openNode(id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          openNode(id)
        }
      }}
      className={`group relative flex h-[68px] w-[220px] cursor-pointer items-center overflow-hidden rounded-xl border bg-gradient-to-b from-raised/60 to-surface py-2.5 pr-2.5 pl-3.5 shadow-control transition-all duration-200 after:pointer-events-none after:absolute after:inset-x-0 after:top-0 after:h-px after:bg-white/[0.06] hover:-translate-y-0.5 hover:border-border-strong hover:shadow-panel focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none ${
        selected ? 'border-accent/60 ring-2 ring-accent/15' : 'border-border'
      }`}
    >
      <span className={`absolute inset-y-0 left-0 w-[3px] ${meta.strip}`} />

      {data.kind === 'schedule' ? (
        <Handle
          type="source"
          id={WORKFLOW_HANDLE.nodeOut}
          position={Position.Bottom}
          className="agent-handle"
        />
      ) : null}
      {data.kind === 'input' ? (
        <>
          <Handle
            type="target"
            id={WORKFLOW_HANDLE.hostScheduleIn}
            position={Position.Top}
            className="agent-handle"
          />
          <Handle
            type="source"
            id={WORKFLOW_HANDLE.hostAgentsOut}
            position={Position.Right}
            className="agent-handle"
          />
          <Handle
            type="source"
            id={WORKFLOW_HANDLE.hostOutputOut}
            position={Position.Bottom}
            className="agent-handle"
          />
        </>
      ) : null}
      {data.kind === 'output' ? (
        <Handle
          type="target"
          id={WORKFLOW_HANDLE.nodeIn}
          position={Position.Top}
          className="agent-handle"
        />
      ) : null}
      {data.kind === 'agent' ? (
        <>
          <Handle
            type="target"
            id={WORKFLOW_HANDLE.nodeIn}
            position={Position.Left}
            className="agent-handle"
          />
          <Handle
            type="source"
            id={WORKFLOW_HANDLE.nodeOut}
            position={Position.Right}
            className="agent-handle"
          />
        </>
      ) : null}

      <div className="relative flex min-w-0 flex-1 items-center gap-2.5 pl-1">
        <span
          className={`relative flex size-8 shrink-0 items-center justify-center rounded-lg shadow-control ring-1 ring-inset ${meta.tile}`}
        >
          <Icon className="size-4" strokeWidth={1.9} />
          {orderNo ? (
            <span className="absolute -top-1.5 -left-1.5 flex h-4 w-4 items-center justify-center rounded-full bg-accent text-[8.5px] font-bold text-white shadow-control ring-2 ring-surface">
              {orderNo}
            </span>
          ) : null}
        </span>

        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span className="truncate text-[12.5px] font-semibold tracking-tight text-foreground">
              {title}
            </span>
            {data.kind === 'input' ? (
              <span className="inline-flex shrink-0 items-center gap-1 rounded-full bg-accent-soft px-1.5 py-0.5 text-[9px] font-semibold text-accent">
                <Crown className="size-2.5" />
                Host
              </span>
            ) : null}
          </span>
          <span
            className={`mt-0.5 block truncate text-[10.5px] ${
              data.kind === 'input' && !data.prompt?.trim() ? 'text-subtle' : 'text-muted'
            }`}
          >
            {subtitle}
          </span>
        </span>

        {data.kind === 'schedule' ? (
          <ArrowDown className="size-3.5 shrink-0 text-subtle" />
        ) : data.kind !== 'agent' ? (
          <ArrowRight className="size-3.5 shrink-0 text-subtle" />
        ) : null}
      </div>

      {data.kind === 'agent' ? (
        <button
          type="button"
          title="Remove agent"
          aria-label="Remove agent"
          onClick={(event) => {
            event.stopPropagation()
            removeNode(id)
          }}
          className="absolute top-1.5 right-1.5 flex size-5 items-center justify-center rounded-md text-subtle/70 transition-colors hover:bg-raised hover:text-accent focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
        >
          <X className="size-3.5" />
        </button>
      ) : null}
    </div>
  )
}

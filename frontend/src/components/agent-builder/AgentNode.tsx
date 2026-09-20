import {
  Bot,
  CalendarClock,
  ChevronRight,
  FileStack,
  FileText,
  MessageSquare,
  Plug,
  Sparkles,
  type LucideIcon,
} from 'lucide-react'
import { Handle, Position, type Node, type NodeProps } from '@xyflow/react'
import {
  agentModelLabel,
  describeSchedule,
  type AgentNodeData,
  type AgentNodeKind,
  type AgentSchedule,
} from '../../lib/agents'
import { useAgentBuilder } from './AgentBuilderContext'

export type AgentFlowNode = Node<AgentNodeData>

/**
 * Cards carry a colour strip and a tinted icon tile so each kind is readable at
 * a glance. Hues are theme-aware tokens, so they hold up in both themes.
 */
type KindMeta = {
  icon: LucideIcon
  /** Icon tile shape — terminals are round, the core is a larger square. */
  tileShape: string
  /** Left colour strip. */
  strip: string
  /** Icon tile fill + icon colour + inset ring. */
  tile: string
}

export const AGENT_KIND_META: Record<AgentNodeKind, KindMeta> = {
  input: {
    icon: MessageSquare,
    tileShape: 'rounded-full',
    strip: 'bg-info',
    tile: 'bg-info-soft text-info ring-info/25',
  },
  agent: {
    icon: Bot,
    tileShape: 'rounded-xl',
    strip: 'bg-accent',
    tile: 'bg-accent-soft text-accent ring-accent/30',
  },
  knowledge: {
    icon: FileStack,
    tileShape: 'rounded-lg',
    strip: 'bg-teal',
    tile: 'bg-teal-soft text-teal ring-teal/25',
  },
  skills: {
    icon: Sparkles,
    tileShape: 'rounded-lg',
    strip: 'bg-violet',
    tile: 'bg-violet-soft text-violet ring-violet/25',
  },
  tools: {
    icon: Plug,
    tileShape: 'rounded-lg',
    strip: 'bg-warning',
    tile: 'bg-warning-soft text-warning ring-warning/25',
  },
  output: {
    icon: FileText,
    tileShape: 'rounded-full',
    strip: 'bg-success',
    tile: 'bg-success-soft text-success ring-success/25',
  },
  schedule: {
    icon: CalendarClock,
    tileShape: 'rounded-lg',
    strip: 'bg-rose',
    tile: 'bg-rose-soft text-rose ring-rose/25',
  },
}

const OUTPUT_FORMAT_LABELS: Record<string, string> = {
  markdown: 'Markdown',
  json: 'JSON',
  text: 'Plain text',
}

type Lookups = {
  knowledgeBases: { id: string; name: string }[]
  skills: { id: string; name: string }[]
}

function summarize(names: string[], empty: string): string {
  return names.length === 0 ? empty : names.join(', ')
}

function cardSubtitle(data: AgentNodeData, { knowledgeBases, skills }: Lookups): string {
  switch (data.kind) {
    case 'agent': {
      const reasoning = data.reasoning ?? 'medium'
      return `${agentModelLabel(data.model)} · ${reasoning[0].toUpperCase() + reasoning.slice(1)}`
    }
    case 'input': {
      const query = data.input?.trim()
      const files = (data.inputFileIds ?? []).length
      const questions = (data.defaultQuestions ?? []).length
      if (!query && files === 0 && questions === 0) return 'No query yet'
      const parts: string[] = []
      if (query) parts.push(query)
      if (files > 0) parts.push(`${files} file${files === 1 ? '' : 's'}`)
      if (questions > 0) parts.push(`${questions} starter question${questions === 1 ? '' : 's'}`)
      return parts.join(' · ')
    }
    case 'output': {
      const format = OUTPUT_FORMAT_LABELS[data.outputFormat ?? 'markdown'] ?? 'Markdown'
      return data.outputInstructions?.trim() ? `${format} · Custom instructions` : format
    }
    case 'knowledge': {
      const names = (data.knowledgeBaseIds ?? []).map(
        (id) => knowledgeBases.find((kb) => kb.id === id)?.name ?? id.slice(0, 8),
      )
      const label = summarize(names, 'No knowledge bases attached')
      return names.length > 0 && data.rerank ? `${label} · rerank` : label
    }
    case 'skills':
      return summarize(
        (data.skillIds ?? []).map(
          (id) => skills.find((skill) => skill.id === id)?.name ?? id.slice(0, 8),
        ),
        'No skills attached',
      )
    case 'tools':
      return summarize(
        (data.servers ?? []).map((server) =>
          server.tools === null ? server.name : `${server.name} (${server.tools.length})`,
        ),
        'No MCP servers attached',
      )
    case 'schedule': {
      const schedule: AgentSchedule = data.schedule ?? {
        enabled: false,
        cron: '',
        timezone: 'UTC',
      }
      if (!schedule.enabled) return 'Not scheduled'
      return schedule.cron ? describeSchedule(schedule.cron) : 'Not scheduled'
    }
    default:
      return ''
  }
}

function isEmptySubtitle(data: AgentNodeData): boolean {
  switch (data.kind) {
    case 'agent':
      return false
    case 'input':
      return (
        !data.input?.trim() &&
        (data.inputFileIds ?? []).length === 0 &&
        (data.defaultQuestions ?? []).length === 0
      )
    case 'output':
      return false
    case 'knowledge':
      return (data.knowledgeBaseIds ?? []).length === 0
    case 'skills':
      return (data.skillIds ?? []).length === 0
    case 'tools':
      return (data.servers ?? []).length === 0
    case 'schedule':
      return !(data.schedule?.enabled ?? false)
    default:
      return true
  }
}

export function AgentNodeView({ id, data, selected }: NodeProps<AgentFlowNode>) {
  const meta = AGENT_KIND_META[data.kind] ?? AGENT_KIND_META.agent
  const Icon = meta.icon
  const { openNodeEditor, knowledgeBases, skills } = useAgentBuilder()

  const subtitle = cardSubtitle(data, { knowledgeBases, skills })
  const muted = isEmptySubtitle(data)

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`Edit ${data.title}`}
      onClick={() => openNodeEditor(id)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault()
          openNodeEditor(id)
        }
      }}
      className={`group relative flex h-[88px] w-[272px] cursor-pointer items-center overflow-hidden rounded-2xl border bg-gradient-to-b from-raised/60 to-surface py-3 pr-3 pl-4 shadow-control transition-all duration-200 after:pointer-events-none after:absolute after:inset-x-0 after:top-0 after:h-px after:bg-white/[0.06] hover:-translate-y-0.5 hover:border-border-strong hover:shadow-panel focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none ${
        selected ? 'border-accent/60 ring-2 ring-accent/15' : 'border-border'
      }`}
    >
      <span
        className={`absolute inset-y-0 left-0 w-[3px] transition-all duration-200 group-hover:w-[4px] ${meta.strip}`}
      />

      {/* Handles. Agent: input from top, schedule from left, right to the
          knowledge/tools/skills column, bottom to the output. */}
      {data.kind === 'agent' ? (
        <>
          <Handle type="target" id="top" position={Position.Top} className="agent-handle" />
          <Handle type="target" id="left" position={Position.Left} className="agent-handle" />
          <Handle type="source" id="right" position={Position.Right} className="agent-handle" />
          <Handle type="source" id="bottom" position={Position.Bottom} className="agent-handle" />
        </>
      ) : null}
      {data.kind === 'input' ? (
        <Handle type="source" position={Position.Bottom} className="agent-handle" />
      ) : null}
      {data.kind === 'output' ? (
        <Handle type="target" position={Position.Top} className="agent-handle" />
      ) : null}
      {data.kind === 'schedule' ? (
        <Handle type="source" position={Position.Right} className="agent-handle" />
      ) : null}
      {data.kind === 'knowledge' || data.kind === 'tools' || data.kind === 'skills' ? (
        <Handle type="target" position={Position.Left} className="agent-handle" />
      ) : null}

      <div className="relative flex min-w-0 flex-1 items-center gap-3 pl-1">
        <span
          className={`flex size-10 shrink-0 items-center justify-center shadow-control ring-1 ring-inset ${meta.tileShape} ${meta.tile} transition-transform duration-200 group-hover:scale-105`}
        >
          <Icon className="size-5" strokeWidth={1.9} />
        </span>

        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13.5px] font-semibold tracking-tight text-foreground">
            {data.title}
          </span>
          <span
            className={`mt-0.5 block truncate text-[11.5px] ${muted ? 'text-subtle' : 'text-muted'}`}
          >
            {subtitle}
          </span>
        </span>

        <ChevronRight className="size-4 shrink-0 text-subtle transition-all duration-150 group-hover:translate-x-0.5 group-hover:text-foreground" />
      </div>
    </div>
  )
}

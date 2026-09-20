import { useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Braces,
  Check,
  ChevronRight,
  Loader2,
  Search,
  Square,
  Terminal,
  Wrench,
  XCircle,
} from 'lucide-react'
import type { AgentUsage } from '../../lib/agentRun'
import {
  formatDuration,
  formatUsage,
  type ChatPlan,
  type ChatPlanTodo,
  type ChatSubQuery,
  type ChatToolCall,
  type ChatToolStatus,
  type ChatTurnStatus,
} from '../../lib/chat'

const EASE = [0.22, 1, 0.36, 1] as const

type Tone = { text: string; soft: string }

const TONES: Record<'info' | 'success' | 'warning' | 'danger' | 'neutral', Tone> = {
  info: { text: 'text-info', soft: 'bg-info-soft' },
  success: { text: 'text-success', soft: 'bg-success-soft' },
  warning: { text: 'text-warning', soft: 'bg-warning-soft' },
  danger: { text: 'text-rose', soft: 'bg-rose-soft' },
  neutral: { text: 'text-muted', soft: 'bg-raised' },
}

const TURN_META: Record<
  ChatTurnStatus,
  { label: string; tone: Tone; spin?: boolean; icon: typeof Loader2 }
> = {
  streaming: { label: 'Working', tone: TONES.info, spin: true, icon: Loader2 },
  done: { label: 'Completed', tone: TONES.success, icon: Check },
  error: { label: 'Failed', tone: TONES.danger, icon: XCircle },
  stopped: { label: 'Stopped', tone: TONES.warning, icon: Square },
}

const TOOL_META: Record<
  ChatToolStatus,
  { label: string; tone: Tone; spin?: boolean; icon: typeof Loader2 }
> = {
  running: { label: 'Running', tone: TONES.info, spin: true, icon: Loader2 },
  success: { label: 'Done', tone: TONES.success, icon: Check },
  error: { label: 'Failed', tone: TONES.danger, icon: XCircle },
}

/** Smooth height dropdown used for every collapsible level. */
function Collapse({ open, children }: { open: boolean; children: ReactNode }) {
  return (
    <AnimatePresence initial={false}>
      {open ? (
        <motion.div
          key="content"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.2, ease: EASE }}
          className="overflow-hidden"
        >
          {children}
        </motion.div>
      ) : null}
    </AnimatePresence>
  )
}

function Chevron({ open }: { open: boolean }) {
  return (
    <ChevronRight
      className={`size-3.5 shrink-0 text-subtle transition-transform duration-200 ${
        open ? 'rotate-90' : ''
      }`}
    />
  )
}

function StatusPill({
  tone,
  icon: Icon,
  label,
  spin,
}: {
  tone: Tone
  icon: typeof Loader2
  label: string
  spin?: boolean
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-semibold ${tone.soft} ${tone.text}`}
    >
      <Icon className={`size-2.5 ${spin ? 'animate-spin' : ''}`} />
      {label}
    </span>
  )
}

function TodoMarker({ todo, index }: { todo: ChatPlanTodo; index: number }) {
  if (todo.status === 'active') {
    return (
      <span className="relative flex size-5 items-center justify-center rounded-full bg-info text-white">
        <span className="absolute inset-0 animate-ping rounded-full bg-info/30" />
        <Loader2 className="relative size-3 animate-spin" />
      </span>
    )
  }
  if (todo.status === 'done') {
    return (
      <span className="flex size-5 items-center justify-center rounded-full bg-success-soft text-success ring-1 ring-inset ring-success/30">
        <Check className="size-3" strokeWidth={3} />
      </span>
    )
  }
  if (todo.status === 'error') {
    return (
      <span className="flex size-5 items-center justify-center rounded-full bg-rose-soft text-rose ring-1 ring-inset ring-rose/30">
        <XCircle className="size-3" />
      </span>
    )
  }
  return (
    <span className="flex size-5 items-center justify-center rounded-full border border-border bg-surface text-[10px] font-semibold text-subtle tabular-nums">
      {index + 1}
    </span>
  )
}

function ToolField({
  label,
  icon: Icon,
  children,
}: {
  label: string
  icon: typeof Terminal
  children: ReactNode
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.1em] text-subtle uppercase">
        <Icon className="size-3" />
        {label}
      </div>
      {children}
    </div>
  )
}

function ToolCall({ tool }: { tool: ChatToolCall }) {
  const meta = TOOL_META[tool.status]
  // Collapse automatically when the call finishes; a manual toggle wins.
  const [override, setOverride] = useState<boolean | null>(null)
  const open = override ?? tool.status !== 'success'

  const hasInput = Boolean(tool.input)
  const hasOutput = Boolean(tool.output)

  return (
    <div className="overflow-hidden rounded-lg border border-border/70 bg-canvas/40 transition-colors hover:border-border-strong/60">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left transition-colors hover:bg-raised/40"
      >
        <span className="flex size-5 shrink-0 items-center justify-center rounded-md bg-raised text-muted">
          <Wrench className="size-3" />
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[11.5px] text-foreground">
          {tool.name}
        </span>
        <StatusPill tone={meta.tone} icon={meta.icon} label={meta.label} spin={meta.spin} />
        <Chevron open={open} />
      </button>

      <Collapse open={open}>
        <div className="space-y-2.5 border-t border-border/60 px-2.5 py-2.5">
          <ToolField label="Arguments" icon={Braces}>
            {hasInput ? (
              <pre className="scrollbar-thin max-h-80 overflow-auto rounded-md border border-border/60 bg-surface/70 p-2.5 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words text-muted">
                {tool.input}
              </pre>
            ) : (
              <p className="text-[11px] text-subtle">
                {tool.status === 'running' ? 'Building arguments…' : 'No arguments'}
              </p>
            )}
          </ToolField>

          <ToolField label="Response" icon={Terminal}>
            {hasOutput ? (
              <pre className="scrollbar-thin max-h-[420px] overflow-auto rounded-md border border-border/60 bg-surface/70 p-2.5 font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-words text-muted">
                {tool.output}
              </pre>
            ) : (
              <p className="text-[11px] text-subtle">
                {tool.status === 'running' ? 'Waiting for output…' : 'No output'}
              </p>
            )}
          </ToolField>
        </div>
      </Collapse>
    </div>
  )
}

/** Only steps that actually invoked a tool are shown in the run timeline. */
function involvesToolCall(todo: ChatPlanTodo): boolean {
  return todo.tools.length > 0
}

function TodoRow({ todo, index, last }: { todo: ChatPlanTodo; index: number; last: boolean }) {
  return (
    <li className="relative flex gap-3">
      <div className="relative flex w-5 shrink-0 justify-center">
        {!last ? (
          <span className="absolute top-5 bottom-0 w-px bg-border" aria-hidden="true" />
        ) : null}
        <TodoMarker todo={todo} index={index} />
      </div>

      <div className={`min-w-0 flex-1 ${last ? '' : 'pb-3.5'}`}>
        <p
          className={`pt-0.5 text-[12px] leading-snug font-medium ${
            todo.status === 'pending' ? 'text-muted' : 'text-foreground'
          }`}
        >
          {todo.title}
        </p>

        {todo.tools.length > 0 ? (
          <div className="mt-2 space-y-1.5">
            {todo.tools.map((tool) => (
              <ToolCall key={tool.id} tool={tool} />
            ))}
          </div>
        ) : null}
      </div>
    </li>
  )
}

/**
 * A sub-query is a labelled group of tool steps. It is deliberately styled
 * differently from the numbered todo rows so the two levels never blur.
 */
function SubQueryGroup({ subQuery }: { subQuery: ChatSubQuery }) {
  const visible = subQuery.todos.filter(involvesToolCall)
  const done = visible.filter((todo) => todo.status === 'done').length
  // Only the group currently being worked on is expanded; the rest stay closed.
  const active = visible.some((todo) => todo.status === 'active')
  const [override, setOverride] = useState<boolean | null>(null)
  const open = override ?? active
  const last = visible.length - 1

  return (
    <section className="overflow-hidden rounded-lg border border-border/70 bg-surface/60">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        className="flex w-full items-center gap-2.5 px-3 py-2 text-left transition-colors hover:bg-raised/50"
      >
        <span className="flex size-5 shrink-0 items-center justify-center rounded-md bg-info-soft text-info">
          <Search className="size-3" />
        </span>
        <span className="min-w-0 flex-1 truncate text-[12px] font-semibold text-foreground">
          {subQuery.query || 'Search'}
        </span>
        <span className="shrink-0 rounded-full bg-raised px-1.5 py-0.5 text-[10px] font-semibold text-muted tabular-nums">
          {done}/{visible.length}
        </span>
        <Chevron open={open} />
      </button>

      <Collapse open={open}>
        {visible.length > 0 ? (
          <ol className="border-t border-border/60 px-3 py-3">
            {visible.map((todo, index) => (
              <TodoRow key={todo.id} todo={todo} index={index} last={index === last} />
            ))}
          </ol>
        ) : null}
      </Collapse>
    </section>
  )
}

export function RunTimeline({
  plan,
  planning,
  status,
  startedAt,
  endedAt,
  usage,
  answer = '',
}: {
  plan: ChatPlan | null
  planning: boolean
  status: ChatTurnStatus
  startedAt: number
  endedAt?: number
  usage?: AgentUsage
  answer?: string
}) {
  const meta = TURN_META[status]
  const duration = formatDuration(startedAt, endedAt)
  const tokens = formatUsage(usage)
  // Open while the run streams; collapse as soon as the answer starts arriving
  // (or the run settles). A manual toggle wins.
  const [override, setOverride] = useState<boolean | null>(null)
  const open = override ?? (status === 'streaming' && !answer)

  if (!plan && !planning) return null

  const subQueries = (plan?.subQueries ?? [])
    .map((subQuery) => ({ ...subQuery, todos: subQuery.todos.filter(involvesToolCall) }))
    .filter((subQuery) => subQuery.todos.length > 0)
  const todos = subQueries.flatMap((subQuery) => subQuery.todos)
  const doneCount = todos.filter((todo) => todo.status === 'done').length
  const label = planning && !plan ? 'Planning' : meta.label

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-surface">
      <button
        type="button"
        onClick={() => setOverride(!open)}
        className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left transition-colors hover:bg-raised/40"
      >
        <meta.icon
          className={`size-3.5 shrink-0 ${meta.tone.text} ${meta.spin ? 'animate-spin' : ''}`}
        />
        <span className="text-[12.5px] font-semibold text-foreground">{label}</span>
        {todos.length > 0 ? (
          <span className="rounded-full bg-raised px-1.5 py-0.5 text-[10px] font-semibold text-muted tabular-nums">
            {doneCount}/{todos.length}
          </span>
        ) : null}
        <span className="ml-auto flex items-center gap-2 text-[10.5px] text-subtle">
          {duration ? <span className="tabular-nums">{duration}</span> : null}
          {tokens ? <span className="tabular-nums">{tokens}</span> : null}
        </span>
        <Chevron open={open} />
      </button>

      {subQueries.length > 0 ? (
        <Collapse open={open}>
          <div className="space-y-2 border-t border-border/70 bg-canvas/30 p-2.5">
            {subQueries.map((subQuery) => (
              <SubQueryGroup key={subQuery.id} subQuery={subQuery} />
            ))}
          </div>
        </Collapse>
      ) : null}
    </div>
  )
}

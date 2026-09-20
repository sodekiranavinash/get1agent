import { useEffect, useRef, useState, type ReactNode } from 'react'
import { Bot, Check, ChevronDown, Cpu, Send, Square } from 'lucide-react'
import { Button } from '../ui/Button'
import { Popover, PopoverContent, PopoverTrigger } from '../ui/popover'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import {
  AGENT_MODELS,
  agentModelLabel,
  type Agent,
} from '../../lib/agents'
import type { RunContext } from '../../lib/agentRun'

const MAX_TEXTAREA_HEIGHT = 200

/** One row of the context breakdown tooltip. */
function BreakdownRow({ label, value }: { label: string; value?: number }) {
  return (
    <div className="flex items-center justify-between gap-6">
      <span className="text-muted">{label}</span>
      <span className="tabular-nums text-foreground">
        {value != null ? value.toLocaleString() : '—'}
      </span>
    </div>
  )
}

/** Context-window fill ring (hover for the token breakdown), like an editor's meter. */
function ContextMeter({ context }: { context: RunContext }) {
  const pct = Math.max(0, Math.min(100, Math.round(context.ratio * 100)))
  const tone = context.full ? 'text-accent' : pct >= 80 ? 'text-warning' : 'text-muted'
  const radius = 7
  const circumference = 2 * Math.PI * radius
  const dash = circumference * Math.min(1, Math.max(0, context.ratio))
  const breakdown = context.breakdown

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={`ml-auto flex items-center gap-1.5 rounded-md px-1 py-0.5 text-[10.5px] tabular-nums hover:bg-raised ${tone}`}
        >
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <circle
              cx="9"
              cy="9"
              r={radius}
              fill="none"
              strokeWidth="2"
              stroke="currentColor"
              className="opacity-20"
            />
            <circle
              cx="9"
              cy="9"
              r={radius}
              fill="none"
              strokeWidth="2"
              strokeLinecap="round"
              stroke="currentColor"
              strokeDasharray={`${dash} ${circumference}`}
              transform="rotate(-90 9 9)"
            />
          </svg>
          <span>{pct}%</span>
        </button>
      </TooltipTrigger>
      <TooltipContent side="top" align="end" className="w-60 p-0">
        <div className="border-b border-border px-3 py-2">
          <p className="text-[11px] font-semibold text-foreground">Context window</p>
          <p className="text-[10.5px] text-subtle">
            {context.usedTokens.toLocaleString()} / {context.limitTokens.toLocaleString()} tokens
            {context.full ? ' · full' : ''}
          </p>
        </div>
        {breakdown ? (
          <div className="space-y-1 px-3 py-2 text-[11px]">
            <BreakdownRow label="System prompt" value={breakdown.system} />
            <BreakdownRow label="Tools" value={breakdown.tools} />
            <BreakdownRow label="Conversation" value={breakdown.messages} />
            <BreakdownRow
              label="Free"
              value={Math.max(0, context.limitTokens - context.usedTokens)}
            />
          </div>
        ) : (
          <div className="px-3 py-2 text-[11px] text-subtle">
            No messages yet — the breakdown appears after the first run.
          </div>
        )}
      </TooltipContent>
    </Tooltip>
  )
}

function PickerButton({
  icon,
  label,
  disabled,
}: {
  icon: ReactNode
  label: string
  disabled?: boolean
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      className="inline-flex h-7 max-w-[168px] items-center gap-1.5 rounded-full border border-border bg-raised/60 px-2.5 text-left transition-colors hover:border-border-strong hover:bg-raised disabled:cursor-not-allowed disabled:opacity-60"
    >
      <span className="shrink-0 text-subtle">{icon}</span>
      <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-foreground">
        {label}
      </span>
      <ChevronDown className="size-3 shrink-0 text-subtle" />
    </button>
  )
}

export function ChatComposer({
  agents,
  agentId,
  onAgentChange,
  model,
  onModelChange,
  value,
  onValueChange,
  onSend,
  onStop,
  running,
  canSend,
  configured,
  context = null,
}: {
  agents: Agent[]
  agentId: string
  onAgentChange: (id: string) => void
  model: string
  onModelChange: (model: string) => void
  value: string
  onValueChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  running: boolean
  canSend: boolean
  configured: boolean
  context?: RunContext | null
}) {
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const [agentOpen, setAgentOpen] = useState(false)
  const [modelOpen, setModelOpen] = useState(false)

  // Grow the textarea with its content up to a cap, then scroll internally.
  useEffect(() => {
    const element = textareaRef.current
    if (!element) return
    element.style.height = 'auto'
    element.style.height = `${Math.min(element.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`
  }, [value])

  const noAgents = agents.length === 0
  const selectedAgent = agents.find((agent) => agent.id === agentId) ?? null
  const modelLabel = agentModelLabel(model)
  const contextFull = Boolean(context?.full)

  return (
    <div className="shrink-0 border-t border-border/60 bg-canvas px-4 pt-3 pb-4 lg:px-6">
      <div className="mx-auto w-full max-w-3xl">
        <div className="rounded-2xl border border-border-strong/70 bg-canvas shadow-panel transition-colors focus-within:border-accent/50 focus-within:ring-2 focus-within:ring-accent/15">
          <div className="flex flex-wrap items-center gap-2 px-3 pt-3">
            <Popover open={agentOpen} onOpenChange={setAgentOpen}>
              <PopoverTrigger asChild>
                <span>
                  <PickerButton
                    icon={<Bot className="size-3" />}
                    label={selectedAgent?.name ?? (noAgents ? 'No agents yet' : 'Select an agent')}
                    disabled={running || noAgents}
                  />
                </span>
              </PopoverTrigger>
              <PopoverContent side="top" align="start" className="w-64 p-1.5">
                <p className="px-2 py-1.5 text-[10px] font-semibold tracking-[0.12em] text-subtle uppercase">
                  Choose an agent
                </p>
                <div className="scrollbar-thin max-h-72 overflow-y-auto">
                  {agents.map((agent) => {
                    const active = agent.id === agentId
                    return (
                      <button
                        key={agent.id}
                        type="button"
                        onClick={() => {
                          onAgentChange(agent.id)
                          setAgentOpen(false)
                        }}
                        className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors ${
                          active ? 'bg-accent-soft' : 'hover:bg-raised'
                        }`}
                      >
                        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-accent-soft text-accent">
                          <Bot className="size-3.5" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[12.5px] font-medium text-foreground">
                            {agent.name}
                          </span>
                          <span className="block truncate text-[10.5px] text-subtle">
                            {agentModelLabel(agent.model)}
                          </span>
                        </span>
                        {active ? <Check className="size-3.5 shrink-0 text-accent" /> : null}
                      </button>
                    )
                  })}
                </div>
              </PopoverContent>
            </Popover>

            <Popover open={modelOpen} onOpenChange={setModelOpen}>
              <PopoverTrigger asChild>
                <span>
                  <PickerButton
                    icon={<Cpu className="size-3" />}
                    label={modelLabel}
                    disabled={running}
                  />
                </span>
              </PopoverTrigger>
              <PopoverContent side="top" align="start" className="w-72 p-1.5">
                <p className="px-2 py-1.5 text-[10px] font-semibold tracking-[0.12em] text-subtle uppercase">
                  Choose a model
                </p>
                <div className="scrollbar-thin max-h-80 overflow-y-auto">
                  {AGENT_MODELS.map((entry) => {
                    const active = entry.id === model
                    return (
                      <button
                        key={entry.id}
                        type="button"
                        onClick={() => {
                          onModelChange(entry.id)
                          setModelOpen(false)
                        }}
                        className={`flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors ${
                          active ? 'bg-accent-soft' : 'hover:bg-raised'
                        }`}
                      >
                        <span className="flex size-6 shrink-0 items-center justify-center rounded-md bg-info-soft text-info">
                          <Cpu className="size-3.5" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-[12.5px] font-medium text-foreground">
                            {entry.label}
                          </span>
                          <span className="block truncate text-[10.5px] text-subtle">
                            {entry.blurb}
                          </span>
                        </span>
                        {active ? <Check className="size-3.5 shrink-0 text-accent" /> : null}
                      </button>
                    )
                  })}
                </div>
              </PopoverContent>
            </Popover>

            {context ? (
              <ContextMeter context={context} />
            ) : (
              <span className="ml-auto hidden text-[10.5px] text-subtle sm:inline">
                {running ? 'Streaming…' : 'Enter to send · Shift + Enter for a new line'}
              </span>
            )}
          </div>

          {contextFull ? (
            <div className="mx-2.5 mt-2 rounded-lg border border-warning/25 bg-warning-soft px-3 py-2 text-[11.5px] text-warning">
              This conversation has reached the model's context limit. Start a new
              conversation to continue.
            </div>
          ) : null}

          <div className="flex items-end gap-2 p-2.5 pt-2">
            <textarea
              ref={textareaRef}
              rows={1}
              value={value}
              onChange={(event) => onValueChange(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  if (canSend && !running && !contextFull) onSend()
                }
              }}
              placeholder={
                contextFull
                  ? 'Context limit reached — start a new conversation…'
                  : noAgents
                    ? 'Create an agent in the builder first…'
                    : 'Ask anything…'
              }
              disabled={noAgents || contextFull}
              className="scrollbar-thin max-h-[200px] flex-1 resize-none bg-transparent px-1.5 py-1.5 text-[13px] leading-relaxed text-foreground outline-none placeholder:text-subtle disabled:opacity-60"
            />

            {running ? (
              <Button
                variant="outline"
                size="md"
                icon={<Square className="size-3.5" />}
                onClick={onStop}
              >
                Stop
              </Button>
            ) : (
              <Button
                variant="primary"
                size="md"
                icon={<Send className="size-3.5" />}
                onClick={onSend}
                disabled={!canSend || !configured || contextFull}
                title={
                  contextFull
                    ? 'Context limit reached — start a new conversation'
                    : configured
                      ? undefined
                      : 'Set VITE_AGENT_RUN_URL to chat'
                }
              >
                Send
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

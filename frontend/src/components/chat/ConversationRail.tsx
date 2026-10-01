import { useCallback, useEffect, useMemo, useState, type RefObject } from 'react'
import { Bot, Network, Wrench } from 'lucide-react'
import { Tooltip, TooltipContent, TooltipTrigger } from '../ui/tooltip'
import type { ChatTurn, ChatTurnStatus } from '../../lib/chat'

/**
 * A scrollbar-side navigator for a conversation.
 *
 * One horizontal dash per message, evenly spaced and centred vertically in the
 * transcript viewport. Hovering a dash reveals the agent(s) and the tools that
 * ran; clicking scrolls that message into view; the dash for the message at the
 * viewport centre is highlighted.
 */

type RailEntry = {
  id: string
  question: string
  agents: string[]
  tools: string[]
  status: ChatTurnStatus
  isWorkflow: boolean
}

type RailMarker = {
  id: string
  /** The message's content offset — used to jump and to track the active tick. */
  scrollTop: number
}

const STATUS: Record<ChatTurnStatus, { dot: string; label: string }> = {
  streaming: { dot: 'bg-info', label: 'Working' },
  done: { dot: 'bg-success', label: 'Completed' },
  error: { dot: 'bg-rose', label: 'Failed' },
  stopped: { dot: 'bg-warning', label: 'Stopped' },
  awaiting_input: { dot: 'bg-accent', label: 'Waiting for you' },
}

/** Flatten a turn into the agent + tool labels shown on hover. */
function entryFor(turn: ChatTurn): RailEntry {
  const agents = new Set<string>()
  const tools = new Set<string>()
  const isWorkflow = turn.targetType === 'workflow' && Boolean(turn.workflow)

  if (turn.targetType === 'workflow' && turn.workflow) {
    for (const node of turn.workflow.nodes) {
      // Skip nodes that never produced anything (planned but unused).
      if (node.status === 'pending' && !node.output && node.tools.length === 0) continue
      agents.add(node.agentName || node.name)
      for (const tool of node.tools) tools.add(tool.name)
    }
  } else {
    agents.add(turn.agentName)
    for (const tool of turn.tools) tools.add(tool.name)
  }

  if (agents.size === 0) agents.add(turn.agentName)
  return {
    id: turn.id,
    question: turn.question,
    agents: [...agents].filter(Boolean),
    tools: [...tools].filter(Boolean),
    status: turn.status,
    isWorkflow,
  }
}

function Tag({
  icon: Icon,
  tone,
  children,
}: {
  icon: typeof Bot
  tone: string
  children: string
}) {
  return (
    <span
      className={`inline-flex max-w-[11rem] items-center gap-1 rounded-full border border-border/70 px-2 py-0.5 text-[10.5px] font-medium ${tone}`}
    >
      <Icon className="size-2.5 shrink-0" strokeWidth={2} />
      <span className="truncate">{children}</span>
    </span>
  )
}

export function ConversationRail({
  turns,
  containerRef,
}: {
  turns: ChatTurn[]
  containerRef: RefObject<HTMLDivElement | null>
}) {
  const entries = useMemo(() => turns.map(entryFor), [turns])
  const [markers, setMarkers] = useState<RailMarker[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)

  // Re-measure when the set of messages or their settled state changes — not on
  // every streamed token (which would thrash during a run).
  const signature = useMemo(
    () => turns.map((turn) => `${turn.id}:${turn.status}`).join('|'),
    [turns],
  )

  const measure = useCallback(() => {
    const container = containerRef.current
    if (!container) return
    const containerRect = container.getBoundingClientRect()

    const next: RailMarker[] = []
    for (const element of container.querySelectorAll<HTMLElement>('[data-turn-id]')) {
      const id = element.dataset.turnId
      if (!id) continue
      const rect = element.getBoundingClientRect()
      next.push({
        id,
        scrollTop: rect.top - containerRect.top + container.scrollTop,
      })
    }
    setMarkers(next)
  }, [containerRef])

  useEffect(() => {
    measure()
  }, [measure, signature])

  // Track measurement across viewport/content resize.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const observer = new ResizeObserver(() => measure())
    observer.observe(container)
    if (container.firstElementChild) observer.observe(container.firstElementChild)
    return () => observer.disconnect()
  }, [containerRef, measure, signature])

  // Highlight the message at the viewport's centre.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return
    const onScroll = () => {
      const center = container.scrollTop + container.clientHeight / 2
      let current: string | null = markers[0]?.id ?? null
      for (const marker of markers) {
        if (marker.scrollTop <= center) current = marker.id
        else break
      }
      setActiveId(current)
    }
    onScroll()
    container.addEventListener('scroll', onScroll, { passive: true })
    return () => container.removeEventListener('scroll', onScroll)
  }, [containerRef, markers])

  const jumpTo = (marker: RailMarker) => {
    const container = containerRef.current
    if (!container) return
    container.scrollTo({ top: Math.max(0, marker.scrollTop - 16), behavior: 'smooth' })
  }

  if (markers.length === 0) return null

  return (
    <div
      // Sits just left of the native scrollbar; forwards wheel so the rail
      // column never swallows scrolling.
      className="absolute inset-y-0 right-3 z-20 flex w-7 flex-col items-end justify-center gap-1 overflow-hidden py-2"
      onWheel={(event) => {
        const container = containerRef.current
        if (container) container.scrollTop += event.deltaY
      }}
    >
      {markers.map((marker) => {
        const entry = entries.find((item) => item.id === marker.id)
        if (!entry) return null
        const tone = STATUS[entry.status]
        const active = marker.id === activeId
        const hasTools = entry.tools.length > 0

        return (
          <Tooltip key={marker.id} delayDuration={80}>
            <TooltipTrigger asChild>
              <button
                type="button"
                aria-label={`Jump to: ${entry.question.slice(0, 60)}`}
                onClick={() => jumpTo(marker)}
                // A short horizontal dash; the column is centred as a group.
                className="group relative flex h-3 items-center justify-end"
              >
                <span
                  className={`block h-[3px] rounded-full transition-all duration-150 ${tone.dot} ${
                    active
                      ? 'w-7 opacity-100'
                      : 'w-4 opacity-40 group-hover:w-7 group-hover:opacity-100'
                  }`}
                />
              </button>
            </TooltipTrigger>
            <TooltipContent side="left" align="center" className="w-60 space-y-2 p-2.5">
              <p className="line-clamp-3 text-[11.5px] leading-snug font-medium text-foreground">
                {entry.question || 'Message'}
              </p>
              <div className="flex flex-wrap gap-1">
                {entry.agents.map((agent) => (
                  <Tag
                    key={agent}
                    icon={entry.isWorkflow ? Network : Bot}
                    tone="border-accent/25 bg-accent-soft text-accent"
                  >
                    {agent}
                  </Tag>
                ))}
              </div>
              {hasTools ? (
                <div className="flex flex-wrap gap-1">
                  {entry.tools.map((tool) => (
                    <Tag
                      key={tool}
                      icon={Wrench}
                      tone="border-border/70 bg-raised text-muted"
                    >
                      {tool}
                    </Tag>
                  ))}
                </div>
              ) : null}
              <p className="text-[10px] tracking-wide text-subtle uppercase">{tone.label}</p>
            </TooltipContent>
          </Tooltip>
        )
      })}
    </div>
  )
}

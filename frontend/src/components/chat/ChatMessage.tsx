import { Bot } from 'lucide-react'
import { agentModelLabel } from '../../lib/agents'
import type { ChatTurn } from '../../lib/chat'
import { ChatAnswer } from './ChatAnswer'
import { RunTimeline } from './RunTimeline'
import { SourceCarousel } from './SourceCarousel'

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

export function ChatMessage({ turn }: { turn: ChatTurn }) {
  const showTimeline = turn.planning || turn.plan !== null || turn.tools.length > 0

  return (
    <div className="space-y-3">
      {/* User question */}
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-sm bg-accent px-4 py-2.5 text-[13px] leading-relaxed text-white shadow-control">
          <p className="whitespace-pre-wrap">{turn.question}</p>
        </div>
      </div>

      {/* Assistant run + answer */}
      <div className="flex gap-3">
        <span className="mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg bg-accent-soft text-accent ring-1 ring-inset ring-accent/20">
          <Bot className="size-4" strokeWidth={1.9} />
        </span>

        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-subtle">
            <span className="text-[12px] font-semibold text-foreground">{turn.agentName}</span>
            <span className="rounded-full bg-raised px-2 py-0.5 text-[10.5px] font-medium text-muted">
              {agentModelLabel(turn.model)}
            </span>
            <span className="tabular-nums">{formatTime(turn.at)}</span>
          </div>

          {showTimeline ? (
            <RunTimeline
              plan={turn.plan}
              planning={turn.planning}
              status={turn.status}
              startedAt={turn.startedAt}
              endedAt={turn.endedAt}
              usage={turn.usage}
              answer={turn.answer}
            />
          ) : null}

          <ChatAnswer
            content={turn.answer}
            format={turn.outputFormat}
            status={turn.status}
            turnId={turn.id}
          />

          {turn.status !== 'streaming' && turn.sources.length > 0 ? (
            <SourceCarousel sources={turn.sources} turnId={turn.id} />
          ) : null}

          {turn.status === 'error' && turn.error ? (
            <p className="rounded-lg border border-accent/25 bg-accent-soft px-3 py-2 text-[12px] text-accent">
              {turn.error}
            </p>
          ) : null}
        </div>
      </div>
    </div>
  )
}

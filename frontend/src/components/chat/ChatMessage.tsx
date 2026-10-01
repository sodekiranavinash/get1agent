import { Bot, ExternalLink, Network } from 'lucide-react'
import { agentModelLabel } from '../../lib/agents'
import type { ChatTurn } from '../../lib/chat'
import { traceHref } from '../../lib/trace'
import { WorkflowRunTimeline } from '../workflow-builder/WorkflowRunTimeline'
import { ChatAnswer } from './ChatAnswer'
import { HumanPrompt } from './HumanPrompt'
import { RunFeedback } from './RunFeedback'
import { RunTimeline } from './RunTimeline'
import { SourceCarousel } from './SourceCarousel'

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

export function ChatMessage({
  turn,
  onAnswer,
}: {
  turn: ChatTurn
  onAnswer?: (answer: string) => void
}) {
  const isWorkflow = turn.targetType === 'workflow' && Boolean(turn.workflow)
  const showTimeline = turn.planning || turn.plan !== null || turn.tools.length > 0
  // Human-in-the-loop: the agent (or the workflow host) paused for an answer.
  const question = turn.humanQuestion ?? turn.workflow?.humanQuestion ?? null
  // A turn is only "settled" once it finished; a paused question is still in
  // flight, so it must not show citations, feedback or a trace link.
  const settled =
    turn.status === 'done' || turn.status === 'error' || turn.status === 'stopped'

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
          {isWorkflow ? (
            <Network className="size-4" strokeWidth={1.9} />
          ) : (
            <Bot className="size-4" strokeWidth={1.9} />
          )}
        </span>

        <div className="min-w-0 flex-1 space-y-3">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-subtle">
            <span className="text-[12px] font-semibold text-foreground">{turn.agentName}</span>
            <span className="rounded-full bg-raised px-2 py-0.5 text-[10.5px] font-medium text-muted">
              {isWorkflow ? 'Workflow' : agentModelLabel(turn.model)}
            </span>
            <span className="tabular-nums">{formatTime(turn.at)}</span>
          </div>

          {isWorkflow && turn.workflow ? (
            <WorkflowRunTimeline run={turn.workflow} />
          ) : showTimeline ? (
            <RunTimeline
              plan={turn.plan}
              planning={turn.planning}
              skills={turn.skills}
              attachments={turn.attachments}
              status={turn.status}
              startedAt={turn.startedAt}
              endedAt={turn.endedAt}
              usage={turn.usage}
              answer={turn.answer}
              onAnswer={(_questionId, answer) => onAnswer?.(answer)}
            />
          ) : null}

          {/* A workflow's host question has no timeline step, so it stays inline. */}
          {isWorkflow && question ? (
            <HumanPrompt
              question={question}
              disabled={turn.status !== 'awaiting_input'}
              onSubmit={(answer) => onAnswer?.(answer)}
            />
          ) : null}

          <ChatAnswer
            content={turn.answer}
            format={turn.outputFormat}
            status={turn.status}
            turnId={turn.id}
          />

          {settled && turn.sources.length > 0 ? (
            <SourceCarousel sources={turn.sources} turnId={turn.id} />
          ) : null}

          {turn.status === 'error' && turn.error ? (
            <p className="rounded-lg border border-accent/25 bg-accent-soft px-3 py-2 text-[12px] text-accent">
              {turn.error}
            </p>
          ) : null}

          {settled ? (
            <div className="flex items-center gap-3">
              <RunFeedback
                runId={turn.runId ?? turn.id}
                feedback={turn.feedback}
                traceId={turn.traceId}
                agentId={turn.agentId}
              />
              {traceHref(turn.traceUrl) ? (
                <a
                  href={traceHref(turn.traceUrl) ?? undefined}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-subtle transition-colors hover:text-accent"
                >
                  View trace
                  <ExternalLink className="size-3" strokeWidth={1.9} />
                </a>
              ) : null}
            </div>
          ) : null}
        </div>
      </div>
    </div>
  )
}

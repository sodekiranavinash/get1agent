import { useEffect, useState } from 'react'
import type { LucideIcon } from 'lucide-react'
import {
  Bot,
  Check,
  Database,
  FileText,
  GitMerge,
  Globe,
  ListChecks,
  Loader2,
  Sparkles,
  User,
} from 'lucide-react'
import { Segmented } from '../ui/Segmented'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useInView } from '../../hooks/useInView'

type Mode = 'Agent' | 'Workflow'

const MODES = ['Agent', 'Workflow'] as const
const QUESTION =
  'How did Q3 revenue and retention trend — and what drove the change?'

/* ------------------------------------------------------------------ Agent run */

type ToolStep = { tool: string; detail: string; icon: LucideIcon }
type SubQuery = { title: string; steps: ToolStep[] }

const SUBQUERIES: SubQuery[] = [
  {
    title: 'Q3 revenue and retention',
    steps: [
      { tool: 'search-user-knowledge-bases', detail: '6 chunks · 3 KBs', icon: Database },
      { tool: 'web-search', detail: '5 results', icon: Globe },
    ],
  },
  {
    title: 'What drove the change',
    steps: [
      { tool: 'search-user-knowledge-bases', detail: '4 chunks · 2 KBs', icon: Database },
    ],
  },
]

// 1 plan, then a header + one tick per tool step, then answer + references.
const AGENT_PLAN_AT = 1
let agentCursor = AGENT_PLAN_AT + 1
const AGENT_HEADER_AT: number[] = []
const AGENT_STEP_AT: number[][] = []
for (const sq of SUBQUERIES) {
  AGENT_HEADER_AT.push(agentCursor++)
  const steps: number[] = []
  for (const _step of sq.steps) steps.push(agentCursor++)
  AGENT_STEP_AT.push(steps)
}
const AGENT_ANSWER_AT = agentCursor++
const AGENT_REFS_AT = agentCursor
const AGENT_TOTAL = AGENT_REFS_AT
const AGENT_TOOLS = SUBQUERIES.reduce((n, sq) => n + sq.steps.length, 0)

/* --------------------------------------------------------------- Workflow run */

const WF_QUESTION = 'How did Q3 revenue trend, and how is the market reacting?'

type ParticipantId = 'host' | 'docs' | 'market'

const PARTICIPANTS: { id: ParticipantId; label: string; icon: LucideIcon }[] = [
  { id: 'host', label: 'Host', icon: Bot },
  { id: 'docs', label: 'Docs', icon: Database },
  { id: 'market', label: 'Market', icon: Globe },
]

const PARTICIPANT_PHASES: Record<ParticipantId, number[]> = {
  host: [1, 6],
  docs: [2, 3],
  market: [4, 5],
}

// 1 dispatch · 2 docs query · 3 docs tool · 4 market query · 5 market tool ·
// 6 synthesize (answer) · 7 references.
const WF_DISPATCH_AT = 1
const WF_DOCS_AT = 2
const WF_DOCS_TOOL_AT = 3
const WF_MARKET_AT = 4
const WF_MARKET_TOOL_AT = 5
const WF_ANSWER_AT = 6
const WF_REFS_AT = 7
const WF_TOTAL = WF_REFS_AT

const REFERENCES = [
  { icon: FileText, title: 'q3-release-notes.pdf', meta: 'page 4' },
  { icon: Globe, title: 'marketwatch.com', meta: 'Q3 earnings' },
]

function Citation({ n }: { n: number }) {
  return (
    <span className="mx-0.5 inline-flex size-4 items-center justify-center rounded-full bg-accent-soft align-middle text-[9px] font-semibold text-accent">
      {n}
    </span>
  )
}

/**
 * Self-playing run widget for the hero with a switch between two productions:
 *
 * - **Agent** — the planner's question → sub-queries → each todo's tool call
 *   (indented), then the grounded answer with numbered citations and references.
 * - **Workflow** — a multi-agent run: the host dispatches, two teammates each
 *   answer their own sub-query with a tool call, and the host synthesizes.
 *
 * Every item is always laid out and only faded in, and the two productions
 * share one grid cell, so the card holds the height of its finished state from
 * the first frame — nothing on the page reflows. Loops while in view; shows the
 * finished state under reduced motion.
 */
export function AgentRunPreview() {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 })
  const [mode, setMode] = useState<Mode>('Agent')
  const total = mode === 'Agent' ? AGENT_TOTAL : WF_TOTAL
  const [phase, setPhase] = useState(() => (reduced ? total : 0))

  useEffect(() => {
    if (reduced || !inView) return
    setPhase(0)
    let cancelled = false
    let handle = 0
    let current = 0

    const run = () => {
      if (cancelled) return
      current += 1
      if (current > total) {
        handle = window.setTimeout(() => {
          if (cancelled) return
          current = 0
          setPhase(0)
          handle = window.setTimeout(run, 600)
        }, 2600)
        return
      }
      setPhase(current)
      handle = window.setTimeout(run, 820)
    }

    handle = window.setTimeout(run, 600)
    return () => {
      cancelled = true
      window.clearTimeout(handle)
    }
  }, [mode, total, inView, reduced])

  const done = phase >= total
  const answerAt = mode === 'Agent' ? AGENT_ANSWER_AT : WF_ANSWER_AT
  const refsAt = mode === 'Agent' ? AGENT_REFS_AT : WF_REFS_AT
  const answerStarted = phase >= answerAt

  // Reveal helper: an item is always laid out, and only fades/slides in.
  const reveal = (at: number) =>
    `transition-all duration-300 ${
      phase >= at ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
    }`

  const participantActive = (id: ParticipantId) =>
    PARTICIPANT_PHASES[id].includes(phase) && !done
  const participantDone = (id: ParticipantId) =>
    done || Math.max(...PARTICIPANT_PHASES[id]) < phase

  const renderAgentBody = () => (
    <>
      <div
        className={`flex items-center gap-2 rounded-lg border border-border/70 bg-surface/60 px-2.5 py-1 ${reveal(AGENT_PLAN_AT)}`}
      >
        <span
          className={`flex size-5 shrink-0 items-center justify-center rounded-md border bg-canvas ${
            done ? 'border-success/40 text-success' : 'border-accent/40 text-accent'
          }`}
        >
          {done ? <Check className="size-3" /> : <Sparkles className="size-3" />}
        </span>
        <span className="min-w-0 flex-1 text-[11.5px] font-semibold text-foreground">
          Planning
        </span>
        <span className="shrink-0 font-mono text-[10px] text-subtle">
          {SUBQUERIES.length} sub-queries · {AGENT_TOOLS} tool calls
        </span>
      </div>

      {SUBQUERIES.map((sq, sqIndex) => (
        <div
          key={sq.title}
          className={`border-l-2 pl-2.5 transition-colors ${
            phase >= AGENT_HEADER_AT[sqIndex] ? 'border-accent/30' : 'border-transparent'
          }`}
        >
          <div className={`flex items-center gap-2 py-0.5 ${reveal(AGENT_HEADER_AT[sqIndex])}`}>
            <ListChecks className="size-3.5 shrink-0 text-accent" />
            <span className="truncate text-[11.5px] font-medium text-foreground">
              {sq.title}
            </span>
          </div>
          <div className="mt-0.5 space-y-1">
            {sq.steps.map((step, stepIndex) => {
              const at = AGENT_STEP_AT[sqIndex][stepIndex]
              const active = phase === at && !done
              const complete = phase > at || done
              const Icon = step.icon
              return (
                <div
                  key={step.tool}
                  className={`flex items-center gap-2 rounded-lg border px-2 py-1 transition-colors ${reveal(at)} ${
                    active
                      ? 'border-accent/40 bg-accent-soft'
                      : 'border-transparent bg-raised/40'
                  }`}
                >
                  <span
                    className={`flex size-5 shrink-0 items-center justify-center rounded-md border bg-canvas ${
                      active
                        ? 'border-accent/40 text-accent'
                        : complete
                          ? 'border-success/40 text-success'
                          : 'border-border text-muted'
                    }`}
                  >
                    {active ? (
                      <Loader2 className="size-3 animate-spin" />
                    ) : complete ? (
                      <Check className="size-3" />
                    ) : (
                      <Icon className="size-3" />
                    )}
                  </span>
                  <span
                    className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-foreground"
                    title={step.tool}
                  >
                    {step.tool}
                  </span>
                  <span className="shrink-0 font-mono text-[9.5px] text-subtle">
                    {step.detail}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </>
  )

  const renderWorkflowBody = () => (
    <>
      <div className={`flex flex-wrap items-center gap-1.5 ${reveal(WF_DISPATCH_AT)}`}>
        {PARTICIPANTS.map(({ id, label, icon: Icon }) => {
          const active = participantActive(id)
          const finished = participantDone(id)
          return (
            <span
              key={id}
              className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10px] font-medium transition-colors ${
                active
                  ? 'border-accent/50 bg-accent-soft text-accent'
                  : finished
                    ? 'border-success/40 bg-success-soft text-success'
                    : 'border-border bg-canvas/60 text-subtle'
              }`}
            >
              <Icon className="size-2.5" />
              {label}
              {active ? <Loader2 className="size-2.5 animate-spin" /> : null}
            </span>
          )
        })}
      </div>

      <div
        className={`flex items-start gap-2 rounded-lg border border-border/70 bg-surface/60 px-2.5 py-1 ${reveal(WF_DISPATCH_AT)}`}
      >
        <span className="flex size-5 shrink-0 items-center justify-center rounded-md border border-accent/40 bg-canvas text-accent">
          <Bot className="size-3" />
        </span>
        <span className="min-w-0">
          <span className="block text-[11px] font-semibold text-foreground">
            Host · dispatch
          </span>
          <span className="block truncate text-[10.5px] text-subtle">
            Split the question into two research tracks
          </span>
        </span>
      </div>

      <WorkflowAgent
        borderClass={phase >= WF_DOCS_AT ? 'border-accent/30' : 'border-transparent'}
        revealQuery={reveal(WF_DOCS_AT)}
        revealTool={reveal(WF_DOCS_TOOL_AT)}
        name="Docs analyst"
        query="Which filings cover Q3 revenue?"
        tool="search-user-knowledge-bases"
        detail="6 chunks"
        icon={Database}
        active={phase === WF_DOCS_TOOL_AT && !done}
        complete={phase > WF_DOCS_TOOL_AT || done}
      />

      <WorkflowAgent
        borderClass={phase >= WF_MARKET_AT ? 'border-accent/30' : 'border-transparent'}
        revealQuery={reveal(WF_MARKET_AT)}
        revealTool={reveal(WF_MARKET_TOOL_AT)}
        name="Market analyst"
        query="What's the latest market reaction?"
        tool="web-search"
        detail="5 results"
        icon={Globe}
        active={phase === WF_MARKET_TOOL_AT && !done}
        complete={phase > WF_MARKET_TOOL_AT || done}
      />

      <div
        className={`flex items-center gap-2 rounded-lg border border-border/70 bg-surface/60 px-2.5 py-1 ${reveal(WF_ANSWER_AT)}`}
      >
        <span
          className={`flex size-5 shrink-0 items-center justify-center rounded-md border bg-canvas ${
            done ? 'border-success/40 text-success' : 'border-accent/40 text-accent'
          }`}
        >
          {done ? <Check className="size-3" /> : <GitMerge className="size-3" />}
        </span>
        <span className="min-w-0 flex-1 text-[11px] font-semibold text-foreground">
          Host · synthesize
        </span>
        <span className="shrink-0 font-mono text-[9.5px] text-subtle">final answer</span>
      </div>
    </>
  )

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface/80 p-3.5 shadow-[0_28px_80px_-36px_rgba(0,0,0,0.65)] backdrop-blur-xl"
    >
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-accent/70 to-transparent"
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-20 -right-16 size-44 rounded-full bg-accent-soft blur-3xl"
      />

      {/* Header */}
      <div className="relative flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-accent to-violet text-white shadow-control">
            {mode === 'Agent' ? <Bot className="size-4" /> : <GitMerge className="size-4" />}
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[12.5px] leading-tight font-semibold text-foreground">
              {mode === 'Agent' ? 'research-agent' : 'research-workflow'}
            </span>
            <span className="block truncate font-mono text-[10.5px] text-subtle">
              {mode === 'Agent' ? 'Nova 2 Lite · run 8f3a19' : '3 agents · graph'}
            </span>
          </span>
        </div>
        <span
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 text-[10.5px] font-semibold ${
            done
              ? 'border-success/40 bg-success-soft text-success'
              : 'border-accent/40 bg-accent-soft text-accent'
          }`}
        >
          <span className="relative flex size-1.5">
            {!done ? (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-accent opacity-70" />
            ) : null}
            <span
              className={`relative inline-flex size-1.5 rounded-full ${done ? 'bg-success' : 'bg-accent'}`}
            />
          </span>
          {done ? 'Complete' : 'Streaming'}
        </span>
      </div>

      {/* Mode switch */}
      <div className="relative mt-2.5">
        <Segmented options={MODES} value={mode} size="sm" onChange={(next) => setMode(next)} />
      </div>

      {/* Run progress */}
      <div className="relative mt-2 h-0.5 overflow-hidden rounded-full bg-raised/60">
        <div
          className="h-full rounded-full bg-gradient-to-r from-accent via-violet to-teal transition-[width] duration-700 ease-out"
          style={{ width: `${Math.min(100, (phase / total) * 100)}%` }}
        />
      </div>

      {/* Run body */}
      <div className="relative mt-3 space-y-1.5">
        {/* Question */}
        <div className="flex items-start gap-2.5 rounded-xl border border-border bg-canvas/70 p-2">
          <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full border border-border bg-raised text-muted">
            <User className="size-3" />
          </span>
          <p className="min-h-[32px] text-[11.5px] leading-snug text-foreground">
            {mode === 'Agent' ? QUESTION : WF_QUESTION}
          </p>
        </div>

        {/* Both productions share one grid cell, so the card height is the max
            of the two and never jumps when the switch is used. */}
        <div className="grid">
          <div
            className={`col-start-1 row-start-1 space-y-1.5 ${
              mode === 'Agent' ? '' : 'invisible'
            }`}
          >
            {renderAgentBody()}
          </div>
          <div
            className={`col-start-1 row-start-1 space-y-1.5 ${
              mode === 'Workflow' ? '' : 'invisible'
            }`}
          >
            {renderWorkflowBody()}
          </div>
        </div>

        {/* Answer (reserved height, types out when reached) */}
        <div className="rounded-xl border border-border bg-canvas/70 p-2">
          <p
            className={`min-h-[34px] text-[11.5px] leading-relaxed text-foreground ${
              answerStarted ? 'animate-reveal-x' : 'opacity-0'
            }`}
          >
            Q3 revenue grew 18% QoQ to $4.2M, led by Northwind
            <Citation n={1} />. Retention held at 94%, with expansion offsetting
            churn
            <Citation n={2} />.
          </p>
        </div>

        {/* References (reserved height, fades in) */}
        <div className={reveal(refsAt)}>
          <p className="mb-1 text-[9.5px] font-semibold tracking-wide text-subtle uppercase">
            References
          </p>
          <div className="grid grid-cols-2 gap-1.5">
            {REFERENCES.map(({ icon: Icon, title, meta }, index) => (
              <div
                key={title}
                className="flex items-center gap-2 rounded-lg border border-border bg-canvas/60 px-2 py-1"
              >
                <span className="flex size-5 shrink-0 items-center justify-center rounded-md border border-border bg-raised text-accent">
                  <Icon className="size-2.5" />
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[10.5px] font-medium text-foreground">
                    <span className="mr-1 font-mono text-accent">[{index + 1}]</span>
                    {title}
                  </span>
                  <span className="block truncate text-[9.5px] text-subtle">{meta}</span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

/** One teammate's block in the workflow run: query then its tool call. */
function WorkflowAgent({
  borderClass,
  revealQuery,
  revealTool,
  name,
  query,
  tool,
  detail,
  icon: Icon,
  active,
  complete,
}: {
  borderClass: string
  revealQuery: string
  revealTool: string
  name: string
  query: string
  tool: string
  detail: string
  icon: LucideIcon
  active: boolean
  complete: boolean
}) {
  return (
    <div className={`border-l-2 pl-2.5 transition-colors ${borderClass}`}>
      <div className={`flex items-center gap-2 py-0.5 ${revealQuery}`}>
        <span className="flex size-5 shrink-0 items-center justify-center rounded-md border border-border bg-canvas text-accent">
          <Icon className="size-3" />
        </span>
        <span className="min-w-0 truncate text-[11px] font-semibold text-foreground">
          {name}
        </span>
        <span className="shrink-0 rounded-full border border-border bg-canvas/60 px-1.5 py-0.5 text-[8.5px] font-medium text-subtle">
          handoff
        </span>
      </div>
      <p className={`mt-0.5 pl-7 text-[10.5px] leading-snug text-muted ${revealQuery}`}>
        {query}
      </p>
      <div
        className={`mt-0.5 flex items-center gap-2 rounded-lg border px-2 py-1 transition-colors ${revealTool} ${
          active ? 'border-accent/40 bg-accent-soft' : 'border-transparent bg-raised/40'
        }`}
      >
        <span
          className={`flex size-5 shrink-0 items-center justify-center rounded-md border bg-canvas ${
            active
              ? 'border-accent/40 text-accent'
              : complete
                ? 'border-success/40 text-success'
                : 'border-border text-muted'
          }`}
        >
          {active ? (
            <Loader2 className="size-3 animate-spin" />
          ) : complete ? (
            <Check className="size-3" />
          ) : (
            <Icon className="size-3" />
          )}
        </span>
        <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-foreground">
          {tool}
        </span>
        <span className="shrink-0 font-mono text-[9.5px] text-subtle">{detail}</span>
      </div>
    </div>
  )
}

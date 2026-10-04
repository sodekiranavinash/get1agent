import { useEffect, useState } from 'react'
import { CheckCircle2, Code2, Loader2, Play, Sparkles, User } from 'lucide-react'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { useInView } from '../../hooks/useInView'

const QUESTION = 'A tool that converts currency using live rates.'

const CODE_LINES = [
  'def run(args):',
  '    amount = float(args["amount"])',
  '    rate = fetch_rate(args["from"], args["to"])',
  '    return {"converted": round(amount * rate, 2),',
  '            "rate": rate}',
]

const CODE = CODE_LINES.join('\n')

const SCHEMA = ['amount: number', 'from: string', 'to: string']

// Phase 0 type the question · 1 generating · 2 reply · 3 type the code ·
// 4 schema + running test · 5 done.
const DONE = 5

/**
 * The MCP Builder: a visitor describes a tool in plain English and watches the
 * generator type out a runnable Python MCP tool with input/output schemas and an
 * inline test. Self-playing and looping while in view.
 */
export function McpBuilderPreview() {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const { ref, inView } = useInView<HTMLDivElement>({ threshold: 0.2 })
  // Under reduced motion the build is simply shown finished.
  const [phase, setPhase] = useState(() => (reduced ? DONE : 0))
  const [questionLen, setQuestionLen] = useState(() => (reduced ? QUESTION.length : 0))
  const [codeLen, setCodeLen] = useState(() => (reduced ? CODE.length : 0))

  useEffect(() => {
    if (reduced || !inView) return
    let handle = 0

    if (phase === 0) {
      handle =
        questionLen >= QUESTION.length
          ? window.setTimeout(() => setPhase(1), 350)
          : window.setTimeout(() => setQuestionLen((n) => n + 1), 34)
    } else if (phase === 1) {
      handle = window.setTimeout(() => setPhase(2), 1000)
    } else if (phase === 2) {
      handle = window.setTimeout(() => setPhase(3), 800)
    } else if (phase === 3) {
      handle =
        codeLen >= CODE.length
          ? window.setTimeout(() => setPhase(4), 350)
          : window.setTimeout(
              () => setCodeLen((n) => Math.min(CODE.length, n + 2)),
              26,
            )
    } else if (phase === 4) {
      handle = window.setTimeout(() => setPhase(DONE), 1100)
    } else if (phase === DONE) {
      handle = window.setTimeout(() => {
        setQuestionLen(0)
        setCodeLen(0)
        setPhase(0)
      }, 3000)
    }

    return () => window.clearTimeout(handle)
  }, [phase, questionLen, codeLen, inView, reduced])

  const typedCode = CODE.slice(0, codeLen)
  const codeLines = typedCode.split('\n')
  const typingCode = phase === 3
  const answered = phase >= 2
  const schemasShown = phase >= 4
  const done = phase >= DONE

  return (
    <div
      ref={ref}
      className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Sparkles className="size-3.5 shrink-0 text-accent" />
          <span className="text-[12px] font-semibold text-foreground">MCP Builder</span>
        </div>
        <span className="rounded-full border border-accent/40 bg-accent-soft px-2 py-0.5 text-[10.5px] font-semibold text-accent">
          natural language
        </span>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {/* Chat */}
        <div className="space-y-2.5">
          <div className="flex items-start gap-2">
            <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-raised text-muted">
              <User className="size-3" />
            </span>
            <p className="min-h-[34px] rounded-xl rounded-tl-sm border border-border bg-canvas/60 px-3 py-2 text-[12px] leading-relaxed text-foreground">
              {/* The untyped remainder stays in layout (invisible) so the bubble
                  keeps its final height while the text types out. */}
              <span>{QUESTION.slice(0, questionLen)}</span>
              <span
                className={`mx-0.5 inline-block h-3.5 w-1.5 translate-y-0.5 bg-accent align-middle ${
                  phase === 0 ? 'animate-caret' : 'invisible'
                }`}
              />
              <span className="invisible" aria-hidden="true">
                {QUESTION.slice(questionLen)}
              </span>
            </p>
          </div>

          {/* Assistant reply. The final content is always laid out (only faded
              in) so the card never grows while it types. */}
          <div className="relative flex items-start gap-2">
            <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-accent/40 bg-accent-soft text-accent">
              <Sparkles className="size-3" />
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={`rounded-xl rounded-tl-sm border border-border bg-canvas/60 px-3 py-2 text-[12px] leading-relaxed text-foreground transition-opacity duration-300 ${
                  answered ? 'opacity-100' : 'opacity-0'
                }`}
              >
                Generated{' '}
                <span className="font-mono text-accent">convert_currency</span> — a
                Python MCP tool with input and output schemas.
              </p>
              <span
                className={`mt-2 inline-flex items-center gap-2 rounded-md border border-success/40 bg-success-soft px-2 py-1 font-mono text-[10.5px] text-success transition-opacity duration-300 ${
                  answered ? 'opacity-100' : 'opacity-0'
                }`}
              >
                +24
                <span className="text-rose">−3</span>
              </span>
              {!answered && phase >= 1 ? (
                <span className="absolute inset-x-0 top-0 ml-8 flex items-center gap-2 rounded-xl border border-border bg-canvas/60 px-3 py-2 text-[12px] text-muted">
                  <Loader2 className="size-3 animate-spin" />
                  Generating the tool…
                </span>
              ) : null}
            </div>
          </div>
        </div>

        {/* Code */}
        <div className="overflow-hidden rounded-xl border border-border bg-canvas/80">
          <div className="flex items-center gap-1.5 border-b border-border px-3 py-2">
            <Code2 className="size-3.5 text-muted" />
            <span className="font-mono text-[11px] text-muted">convert_currency.py</span>
            {typingCode ? (
              <span className="ml-auto inline-flex items-center gap-1 text-[9.5px] text-accent">
                <Loader2 className="size-2.5 animate-spin" />
                writing
              </span>
            ) : null}
          </div>
          <pre className="scrollbar-thin min-h-[118px] overflow-x-auto px-3 py-2.5 font-mono text-[11px] leading-relaxed text-foreground">
            {codeLen > 0
              ? codeLines.map((line, index) => (
                  <span key={index} className="block">
                    <span className="mr-3 inline-block w-3 text-right text-subtle select-none">
                      {index + 1}
                    </span>
                    {line}
                    {typingCode && index === codeLines.length - 1 ? (
                      <span className="ml-0.5 inline-block h-3 w-1.5 translate-y-0.5 animate-caret bg-accent align-middle" />
                    ) : null}
                  </span>
                ))
              : null}
          </pre>
          <div className="flex flex-wrap gap-1.5 border-t border-border px-3 py-2">
            {SCHEMA.map((field) => (
              <span
                key={field}
                className={`rounded-md border border-border bg-raised/50 px-1.5 py-0.5 font-mono text-[10px] text-muted transition-opacity duration-300 ${
                  schemasShown ? 'opacity-100' : 'opacity-0'
                }`}
              >
                {field}
              </span>
            ))}
          </div>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">
        <span className="inline-flex items-center gap-1.5 rounded-md bg-accent px-2.5 py-1 text-[11px] font-semibold text-white">
          <Play className="size-3" />
          Test
        </span>
        {phase === 4 ? (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-border bg-canvas/60 px-2 py-1 font-mono text-[10.5px] text-muted">
            <Loader2 className="size-3 animate-spin" />
            running…
          </span>
        ) : done ? (
          <span className="inline-flex items-center gap-1.5 rounded-md border border-success/40 bg-success-soft px-2 py-1 font-mono text-[10.5px] text-success">
            <CheckCircle2 className="size-3" />
            200 OK · 84ms
          </span>
        ) : null}
      </div>
    </div>
  )
}

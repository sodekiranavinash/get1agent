import { CheckCircle2, Code2, Play, Sparkles, User } from 'lucide-react'

const CODE_LINES = [
  'def run(args):',
  '    amount = float(args["amount"])',
  '    rate = fetch_rate(args["from"], args["to"])',
  '    return {"converted": round(amount * rate, 2),',
  '            "rate": rate}',
]

const SCHEMA = ['amount: number', 'from: string', 'to: string']

/**
 * The MCP Builder: describe a tool in plain English and get a runnable Python
 * MCP tool with input/output schemas and an inline test.
 */
export function McpBuilderPreview() {
  return (
    <div className="relative overflow-hidden rounded-2xl border border-border bg-surface/70 p-4 shadow-panel backdrop-blur-xl">
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
            <p className="rounded-xl rounded-tl-sm border border-border bg-canvas/60 px-3 py-2 text-[12px] leading-relaxed text-foreground">
              A tool that converts currency using live rates.
            </p>
          </div>
          <div className="flex items-start gap-2">
            <span className="mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full border border-accent/40 bg-accent-soft text-accent">
              <Sparkles className="size-3" />
            </span>
            <div className="min-w-0 flex-1">
              <p className="rounded-xl rounded-tl-sm border border-border bg-canvas/60 px-3 py-2 text-[12px] leading-relaxed text-foreground">
                Generated <span className="font-mono text-accent">convert_currency</span> — a
                Python MCP tool with input and output schemas.
              </p>
              <span className="mt-2 inline-flex items-center gap-2 rounded-md border border-success/40 bg-success-soft px-2 py-1 font-mono text-[10.5px] text-success">
                +24
                <span className="text-rose">−3</span>
              </span>
            </div>
          </div>
        </div>

        {/* Code */}
        <div className="overflow-hidden rounded-xl border border-border bg-canvas/80">
          <div className="flex items-center gap-1.5 border-b border-border px-3 py-2">
            <Code2 className="size-3.5 text-muted" />
            <span className="font-mono text-[11px] text-muted">convert_currency.py</span>
          </div>
          <pre className="scrollbar-thin overflow-x-auto px-3 py-2.5 font-mono text-[11px] leading-relaxed text-foreground">
            {CODE_LINES.map((line, index) => (
              <span key={line} className="block">
                <span className="mr-3 inline-block w-3 text-right text-subtle select-none">
                  {index + 1}
                </span>
                {line}
              </span>
            ))}
            <span className="ml-6 inline-block h-3.5 w-1.5 translate-y-0.5 animate-caret bg-accent align-middle" />
          </pre>
          <div className="flex flex-wrap gap-1.5 border-t border-border px-3 py-2">
            {SCHEMA.map((field) => (
              <span
                key={field}
                className="rounded-md border border-border bg-raised/50 px-1.5 py-0.5 font-mono text-[10px] text-muted"
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
        <span className="inline-flex items-center gap-1.5 rounded-md border border-success/40 bg-success-soft px-2 py-1 font-mono text-[10.5px] text-success">
          <CheckCircle2 className="size-3" />
          200 OK · 84ms
        </span>
      </div>
    </div>
  )
}

import { useState } from 'react'
import { Check, Copy, X } from 'lucide-react'
import { Badge } from '../../components/ui/Badge'
import { Card } from '../../components/ui/Card'
import { Spinner } from '../../components/ui/Spinner'
import type { McpCallResponse } from '../lib/mcpAdmin'

type McpResultPanelProps = {
  result: McpCallResponse | null
  error: string | null
  running: boolean
}

function CopyButton({ value }: { value: unknown }) {
  const [copied, setCopied] = useState(false)
  const text =
    (typeof value === 'string' ? value : JSON.stringify(value, null, 2)) ?? ''

  return (
    <button
      type="button"
      onClick={() => {
        void navigator.clipboard?.writeText(text).then(() => {
          setCopied(true)
          window.setTimeout(() => setCopied(false), 1500)
        })
      }}
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium text-subtle transition-colors hover:bg-raised hover:text-foreground"
    >
      {copied ? (
        <Check className="h-3.5 w-3.5 text-success" strokeWidth={2} />
      ) : (
        <Copy className="h-3.5 w-3.5" strokeWidth={1.75} />
      )}
      {copied ? 'Copied' : 'Copy'}
    </button>
  )
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="scrollbar-thin max-h-[60vh] w-full max-w-full overflow-auto rounded-xl border border-border bg-canvas/60 p-4 text-[11px] leading-relaxed break-words whitespace-pre-wrap text-foreground">
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

type Tab = 'result' | 'raw'

export function McpResultPanel({ result, error, running }: McpResultPanelProps) {
  const [tab, setTab] = useState<Tab>('result')

  if (running) {
    return (
      <Card padding="lg">
        <div className="flex items-center gap-3 py-6">
          <Spinner size="sm" />
          <span className="text-sm text-muted">Running tool…</span>
        </div>
      </Card>
    )
  }

  if (error) {
    return (
      <Card padding="lg" className="border-warning/40">
        <div className="flex items-start gap-3">
          <X className="mt-0.5 h-4 w-4 shrink-0 text-warning" strokeWidth={2} />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-foreground">Request failed</p>
            <p className="mt-1 text-xs leading-relaxed break-words text-muted">
              {error}
            </p>
          </div>
        </div>
      </Card>
    )
  }

  if (!result) {
    return (
      <Card padding="lg">
        <p className="py-6 text-center text-sm text-muted">
          Run a tool to see its result here.
        </p>
      </Card>
    )
  }

  const payload = result.data ?? result.result
  const raw = { request: result.request, response: result.response }

  return (
    <Card padding="none" className="min-w-0 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div className="flex min-w-0 items-center gap-2">
          {result.ok ? (
            <Badge variant="success" dot>
              Success
            </Badge>
          ) : (
            <Badge variant="warning">Tool error</Badge>
          )}
          <code className="min-w-0 text-xs font-semibold break-words text-foreground">
            {result.tool}
          </code>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="text-[11px] text-subtle">{result.durationMs} ms</span>
          <CopyButton value={tab === 'result' ? payload : raw} />
        </div>
      </div>

      <div className="flex items-center gap-1 border-b border-border px-3 py-2">
        {(['result', 'raw'] as const).map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => setTab(item)}
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
              tab === item
                ? 'bg-accent-soft text-accent'
                : 'text-muted hover:text-foreground'
            }`}
          >
            {item === 'result' ? 'Result' : 'Raw JSON-RPC'}
          </button>
        ))}
        {result.auth0Sub ? (
          <span className="ml-auto max-w-[50%] truncate text-[11px] text-subtle">
            as {result.auth0Sub}
          </span>
        ) : null}
      </div>

      <div className="min-w-0 p-4">
        {tab === 'result' ? (
          result.ok ? (
            <JsonBlock value={payload} />
          ) : (
            <div className="rounded-xl border border-warning/30 bg-warning-soft/40 p-4">
              <p className="text-xs leading-relaxed break-words text-warning">
                {result.error?.message ?? 'The tool returned an error.'}
              </p>
            </div>
          )
        ) : (
          <div className="min-w-0 space-y-3">
            <div className="min-w-0">
              <p className="mb-1 text-[11px] font-semibold text-muted">
                → request (admin → knowledge-mcp)
              </p>
              <JsonBlock value={result.request} />
            </div>
            <div className="min-w-0">
              <p className="mb-1 text-[11px] font-semibold text-muted">← response</p>
              <JsonBlock value={result.response} />
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  BarChart3,
  Check,
  Copy,
  ListTree,
  Loader2,
  X,
} from 'lucide-react'
import { ObservationList, type TraceView } from './ObservationList'
import { ObservationDetail } from './ObservationDetail'
import { useTheme } from '../../theme/ThemeProvider'
import {
  formatCostUsd,
  formatDurationMs,
  formatTokens,
  usageTotals,
  type LabTraceDetail,
} from '../../lib/lab'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="hidden min-w-[68px] flex-col rounded-lg border border-border bg-surface px-2.5 py-1 sm:flex">
      <span className="text-[9.5px] tracking-wider text-subtle uppercase">{label}</span>
      <span className="font-mono text-[12px] text-foreground">{value}</span>
    </div>
  )
}

function Logo() {
  const { theme } = useTheme()
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'
  return (
    <Link
      to="/"
      className="flex shrink-0 items-center transition-opacity hover:opacity-80"
      aria-label="OneAgent home"
      title="OneAgent"
    >
      <img src={logoSrc} alt="OneAgent" className="h-8 w-auto object-contain sm:h-9" />
    </Link>
  )
}

const STATUS_META: Record<string, { label: string; className: string }> = {
  ok: { label: 'Success', className: 'bg-success-soft text-success' },
  completed: { label: 'Success', className: 'bg-success-soft text-success' },
  error: { label: 'Error', className: 'bg-rose-soft text-rose' },
  awaiting_input: { label: 'Awaiting input', className: 'bg-warning-soft text-warning' },
}

/**
 * Full-screen, chrome-free trace explorer (Langfuse-style): the app's own
 * observation store on the left — with a tree/waterfall toggle — and the
 * selected stage's input/output/metadata on the right. No sidebar, no navbar.
 */
export function TraceViewer({
  trace,
  loading = false,
  error = '',
  onClose,
}: {
  trace: LabTraceDetail | null
  loading?: boolean
  error?: string
  onClose?: () => void
}) {
  const observations = useMemo(() => trace?.observations ?? [], [trace?.observations])
  const [view, setView] = useState<TraceView>('tree')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)

  const selected =
    observations.find((observation) => observation.id === selectedId) ??
    observations[0] ??
    null
  const usage = usageTotals(trace?.usage)
  const status = STATUS_META[String(trace?.status || 'ok')] ?? STATUS_META.ok
  const traceId = trace?.traceId || trace?.id || ''

  async function copyId() {
    if (!traceId) return
    try {
      await navigator.clipboard.writeText(traceId)
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      // Clipboard unavailable; ignore.
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-canvas text-foreground">
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 border-b border-border bg-surface/85 px-4 py-2.5 backdrop-blur">
        <Logo />
        <span className="hidden h-6 w-px bg-border sm:block" />

        <div className="flex min-w-0 flex-1 items-center gap-3">
          <div className="min-w-0">
            <p className="truncate text-[13px] font-semibold text-foreground">
              {loading ? 'Loading trace…' : trace?.name || 'Trace'}
            </p>
            {traceId ? (
              <button
                type="button"
                onClick={copyId}
                className="inline-flex items-center gap-1.5 font-mono text-[11px] text-subtle transition-colors hover:text-foreground"
                title="Copy trace id"
              >
                {traceId}
                {copied ? <Check className="size-3" /> : <Copy className="size-3" />}
              </button>
            ) : null}
          </div>
        </div>

        <div className="flex items-center gap-2">
          {trace ? (
            <>
              <span className={`rounded-full px-2 py-0.5 text-[11px] ${status.className}`}>
                {status.label}
              </span>
              <Stat
                label="Latency"
                value={formatDurationMs(trace.latencyMs ?? (trace.latency ? trace.latency * 1000 : null))}
              />
              <Stat label="Tokens" value={usage.total ? formatTokens(usage.total) : '—'} />
              <Stat label="Cost" value={formatCostUsd(trace.costMicroUsd) ?? '—'} />
              <Stat label="Stages" value={String(observations.length)} />
            </>
          ) : null}
          <button
            type="button"
            onClick={onClose}
            className="ml-1 inline-flex size-8 items-center justify-center rounded-lg border border-border text-muted transition-colors hover:bg-raised hover:text-foreground"
            title="Close"
          >
            <X className="size-4" />
          </button>
        </div>
      </header>

      {error ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <div className="max-w-md rounded-xl border border-border bg-surface p-8 text-center">
            <h1 className="text-[15px] font-semibold text-foreground">Trace unavailable</h1>
            <p className="mt-2 text-[13px] text-muted">{error}</p>
          </div>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
          <aside className="flex max-h-[46%] w-full shrink-0 flex-col border-b border-border bg-surface/40 lg:max-h-none lg:w-[380px] lg:border-b-0 lg:border-r">
            <div className="flex items-center justify-between border-b border-border px-3 py-2">
              <span className="text-[10.5px] font-semibold tracking-[0.14em] text-subtle uppercase">
                {observations.length} stage{observations.length === 1 ? '' : 's'}
              </span>
              <div className="flex items-center gap-0.5 rounded-md border border-border p-0.5">
                <button
                  type="button"
                  onClick={() => setView('tree')}
                  className={`inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors ${
                    view === 'tree' ? 'bg-accent-soft text-accent' : 'text-muted hover:text-foreground'
                  }`}
                >
                  <ListTree className="size-3.5" /> Tree
                </button>
                <button
                  type="button"
                  onClick={() => setView('waterfall')}
                  className={`inline-flex items-center gap-1 rounded px-2 py-1 text-[11px] transition-colors ${
                    view === 'waterfall'
                      ? 'bg-accent-soft text-accent'
                      : 'text-muted hover:text-foreground'
                  }`}
                >
                  <BarChart3 className="size-3.5" /> Waterfall
                </button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-auto">
              {loading ? (
                <TraceListSkeleton />
              ) : (
                <ObservationList
                  observations={observations}
                  selectedId={selected?.id ?? null}
                  onSelect={(observation) => setSelectedId(observation.id)}
                  view={view}
                />
              )}
            </div>
          </aside>

          <main className="min-h-0 flex-1 overflow-auto bg-canvas">
            {loading ? (
              <TraceDetailSkeleton />
            ) : (
              <ObservationDetail key={selected?.id ?? 'none'} observation={selected} />
            )}
          </main>
        </div>
      )}
    </div>
  )
}

function TraceListSkeleton() {
  return (
    <div className="space-y-1 p-2">
      {Array.from({ length: 8 }).map((_, index) => (
        <div key={index} className="h-9 w-full animate-pulse rounded-md bg-raised/50" />
      ))}
    </div>
  )
}

function TraceDetailSkeleton() {
  return (
    <div className="space-y-3 p-5">
      <div className="h-6 w-1/3 animate-pulse rounded bg-raised/50" />
      <div className="h-16 w-full animate-pulse rounded-lg bg-raised/40" />
      <div className="h-40 w-full animate-pulse rounded-lg bg-raised/30" />
      <div className="flex items-center gap-2 text-[12px] text-subtle">
        <Loader2 className="size-3.5 animate-spin" /> Loading trace data…
      </div>
    </div>
  )
}

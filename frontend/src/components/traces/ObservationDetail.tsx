import { useState } from 'react'
import type { ReactNode } from 'react'
import { Code2, ExternalLink } from 'lucide-react'
import {
  extractMessages,
  formatDurationMs,
  formatTimestamp,
  humanizeKey,
  isPlainObject,
  observationMeta,
  parseMaybeJson,
  safeStringify,
  usageTotals,
  type MessagePart,
  type TraceObservation,
} from '../../lib/lab'

const ROLE_STYLE: Record<string, string> = {
  system: 'border-violet/40 bg-violet-soft',
  user: 'border-accent/40 bg-accent-soft',
  assistant: 'border-teal/40 bg-teal-soft',
  tool: 'border-warning/40 bg-warning-soft',
}

function MessageList({ messages }: { messages: MessagePart[] }) {
  return (
    <div className="space-y-2">
      {messages.map((message, index) => (
        <div
          key={index}
          className={`animate-trace-row rounded-lg border px-3 py-2 ${
            ROLE_STYLE[message.role] ?? 'border-border bg-raised/50'
          }`}
          style={{ animationDelay: `${Math.min(index * 30, 240)}ms` }}
        >
          <p className="mb-1 text-[10px] font-semibold tracking-wider text-subtle uppercase">
            {message.role}
          </p>
          <pre className="font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-foreground">
            {message.content}
          </pre>
        </div>
      ))}
    </div>
  )
}

function TextBlock({ text }: { text: string }) {
  if (!text) return null
  return (
    <pre className="rounded-lg border border-border bg-canvas/60 p-3 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-foreground">
      {text}
    </pre>
  )
}

function ScalarRows({ entries }: { entries: [string, unknown][] }) {
  return (
    <dl className="divide-y divide-border/40">
      {entries.map(([key, value]) => (
        <div key={key} className="flex items-start justify-between gap-6 py-1.5">
          <dt className="shrink-0 text-[11.5px] text-subtle">{humanizeKey(key)}</dt>
          <dd className="min-w-0 text-right font-mono text-[12px] break-words text-foreground">
            {value === null || value === undefined || value === '' ? '—' : String(value)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

function ObjectView({ value }: { value: Record<string, unknown> }) {
  const entries = Object.entries(value).filter(([, entry]) => entry !== undefined)
  const scalars = entries.filter(
    ([, entry]) => entry === null || typeof entry !== 'object',
  )
  const nested = entries.filter(
    ([, entry]) => entry !== null && typeof entry === 'object',
  )
  return (
    <div className="space-y-3">
      {scalars.length > 0 ? <ScalarRows entries={scalars} /> : null}
      {nested.map(([key, entry]) => (
        <div key={key}>
          <p className="mb-1 text-[11px] font-semibold tracking-wide text-subtle uppercase">
            {humanizeKey(key)}
          </p>
          <ValueView value={entry} />
        </div>
      ))}
    </div>
  )
}

function ValueView({ value }: { value: unknown }) {
  const messages = extractMessages(value)
  if (messages) return <MessageList messages={messages} />
  const parsed = parseMaybeJson(value)
  if (parsed === null || parsed === undefined) return null
  if (typeof parsed === 'string') return <TextBlock text={parsed} />
  if (isPlainObject(parsed)) return <ObjectView value={parsed} />
  return <TextBlock text={safeStringify(parsed)} />
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mt-5">
      <h3 className="mb-2 text-[11px] font-semibold tracking-[0.14em] text-subtle uppercase">
        {title}
      </h3>
      {children}
    </section>
  )
}

function Meta({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-surface px-3 py-2">
      <p className="text-[10px] tracking-wide text-subtle uppercase">{label}</p>
      <p className="mt-0.5 font-mono text-[12.5px] text-foreground">{value}</p>
    </div>
  )
}

type SourceRef = { title?: string; url?: string; subtitle?: string }

export function ObservationDetail({
  observation,
}: {
  observation: TraceObservation | null
}) {
  const [raw, setRaw] = useState(false)

  if (!observation) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-[12.5px] text-subtle">
        No observations are available for this trace.
      </div>
    )
  }

  const meta = observationMeta(observation.type)
  const usage = usageTotals(observation.usage)
  const metadata = observation.metadata ?? {}
  const metadataEntries = Object.entries(metadata).filter(([, value]) => value !== undefined)
  const sources = Array.isArray(metadata.sources) ? (metadata.sources as SourceRef[]) : []
  const hasMetadata = metadataEntries.length > 0

  return (
    <div className="animate-trace-in p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full bg-raised px-2 py-0.5 text-[11px] ${meta.text}`}
            >
              <span className={`size-1.5 rounded-full ${meta.dot}`} />
              {meta.label}
            </span>
            {observation.model ? (
              <span className="rounded-full border border-border px-2 py-0.5 font-mono text-[11px] text-muted">
                {observation.model}
              </span>
            ) : null}
            {observation.level === 'ERROR' ? (
              <span className="rounded-full bg-rose-soft px-2 py-0.5 text-[11px] text-rose">
                Error
              </span>
            ) : null}
          </div>
          <h2 className="mt-2 font-mono text-[15px] font-semibold break-words text-foreground">
            {observation.name}
          </h2>
        </div>
        <button
          type="button"
          onClick={() => setRaw((current) => !current)}
          className={`inline-flex shrink-0 items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-[11.5px] transition-colors ${
            raw
              ? 'border-accent/50 bg-accent-soft text-accent'
              : 'border-border text-muted hover:text-foreground'
          }`}
        >
          <Code2 className="size-3.5" />
          Raw
        </button>
      </div>

      {raw ? (
        <pre className="mt-4 max-h-[70vh] overflow-auto rounded-lg border border-border bg-canvas/70 p-3 font-mono text-[11.5px] whitespace-pre-wrap text-muted">
          {safeStringify(observation)}
        </pre>
      ) : (
        <>
          {observation.statusMessage ? (
            <p className="mt-3 rounded-md bg-rose-soft px-3 py-2 text-[12px] text-rose">
              {observation.statusMessage}
            </p>
          ) : null}

          <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Meta label="Duration" value={formatDurationMs(observation.durationMs)} />
            <Meta
              label="Started"
              value={
                observation.startTime
                  ? formatTimestamp(new Date(observation.startTime).toISOString())
                  : '—'
              }
            />
            <Meta
              label="Tokens"
              value={usage.total ? `${usage.input.toLocaleString()} / ${usage.output.toLocaleString()}` : '—'}
            />
            <Meta label="Type" value={meta.label} />
          </div>

          {observation.input !== undefined && observation.input !== null ? (
            <Section title="Input">
              <ValueView value={observation.input} />
            </Section>
          ) : null}

          {observation.output !== undefined && observation.output !== null ? (
            <Section title="Output">
              <ValueView value={observation.output} />
            </Section>
          ) : null}

          {sources.length > 0 ? (
            <Section title="Sources">
              <ul className="space-y-1">
                {sources.map((source, index) => (
                  <li key={`${source.url ?? source.title ?? index}`} className="text-[12.5px]">
                    {source.url ? (
                      <a
                        href={source.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1.5 text-accent hover:underline"
                      >
                        {source.title || source.url}
                        <ExternalLink className="size-3" />
                      </a>
                    ) : (
                      <span className="text-muted">{source.title || 'source'}</span>
                    )}
                  </li>
                ))}
              </ul>
            </Section>
          ) : null}

          {hasMetadata ? (
            <Section title="Metadata">
              <ObjectView value={metadata} />
            </Section>
          ) : null}
        </>
      )}
    </div>
  )
}

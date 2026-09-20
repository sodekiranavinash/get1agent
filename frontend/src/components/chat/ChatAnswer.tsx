import type { ReactNode } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AlertTriangle, Ban, Braces, FileText, Sparkles } from 'lucide-react'
import type { AgentOutputFormat } from '../../lib/agents'
import type { ChatTurnStatus } from '../../lib/chat'

/**
 * Turn citation markers (``[1]``, ``[1][3]``, ``[1, 2]``) into links so they can
 * scroll the matching source card into view in the sources carousel.
 */
function linkCitations(content: string, turnId: string): string {
  return content.replace(/\[(\d+(?:\s*[-,]\s*\d+)*)\](?!\()/g, (_match, group: string) =>
    group
      .split(/[-,]/)
      .map((part) => part.trim())
      .filter(Boolean)
      .map((number) => `[${number}](#source-${turnId}-${number})`)
      .join(''),
  )
}

/** A round, numbered citation badge that jumps to its source line. */
function CitationBadge({ number, turnId }: { number: number; turnId: string }) {
  return (
    <button
      type="button"
      onClick={() =>
        document
          .getElementById(`source-${turnId}-${number}`)
          ?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' })
      }
      title={`Source ${number}`}
      className="mx-0.5 inline-flex size-3.5 items-center justify-center rounded-full bg-info-soft align-super text-[9px] font-bold text-info transition-colors hover:bg-info hover:text-white"
    >
      {number}
    </button>
  )
}

function CitationLink({ href, children }: { href?: string; children?: ReactNode }) {
  if (href?.startsWith('#source-')) {
    const id = href.slice(1)
    const match = /^source-(.+)-(\d+)$/.exec(id)
    if (match) {
      return <CitationBadge number={Number(match[2])} turnId={match[1]} />
    }
  }
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  )
}

/** Render plain text with ``[n]`` markers as round citation badges. */
function TextWithCitations({
  content,
  turnId,
  streaming,
}: {
  content: string
  turnId: string
  streaming: boolean
}) {
  const parts = content.split(/(\[\d+(?:\s*[-,]\s*\d+)*\])/g)
  return (
    <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-foreground">
      {parts.map((part, index) => {
        const match = /^\[(\d+(?:\s*[-,]\s*\d+)*)\]$/.exec(part)
        if (match) {
          return (
            <span key={index}>
              {match[1]
                .split(/[-,]/)
                .map((entry) => entry.trim())
                .filter(Boolean)
                .map((number) => (
                  <CitationBadge key={number} number={Number(number)} turnId={turnId} />
                ))}
            </span>
          )
        }
        return <span key={index}>{part}</span>
      })}
      {streaming ? <Caret /> : null}
    </p>
  )
}

function Caret() {
  return (
    <span
      className="ml-0.5 inline-block h-3.5 w-[2px] translate-y-0.5 animate-pulse rounded-full bg-accent align-middle"
      aria-hidden="true"
    />
  )
}

function JsonAnswer({ content, streaming }: { content: string; streaming: boolean }) {
  let pretty = content
  try {
    pretty = JSON.stringify(JSON.parse(content), null, 2)
  } catch {
    // The stream may still be mid-object; show it raw until it parses.
  }
  return (
    <div className="overflow-hidden rounded-lg border border-border bg-canvas/60">
      <div className="flex items-center gap-1.5 border-b border-border px-3 py-1.5 text-[10px] font-semibold tracking-[0.1em] text-subtle uppercase">
        <Braces className="size-3" />
        JSON
      </div>
      <pre className="scrollbar-thin max-h-[420px] overflow-auto whitespace-pre-wrap p-3 font-mono text-[11.5px] leading-relaxed text-foreground">
        {pretty}
        {streaming ? <Caret /> : null}
      </pre>
    </div>
  )
}

export function ChatAnswer({
  content,
  format,
  status,
  turnId,
}: {
  content: string
  format: AgentOutputFormat
  status: ChatTurnStatus
  turnId: string
}) {
  const streaming = status === 'streaming'
  const FormatIcon = format === 'json' ? Braces : format === 'text' ? FileText : Sparkles

  if (status === 'error' && !content) {
    return (
      <p className="flex items-center gap-2 text-[12.5px] text-accent">
        <AlertTriangle className="size-3.5 shrink-0" />
        The run failed before producing an answer.
      </p>
    )
  }

  if (status === 'stopped' && !content) {
    return (
      <p className="flex items-center gap-2 text-[12.5px] text-warning">
        <Ban className="size-3.5 shrink-0" />
        Run stopped.
      </p>
    )
  }

  if (!content) {
    return null
  }

  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.12em] text-subtle uppercase">
        <FormatIcon className="size-3" />
        Response · {format}
      </div>
      {format === 'markdown' ? (
        <div className="md-preview">
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: CitationLink }}>
            {linkCitations(content, turnId)}
          </ReactMarkdown>
          {streaming ? <Caret /> : null}
        </div>
      ) : format === 'json' ? (
        <JsonAnswer content={content} streaming={streaming} />
      ) : (
        <TextWithCitations content={content} turnId={turnId} streaming={streaming} />
      )}
    </div>
  )
}

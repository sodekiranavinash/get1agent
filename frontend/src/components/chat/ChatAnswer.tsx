import { useMemo, type ReactNode } from 'react'
import ReactMarkdown, { type Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'
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

/**
 * Drop the inline `[n]` markers entirely.
 *
 * Used by the narrow widget, which renders no numbered source carousel — a badge
 * there jumps nowhere and just leaves a stray blue "1" mid-sentence. The
 * horizontal whitespace goes with it so no double space is left behind, while a
 * leading newline is deliberately *not* matched (that would glue two paragraphs
 * together).
 */
function stripCitations(content: string): string {
  return content.replace(/[ \t]*\[(\d+(?:\s*[-,]\s*\d+)*)\](?!\()/g, '')
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

/**
 * A `/path` that is *shaped* like an app route: one lowercase-hyphen segment and
 * an optional `#fragment`.
 *
 * Deliberately strict, in the spirit of `backend/ai-assistant/src/deep_links.py`
 * — a wrong link is worse than no link. It accepts `/metrics`, `/agent-builder`
 * and `/docs#metrics`, and leaves `/v1/lab/metrics`, `/usr/local/bin` and any
 * multi-segment file path as plain code.
 */
const INTERNAL_ROUTE = /^\/[a-z0-9][a-z0-9-]*(?:#[a-z0-9][a-z0-9-]*)?$/

/** True for a link that points inside this app rather than off it. */
function isInternalHref(href: string): boolean {
  return href.startsWith('/') && !href.startsWith('//')
}

function CitationLink({ href, children }: { href?: string; children?: ReactNode }) {
  if (href?.startsWith('#source-')) {
    const id = href.slice(1)
    const match = /^source-(.+)-(\d+)$/.exec(id)
    if (match) {
      return <CitationBadge number={Number(match[2])} turnId={match[1]} />
    }
  }
  // An in-app route navigates the router. It used to be an `<a target="_blank">`,
  // which reloads the whole bundle in a new tab and loses the client-side route.
  if (href && isInternalHref(href)) {
    return <Link to={href}>{children}</Link>
  }
  return (
    <a href={href} target="_blank" rel="noreferrer">
      {children}
    </a>
  )
}

/**
 * Rescue a route the model wrapped in brackets but never gave a target.
 *
 * Asked for `[Metrics](/metrics)`, a small model reliably drops the parenthetical
 * and writes `[/metrics]` instead, which Markdown renders as literal text — dead
 * in exactly the way the code span was. The route is the one thing the model got
 * right, so it becomes both the label and the target. A `(?!\()` guard leaves a
 * real link alone, and this only runs for AI Assistant (`linkRoutes`), never for
 * an agent's answer.
 */
function linkBareRoutes(content: string): string {
  return content.replace(/\[(\/[^\][\s()]+)\](?!\()/g, (_match, route: string) => `[${route}](${route})`)
}

/**
 * A code span that is really an in-app route.
 *
 * The assistant was told to write routes as inline code ("open the Agent builder
 * (`/agent-builder`)"), which renders as plain text: clicking `/metrics` did
 * nothing at all. The prompt now asks for a Markdown link, and this is the
 * safety net for an answer that still writes one — the route is only linked when
 * it passes `INTERNAL_ROUTE`, and fenced code (which carries a `language-*`
 * class) is never touched.
 */
function RouteCode({ className, children }: { className?: string; children?: ReactNode }) {
  const text = typeof children === 'string' ? children.trim() : ''
  if (!className && INTERNAL_ROUTE.test(text)) {
    return (
      <Link to={text} title={text} className="text-accent hover:underline">
        <code>{text}</code>
      </Link>
    )
  }
  return <code className={className}>{children}</code>
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
  compact = false,
  linkRoutes = false,
}: {
  content: string
  format: AgentOutputFormat
  status: ChatTurnStatus
  turnId: string
  /** Wide surfaces (chat, builder) keep the format header; narrow widgets drop it. */
  compact?: boolean
  /**
   * Turn a route-shaped code span (`` `/metrics` ``) into a link.
   *
   * Opt-in, and only the AI Assistant widget asks for it: its prompt is the one
   * that writes routes, so elsewhere a `/path` in a code span is more likely to
   * be code than a page. Markdown links always navigate the router.
   */
  linkRoutes?: boolean
}) {
  const streaming = status === 'streaming'
  const FormatIcon = format === 'json' ? Braces : format === 'text' ? FileText : Sparkles
  // The widget has no numbered carousel to jump to, so it drops the markers
  // instead of rendering badges that go nowhere.
  const body = compact ? stripCitations(content) : content
  // Avi's answers only: its prompt is the one that writes routes, so a `/path`
  // in a code span or a bare bracket elsewhere is far more likely to be code.
  const linked = linkRoutes ? linkBareRoutes(body) : body
  const components = useMemo<Components>(
    () => (linkRoutes ? { a: CitationLink, code: RouteCode } : { a: CitationLink }),
    [linkRoutes],
  )

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
      {!compact && (
        <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold tracking-[0.12em] text-subtle uppercase">
          <FormatIcon className="size-3" />
          Response · {format}
        </div>
      )}
      {format === 'markdown' ? (
        <div
          className={
            compact
              ? 'md-preview text-[12.5px] [&_.md-preview]:text-[12.5px] [&_.md-preview]:leading-[1.65]'
              : 'md-preview'
          }
        >
          <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
            {linkCitations(linked, turnId)}
          </ReactMarkdown>
          {streaming ? <Caret /> : null}
        </div>
      ) : format === 'json' ? (
        <JsonAnswer content={body} streaming={streaming} />
      ) : (
        <TextWithCitations content={body} turnId={turnId} streaming={streaming} />
      )}
    </div>
  )
}

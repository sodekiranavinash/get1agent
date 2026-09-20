import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, ExternalLink, FileText } from 'lucide-react'
import { Dialog } from '../ui/Dialog'
import { useApiClient } from '../../lib/api'
import { fetchKnowledgeBase } from '../../lib/knowledgeBases'
import type { ChatSource } from '../../lib/chat'

/** Only absolute URLs are safe to open from the UI. */
export function sourceHref(url: string | undefined): string | undefined {
  if (!url) return undefined
  return /^https?:\/\//i.test(url) ? url : undefined
}

/** A human-readable site/publication name derived from a web URL. */
export function siteLabel(url: string | undefined): string {
  if (!url) return ''
  try {
    const host = new URL(url).hostname.replace(/^www\./, '')
    const parts = host.split('.').filter(Boolean)
    const base = parts.length >= 2 ? parts[parts.length - 2] : (parts[0] ?? '')
    return base
      .split(/[-_]/)
      .filter(Boolean)
      .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ')
  } catch {
    return ''
  }
}

/**
 * Resolve a knowledge source's document reference, falling back to parsing the
 * relative ``sourceUrl`` when the runtime did not send the explicit ids.
 */
function knowledgeRef(source: ChatSource): { kbId?: string; docId?: string; page: number } {
  const url = source.url ?? ''
  const match = /\/knowledge-bases\/([^/]+)\/documents\/([^/?#]+)/.exec(url)
  const pageMatch = /[#&]page=(\d+)/.exec(url)
  return {
    kbId: source.knowledgeBaseId ?? match?.[1],
    docId: source.documentId ?? match?.[2],
    page: source.page ?? (pageMatch ? Number(pageMatch[1]) : 1),
  }
}

function isImageSource(source: ChatSource): boolean {
  if ((source.contentType ?? '').startsWith('image/')) return true
  return /\.(png|jpe?g|gif|webp|bmp|svg)$/i.test(source.title)
}

function pdfUrl(downloadUrl: string | undefined, page: number, toolbar: boolean): string | undefined {
  if (!downloadUrl) return undefined
  return `${downloadUrl}#page=${page}&toolbar=${toolbar ? 1 : 0}&navpanes=0&scrollbar=${toolbar ? 1 : 0}&view=FitH`
}

type UrlCacheEntry = { urls: Record<string, string>; at: number }
const kbUrlCache = new Map<string, UrlCacheEntry>()
const CACHE_TTL_MS = 45 * 60 * 1000

/** Resolve presigned download URLs for the knowledge documents cited. */
function useDocumentUrls(sources: ChatSource[]): Record<string, string> {
  const api = useApiClient()
  const [urls, setUrls] = useState<Record<string, string>>({})
  const kbKey = useMemo(() => {
    const ids = new Set<string>()
    for (const source of sources) {
      if (source.kind !== 'knowledge') continue
      const { kbId } = knowledgeRef(source)
      if (kbId) ids.add(kbId)
    }
    return [...ids].sort().join(',')
  }, [sources])

  useEffect(() => {
    if (!kbKey) return
    let cancelled = false
    void (async () => {
      const next: Record<string, string> = {}
      for (const kbId of kbKey.split(',')) {
        const cached = kbUrlCache.get(kbId)
        if (cached && Date.now() - cached.at < CACHE_TTL_MS) {
          Object.assign(next, cached.urls)
          continue
        }
        try {
          const detail = await fetchKnowledgeBase(api, kbId)
          const map: Record<string, string> = {}
          for (const document of detail.documents) {
            if (document.downloadUrl) map[document.id] = document.downloadUrl
          }
          kbUrlCache.set(kbId, { urls: map, at: Date.now() })
          Object.assign(next, map)
        } catch {
          // Preview falls back to a document icon.
        }
      }
      if (!cancelled) setUrls(next)
    })()
    return () => {
      cancelled = true
    }
  }, [api, kbKey])

  return urls
}

function NumberBadge({ number }: { number?: number }) {
  if (!number) return null
  return (
    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-info text-[10px] font-bold text-white shadow-control">
      {number}
    </span>
  )
}

function SourceCard({
  source,
  turnId,
  downloadUrl,
  onOpen,
}: {
  source: ChatSource
  turnId: string
  downloadUrl?: string
  onOpen: (source: ChatSource) => void
}) {
  const knowledge = source.kind === 'knowledge'
  const href = sourceHref(source.url)
  const ref = knowledgeRef(source)
  const preview = knowledge
    ? pdfUrl(downloadUrl, ref.page, false)
    : source.image || source.favicon
  const site = siteLabel(source.url)

  const handleClick = () => {
    if (knowledge) onOpen(source)
    else if (href) window.open(href, '_blank', 'noreferrer')
  }

  return (
    <button
      id={source.index ? `source-${turnId}-${source.index}` : undefined}
      type="button"
      onClick={handleClick}
      className="group relative flex w-[196px] shrink-0 snap-start flex-col overflow-hidden rounded-xl bg-canvas text-left ring-1 ring-border/60 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-panel hover:ring-border-strong/70"
    >
      <div className="relative aspect-[4/3] w-full overflow-hidden bg-gradient-to-br from-raised to-canvas">
        {preview ? (
          knowledge ? (
            <iframe
              title={source.title}
              src={preview}
              loading="lazy"
              className="pointer-events-none h-full w-full"
            />
          ) : (
            <img src={preview} alt="" loading="lazy" className="h-full w-full object-cover" />
          )
        ) : (
          <div className="flex h-full w-full items-center justify-center">
            {knowledge ? (
              <FileText className="size-7 text-subtle/60" />
            ) : (
              <span className="text-xl font-semibold text-subtle/60">
                {site.charAt(0) || '?'}
              </span>
            )}
          </div>
        )}
        <span className="absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-black/25 to-transparent" />
        <span className="absolute top-2 left-2">
          <NumberBadge number={source.index} />
        </span>
        <span className="absolute right-2 bottom-2 flex size-6 items-center justify-center rounded-full bg-black/45 text-white opacity-0 backdrop-blur transition-opacity group-hover:opacity-100">
          {knowledge ? <FileText className="size-3" /> : <ExternalLink className="size-3" />}
        </span>
      </div>
      <div className="flex min-w-0 flex-col gap-1 p-2.5">
        <span className="line-clamp-2 text-[11.5px] leading-snug font-medium text-foreground">
          {source.title}
        </span>
        <span className="truncate text-[10.5px] text-subtle">
          {knowledge ? source.subtitle : site}
        </span>
      </div>
    </button>
  )
}

function SourceViewer({
  source,
  downloadUrl,
  onClose,
}: {
  source: ChatSource | null
  downloadUrl?: string
  onClose: () => void
}) {
  if (!source) return null
  const knowledge = source.kind === 'knowledge'
  const href = sourceHref(source.url)
  const ref = knowledgeRef(source)
  const preview = knowledge ? pdfUrl(downloadUrl, ref.page, true) : undefined

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose()
      }}
      title={source.title}
      description={knowledge ? source.subtitle : siteLabel(source.url)}
      size="2xl"
    >
      {knowledge ? (
        isImageSource(source) && downloadUrl ? (
          <img
            src={downloadUrl}
            alt={source.title}
            className="mx-auto max-h-[75vh] rounded-lg border border-border"
          />
        ) : preview ? (
          <iframe
            title={source.title}
            src={preview}
            className="h-[75vh] w-full rounded-lg border border-border bg-canvas"
          />
        ) : (
          <p className="py-10 text-center text-[12.5px] text-subtle">
            Preview unavailable for this document.
          </p>
        )
      ) : (
        <div className="space-y-3">
          {source.image ? (
            <img
              src={source.image}
              alt=""
              className="max-h-72 w-full rounded-lg border border-border object-cover"
            />
          ) : null}
          {source.snippet ? (
            <p className="text-[12.5px] leading-relaxed text-muted">{source.snippet}</p>
          ) : null}
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-info hover:underline"
            >
              Open page
              <ExternalLink className="size-3.5" />
            </a>
          ) : null}
        </div>
      )}
    </Dialog>
  )
}

/**
 * Numbered, horizontally scrollable source strip shown under a finished answer.
 * Knowledge documents preview the cited PDF page; web results preview their
 * image/favicon and open the page.
 */
export function SourceCarousel({ sources, turnId }: { sources: ChatSource[]; turnId: string }) {
  const urls = useDocumentUrls(sources)
  const scroller = useRef<HTMLDivElement>(null)
  const [viewer, setViewer] = useState<ChatSource | null>(null)

  const ordered = useMemo(
    () => [...sources].sort((a, b) => (a.index ?? 0) - (b.index ?? 0)),
    [sources],
  )

  if (ordered.length === 0) return null

  const scrollBy = (direction: number) =>
    scroller.current?.scrollBy({ left: direction * 210, behavior: 'smooth' })

  const downloadUrlFor = (source: ChatSource) => {
    const { docId } = knowledgeRef(source)
    return docId ? urls[docId] : undefined
  }

  return (
    <div className="rounded-2xl border border-border/70 bg-surface/40 p-2">
      <div className="flex items-center gap-2 px-1.5 py-1.5">
        <span className="text-[10px] font-semibold tracking-[0.14em] text-subtle uppercase">
          Sources
        </span>
        <span className="rounded-full bg-raised px-1.5 py-0.5 text-[10px] font-semibold text-muted tabular-nums">
          {ordered.length}
        </span>
        <div className="ml-auto flex items-center gap-0.5">
          <button
            type="button"
            onClick={() => scrollBy(-1)}
            aria-label="Previous sources"
            className="rounded-full p-1.5 text-subtle transition-colors hover:bg-raised hover:text-foreground"
          >
            <ChevronLeft className="size-3.5" />
          </button>
          <button
            type="button"
            onClick={() => scrollBy(1)}
            aria-label="Next sources"
            className="rounded-full p-1.5 text-subtle transition-colors hover:bg-raised hover:text-foreground"
          >
            <ChevronRight className="size-3.5" />
          </button>
        </div>
      </div>
      <div
        ref={scroller}
        className="scrollbar-thin flex snap-x snap-mandatory gap-2.5 overflow-x-auto px-1.5 pb-1.5"
      >
        {ordered.map((source) => (
          <SourceCard
            key={source.id}
            source={source}
            turnId={turnId}
            downloadUrl={downloadUrlFor(source)}
            onOpen={setViewer}
          />
        ))}
      </div>
      <SourceViewer
        source={viewer}
        downloadUrl={viewer ? downloadUrlFor(viewer) : undefined}
        onClose={() => setViewer(null)}
      />
    </div>
  )
}

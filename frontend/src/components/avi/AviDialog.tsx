import { useEffect, useLayoutEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link, useLocation } from 'react-router-dom'
import { ArrowUp, Plus, Square, X } from 'lucide-react'

import { AviMessage } from './AviMessage'
import { useAvi } from './useAvi'
import { startersFor } from '../../content/aviStarters'
import { AviMark } from './AviMark'
import { useApiClient } from '../../lib/api'
import { useAuthToken } from '../../hooks/useAuthToken'
import { useDemoMode } from '../../auth/useDemoMode'

/**
 * Avi's dialog.
 *
 * Deliberately a **dialog, not a page**: it opens over whatever the user is
 * looking at, on every page, and never navigates them away. The only exits are
 * the close button, `Esc`, and a deliberately-clicked deep link.
 *
 * The panel has a **fixed height** (`min(540px, 72vh)`, and a taller sheet on a
 * phone) rather than a max-height, so the transcript, the header and the
 * composer never resize as an answer streams in — a chat that grows and shrinks
 * with its content makes the send button jump under the cursor.
 */
export function AviDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const location = useLocation()
  const { isAuthenticated } = useAuth0()
  // The demo API client rejects every write, so a thumb there could never be
  // stored — offer it only when the rating can actually land.
  const demo = useDemoMode()
  const token = useAuthToken()
  const api = useApiClient()
  const [draft, setDraft] = useState('')
  const composerRef = useRef<HTMLTextAreaElement | null>(null)

  // One rule: signed in → the signed-in session route; signed out (guest, demo,
  // not-yet-loaded) → the guest badge route. `lib/avi.ts` picks between them from
  // the presence of this token, so there is nothing else to decide here.
  const signedIn = isAuthenticated
  const avi = useAvi({
    route: location.pathname,
    authToken: signedIn ? token : undefined,
    open,
    api,
  })
  // Destructured rather than read off `avi.*`: the hook's return object also
  // carries a ref, and property access on it during render trips the React
  // Compiler's ref rule once it declines to optimize this component.
  const {
    turns,
    status,
    error,
    retryAfter,
    signInRequired,
    streaming,
    send,
    stop,
    reset,
    rate,
    scrollRef,
  } = avi

  useEffect(() => {
    if (!open) return
    const timer = window.setTimeout(() => composerRef.current?.focus(), 80)
    return () => window.clearTimeout(timer)
  }, [open])

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  // Grow the composer with its content, up to the box's own max height.
  useLayoutEffect(() => {
    const node = composerRef.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight, 112)}px`
  }, [draft, open])

  // Re-rolled on each opening, not each render: `open` is in the deps *and* read
  // in the body, which is what makes the four questions different every time the
  // dialog comes up while staying stable for as long as it is on screen (and while
  // the user is typing). Closed, nothing renders, so the empty list is inert.
  const starters = useMemo(
    () => (open ? startersFor(location.pathname) : []),
    [open, location.pathname],
  )

  if (!open) return null

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const text = draft.trim()
    if (!text) return
    setDraft('')
    void send(text)
  }

  const empty = turns.length === 0
  const nearLimit = draft.length > 1_800

  return (
    <>
      {/* A tap outside closes Avi *on a phone*, where the sheet owns most of the
          screen. On a desktop the panel is a small corner card, so a full-screen
          click-catcher is actively harmful: at `z-[60]` it sat above the top bar
          and the sidebar, so clicking anything in them — the theme switch, a nav
          link — hit the backdrop and closed Avi instead, aborting whatever Avi was
          mid-answer on. Closing there is the Close button and Esc, deliberately. */}
      <div
        className="fixed inset-0 z-[60] bg-black/20 sm:hidden"
        onClick={onClose}
        aria-hidden
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Avi, the get1agent assistant"
        className="fixed inset-x-0 bottom-0 z-[61] flex h-[min(80vh,600px)] flex-col overflow-hidden rounded-t-xl border border-border bg-canvas shadow-2xl sm:inset-x-auto sm:right-5 sm:bottom-24 sm:h-[min(540px,72vh)] sm:w-[380px] sm:rounded-xl"
      >
        {/* Grab handle: the phone sheet reads as draggable even though it is not. */}
        <div className="mx-auto mt-2 h-1 w-9 shrink-0 rounded-full bg-border-strong sm:hidden" aria-hidden />

        {/* Header — fixed above the transcript. */}
        <header className="flex shrink-0 items-center gap-2.5 border-b border-border px-3.5 py-2.5">
          <span className="relative shrink-0">
            <AviMark className="size-8 rounded-lg" />
            {streaming && (
              <span className="absolute -right-0.5 -bottom-0.5 size-2.5 animate-pulse rounded-full border-2 border-canvas bg-accent" />
            )}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-[13px] font-semibold text-foreground">Avi</p>
            <p className="truncate text-[11px] text-muted">
              {streaming
                ? 'Answering…'
                : status === 'limited'
                  ? 'Limit reached'
                  : "I'm your personal platform assistant"}
            </p>
          </div>
          {turns.length > 0 && (
            <button
              type="button"
              onClick={reset}
              title="New chat"
              aria-label="New chat"
              className="grid size-7 place-items-center rounded-md text-muted transition-colors hover:bg-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
            >
              <Plus className="size-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            title="Close"
            aria-label="Close Avi"
            className="grid size-7 place-items-center rounded-md text-muted transition-colors hover:bg-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
          >
            <X className="size-4" />
          </button>
        </header>

        {/* Transcript — the only scrollable region, so the panel height is stable. */}
        <div
          ref={scrollRef}
          className="scrollbar-thin min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-3.5 py-3.5"
        >
          {empty ? (
            <div className="space-y-3.5">
              <div className="rounded-lg border border-border bg-raised/60 px-3 py-2.5">
                <p className="text-[12.5px] leading-relaxed text-foreground">
                  Hi — I&apos;m Avi.
                </p>
                <p className="mt-1 text-[12px] leading-relaxed text-muted">
                  I can explain any feature, show you where to find it, and answer how-to
                  questions about the platform.
                </p>
              </div>
              <div className="space-y-2">
                <p className="text-[10.5px] font-semibold tracking-[0.08em] text-muted uppercase">
                  Try asking
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {starters.map((starter) => (
                    <button
                      key={starter}
                      type="button"
                      onClick={() => void send(starter)}
                      className="rounded-md border border-border-strong px-2.5 py-1 text-left text-[11.5px] text-foreground transition-colors hover:border-accent/50 hover:bg-raised hover:text-accent focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
                    >
                      {starter}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          ) : (
            turns.map((turn) => (
              <AviMessage
                key={turn.id}
                turn={turn}
                onExample={(q) => void send(q)}
                canRate={signedIn && !demo}
                onRate={(value, comment) => void rate(turn.id, value, comment)}
              />
            ))
          )}

          {status === 'limited' && (
            <div className="rounded-lg border border-border bg-raised px-3 py-2">
              <p className="text-[12px] text-foreground">
                You&apos;ve reached the Avi limit for now
                {retryAfter > 0
                  ? ` — try again in about ${Math.ceil(retryAfter / 60)} min`
                  : ''}
                .
              </p>
              {signInRequired && (
                <Link
                  to="/"
                  onClick={onClose}
                  className="mt-1 inline-block text-[12px] font-medium text-accent hover:underline"
                >
                  Sign in to keep asking →
                </Link>
              )}
            </div>
          )}

          {status === 'error' && error && (
            <p className="rounded-lg border border-border bg-raised px-3 py-2 text-[12px] text-warning">
              {error}
            </p>
          )}
        </div>

        {/* Composer — fixed below the transcript. */}
        <form onSubmit={submit} className="shrink-0 border-t border-border px-3 py-2.5">
          <div className="flex items-end gap-2 rounded-lg border border-border-strong bg-raised/40 p-1.5 transition-colors focus-within:border-accent/60">
            <textarea
              ref={composerRef}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  submit(event as unknown as FormEvent)
                }
              }}
              rows={1}
              maxLength={2000}
              placeholder="Ask about a feature…"
              aria-label="Ask Avi a question"
              className="scrollbar-thin max-h-28 min-h-8 flex-1 resize-none bg-transparent px-1.5 py-1 text-[12.5px] leading-relaxed text-foreground placeholder:text-muted focus-visible:outline-none"
            />
            {streaming ? (
              <button
                type="button"
                onClick={stop}
                title="Stop"
                aria-label="Stop answering"
                className="grid size-8 shrink-0 place-items-center rounded-lg border border-border-strong bg-canvas text-muted transition-colors hover:border-warning/50 hover:text-warning focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
              >
                <Square className="size-3 fill-current" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!draft.trim()}
                title="Send"
                aria-label="Send question"
                className="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-white transition-colors hover:bg-accent-hover focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none disabled:pointer-events-none disabled:opacity-40"
              >
                <ArrowUp className="size-4" />
              </button>
            )}
          </div>
          {nearLimit && (
            <p className="mt-1 px-1 text-right text-[10.5px] text-muted">
              {draft.length}/2000
            </p>
          )}
        </form>
      </div>
    </>
  )
}

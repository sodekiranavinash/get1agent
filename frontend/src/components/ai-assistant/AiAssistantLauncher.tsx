import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { X } from 'lucide-react'

import { AviIcon } from './AviIcon'
import { useFooterClearance } from './useFooterClearance'

/**
 * Avi's launcher — the bottom-right button, on **every** screen but the admin
 * console.
 *
 * Mounted **once**, from `App`, not from each layout. That is what lets the
 * dialog survive navigation: opening a source link no longer tears Avi down
 * mid-answer, because the widget is no longer a child of the shell being
 * replaced. The dialog itself is a lazy chunk, so a visitor who never opens Avi
 * never downloads the chat bundle.
 */
const AiAssistantDialog = lazy(() =>
  import('./AiAssistantDialog').then((module) => ({ default: module.AiAssistantDialog })),
)

/**
 * The launcher's resting offset from the viewport bottom, in px (`1.75rem`).
 *
 * Must equal `--avi-launcher-bottom` in `index.css`: it is passed to
 * `useFooterClearance` so the footer measurement is taken against the offset the
 * button actually rests at, and the dialog is anchored off the same variable. It
 * is deliberately a small gap — the button belongs near the corner, not floating
 * above it. **These two numbers move together**: the launcher's height plus a
 * little air is the dialog's floor.
 */
const LAUNCHER_REST_PX = 28

/** Matches the `avi-dialog-out` duration in `index.css`. */
const DIALOG_EXIT_MS = 140

/**
 * Keep a child mounted for a moment after it closes, so its exit animation can run.
 *
 * Closing an animated panel is awkward in React: the moment `open` flips false the
 * element would unmount, and an unmounted element cannot animate. So the answer to
 * "should it render at all" is separated from "is it open" — this returns the
 * former, holding it true through the closing transition.
 *
 * The one-shot state change is deferred to a frame rather than made synchronously
 * in the effect, which is what keeps it from cascading a render on every pass.
 */
function useDelayedUnmount(open: boolean, ms: number): boolean {
  const [rendered, setRendered] = useState(open)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    window.clearTimeout(timer.current)
    if (open) {
      const frame = window.requestAnimationFrame(() => setRendered(true))
      return () => window.cancelAnimationFrame(frame)
    }
    timer.current = window.setTimeout(() => setRendered(false), ms)
    return () => window.clearTimeout(timer.current)
  }, [open, ms])

  return rendered
}

/**
 * The one exception, decided by **path**.
 *
 * Deliberately the whole rule. An earlier version also gated on the active
 * *view* (`view === 'admin'`) and on demo mode; `view` is a session mode rather
 * than a route, so it hid Avi from an admin on every page instead of just the
 * console. A path check describes the surface, cannot go stale, and is obvious to
 * read.
 */
function isAdminConsole(pathname: string): boolean {
  return pathname === '/admin' || pathname.startsWith('/admin/')
}

export function AiAssistantLauncher() {
  const [open, setOpen] = useState(false)
  // Mounted on first open and then kept: the dialog renders `null` while closed,
  // so the transcript survives closing and reopening it. The lazy chunk is still
  // only fetched when someone actually opens Avi.
  const [mounted, setMounted] = useState(false)
  // Held true through the closing animation, so the panel closes rather than
  // vanishing.
  const dialogRendered = useDelayedUnmount(open, DIALOG_EXIT_MS)
  const { pathname } = useLocation()
  // Only measure while the dialog is shut — an open dialog covers the page, so
  // there is nothing left to dodge.
  const clearance = useFooterClearance(!open, LAUNCHER_REST_PX)

  if (isAdminConsole(pathname)) return null

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setMounted(true)
          setOpen((value) => !value)
        }}
        aria-label={open ? 'Close Avi' : 'Ask Avi'}
        title={open ? 'Close Avi' : 'Ask Avi about the platform'}
        aria-expanded={open}
        // Position, not `transform: translate`: every browser understands
        // `bottom`, and the clearance then cannot be lost to a transform shorthand
        // the browser ignores. The offset comes from the shared `--avi-*` variables
        // in `index.css`, which the dialog reads too — the two must agree, or the
        // dialog covers the button that is meant to close it.
        style={{ bottom: `calc(var(--avi-launcher-bottom) + ${clearance}px)` }}
        // `right-4`, not `right-5`: the button hugs the right edge (and the dialog
        // uses the same gutter, so the two stay aligned). `size-12` (48px) rather
        // than `size-14` (56px) — a 56px tile with a 32px glyph was loud enough to
        // compete with page content. It must stay equal to `--avi-launcher-size` in
        // `index.css`, which the dialog subtracts to find its floor.
        // `rounded-2xl`, not a full pill: softer than the old square, without
        // reading as a generic chat widget. `avi-launcher-in` is the entrance only
        // — it is `both`-filled, so it settles at scale(1) and then the hover
        // transform takes over.
        className="avi-launcher-in fixed right-4 z-[62] grid size-12 place-items-center rounded-2xl border border-accent/30 bg-accent text-white shadow-lg transition-[bottom,scale] duration-200 ease-out hover:scale-105 focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
        // NOTE: no `relative` here. `fixed` already establishes the containing block
        // for the swapped glyph, and adding `relative` silently overrode `fixed` —
        // Tailwind emits `.relative` after `.fixed`, so the button dropped out of
        // fixed positioning into the document flow at the bottom of the page.
      >
        {/*
         * The glyph itself swaps — closed is the sparkle, open is a full-size X.
         *
         * An earlier version kept the sparkle and floated a small X *badge* in its
         * corner; that read as two marks competing for one tile, and the badge was
         * far too small to be the close affordance it claimed to be. So the X takes
         * the tile, at the same size as the mark it replaces.
         *
         * Both glyphs stay mounted and crossfade rather than being conditionally
         * rendered, so the swap eases instead of snapping. The wrapper is
         * `aria-hidden`: the button's own `aria-label` already says whether this
         * control opens or closes, so the pair would only be noise.
         */}
        <span aria-hidden className="relative size-6">
          <AviIcon
            className={`absolute inset-0 m-auto size-6 transition-[opacity,scale] duration-150 ease-out ${
              open ? 'scale-75 opacity-0' : 'scale-100 opacity-100'
            }`}
          />
          <X
            strokeWidth={2.75}
            className={`absolute inset-0 m-auto size-6 transition-[opacity,scale] duration-150 ease-out ${
              open ? 'scale-100 opacity-100' : 'scale-75 opacity-0'
            }`}
          />
        </span>
      </button>

      {mounted && dialogRendered && (
        <Suspense fallback={null}>
          <AiAssistantDialog open={open} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </>
  )
}

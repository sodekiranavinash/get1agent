import { lazy, Suspense, useState } from 'react'
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
 * The launcher's resting offset from the viewport bottom, in px (`5.5rem`).
 *
 * The dialog is anchored above this — see `AiAssistantDialog`'s `sm:bottom-40` —
 * so the button stays visible and clickable while the dialog is open, and the icon
 * simply becomes an X. If this changes, that offset has to move with it.
 */
const LAUNCHER_REST_PX = 88

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
        // the browser ignores.
        style={{ bottom: `calc(5.5rem + ${clearance}px)` }}
        // `rounded-2xl`, not a full pill: softer than the old square, without
        // reading as a generic chat widget.
        className="fixed right-5 z-[62] grid size-14 place-items-center rounded-2xl border border-accent/30 bg-accent text-white shadow-lg transition-[bottom,scale] duration-200 ease-out hover:scale-105 focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
      >
        {/* Same control throughout — the icon becomes an X, nothing moves. */}
        {open ? (
          <X className="size-6" strokeWidth={2.5} />
        ) : (
          <AviIcon className="size-7" />
        )}
      </button>

      {mounted && (
        <Suspense fallback={null}>
          <AiAssistantDialog open={open} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </>
  )
}

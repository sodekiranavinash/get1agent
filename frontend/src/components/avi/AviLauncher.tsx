import { lazy, Suspense, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { X } from 'lucide-react'

import { AviMark } from './AviMark'
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
const AviDialog = lazy(() =>
  import('./AviDialog').then((module) => ({ default: module.AviDialog })),
)

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

export function AviLauncher() {
  const [open, setOpen] = useState(false)
  // Mounted on first open and then kept: the dialog renders `null` while closed,
  // so the transcript survives closing and reopening it. The lazy chunk is still
  // only fetched when someone actually opens Avi.
  const [mounted, setMounted] = useState(false)
  const { pathname } = useLocation()
  // Only measure while the button is on screen and the dialog is shut — an open
  // dialog covers the page, so there is nothing left to dodge.
  const clearance = useFooterClearance(!open)

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
        // Position, not `transform: translate`: every browser understands
        // `bottom`, and the clearance then cannot be lost to a transform
        // shorthand the browser ignores.
        style={{ bottom: `calc(2rem + ${clearance}px)` }}
        className="fixed right-5 z-[62] inline-flex h-11 items-center gap-2 rounded-xl border border-accent/30 bg-accent px-3 text-[13px] font-medium text-white shadow-lg transition-[bottom,scale] duration-200 ease-out hover:scale-[1.03] focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:outline-none"
      >
        {open ? (
          <X className="size-4" />
        ) : (
          <>
            <AviMark className="size-7 rounded-md" />
            <span className="hidden pr-1 sm:inline">Ask Avi</span>
          </>
        )}
      </button>

      {mounted && (
        <Suspense fallback={null}>
          <AviDialog open={open} onClose={() => setOpen(false)} />
        </Suspense>
      )}
    </>
  )
}

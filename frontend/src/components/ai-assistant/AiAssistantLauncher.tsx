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

/**
 * Where the launcher rests, and how tall the dialog it opens can be.
 *
 * These two numbers have to agree, and they are declared together for that reason:
 * the dialog is anchored to the bottom of the viewport at up to
 * `min(540px, 72vh)`, so a launcher that sits *below* that would be covered by the
 * dialog it just opened — leaving the close affordance unreachable on exactly the
 * screen where it matters.
 */
const LAUNCHER_REST_PX = 88 // 5.5rem
const DIALOG_ANCHOR = '6rem'
const DIALOG_MAX_HEIGHT = 'min(540px, 72vh)'

export function AiAssistantLauncher() {
  const [open, setOpen] = useState(false)
  // Mounted on first open and then kept: the dialog renders `null` while closed,
  // so the transcript survives closing and reopening it. The lazy chunk is still
  // only fetched when someone actually opens Avi.
  const [mounted, setMounted] = useState(false)
  const { pathname } = useLocation()
  // Only measure while the button is on screen and the dialog is shut — an open
  // dialog covers the page, so there is nothing left to dodge.
  const clearance = useFooterClearance(!open, LAUNCHER_REST_PX)

  if (isAdminConsole(pathname)) return null

  // The dialog's own bottom offset is measured from the viewport, so the launcher
  // is placed from the dialog's *top* edge when it is open.
  const rest = open
    ? `calc(${DIALOG_ANCHOR} + ${DIALOG_MAX_HEIGHT} + 0.75rem)`
    : `calc(5.5rem + ${clearance}px)`

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
        // `bottom`, and the clearance then cannot be lost to a transform
        // shorthand the browser ignores. The resting offset keeps the button well
        // clear of the footer.
        style={{ bottom: rest }}
        // `rounded-2xl`, not `rounded-full`: a full pill reads as a generic chat
        // widget, and squared-off corners match the cards and buttons elsewhere in
        // the product.
        className="fixed right-5 z-[62] grid size-14 place-items-center rounded-2xl border border-accent/30 bg-accent text-white shadow-lg transition-[bottom,scale] duration-200 ease-out hover:scale-105 focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas focus-visible:outline-none"
      >
        {/* One control opens and dismisses, so there is nothing to hunt for when
            the dialog is open. */}
        {open ? (
          <X className="size-6" strokeWidth={2.5} />
        ) : (
          <AviIcon className="size-8" />
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

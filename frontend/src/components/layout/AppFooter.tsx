import { Link, useLocation } from 'react-router-dom'
import { Cookie } from 'lucide-react'
import { useCookiePreferences } from '../cookie/CookiePreferencesProvider'
import { originState } from './returnTarget'

const linkClass =
  'text-muted no-underline transition-colors hover:text-accent'

const FOOTER_LINKS = [
  { label: 'Docs', to: '/docs' },
  { label: 'Support', to: '/support' },
  { label: 'Privacy Notice', to: '/privacy' },
  { label: 'Privacy Rights', to: '/privacy/rights' },
  { label: 'Sub-processors', to: '/sub-processors' },
  { label: 'Terms of Use', to: '/terms' },
  { label: 'Report Security Issues', to: '/security' },
]

/**
 * Fixed, full-width footer shown on every screen (including the landing page).
 * Every link carries the current path as its navigation origin so the opened
 * page can offer a precise "Return to …" link, and pages reached from the
 * public landing surface stay in the minimal public shell.
 */
export function AppFooter() {
  const { openPreferences } = useCookiePreferences()
  const location = useLocation()
  const origin = location.pathname
  const isPublic =
    location.pathname === '/' ||
    location.pathname === '/architecture' ||
    (location.state as { public?: boolean } | null)?.public === true
  const toOrigin = originState(origin, { isPublic })

  // The trace explorers are full-screen and chrome-free.
  const isTraceViewer =
    location.pathname.startsWith('/trace/') || /^\/traces\/[^/]+/.test(location.pathname)
  if (isTraceViewer) return null

  return (
    <footer className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-canvas/95 px-6 py-2.5 backdrop-blur lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-center gap-x-2.5 gap-y-1 text-[11px] text-subtle">
        <span>&copy; {new Date().getFullYear()} get1agent</span>
        <span className="text-border-strong" aria-hidden="true">
          |
        </span>
        {FOOTER_LINKS.map((link) => (
          <span key={link.label} className="flex items-center gap-x-2.5">
            <Link to={link.to} state={toOrigin} className={linkClass}>
              {link.label}
            </Link>
            <span className="text-border-strong" aria-hidden="true">
              |
            </span>
          </span>
        ))}
        <button
          type="button"
          onClick={openPreferences}
          className="inline-flex items-center gap-1.5 rounded-full border border-accent/35 bg-accent-soft/60 px-2.5 py-1 font-medium text-accent transition-colors hover:border-accent/60 hover:bg-accent-soft hover:text-accent-hover focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
        >
          <Cookie className="size-3.5" />
          Cookie Preferences
        </button>
        <span className="text-border-strong" aria-hidden="true">
          |
        </span>
        <Link to="/privacy#cookies" state={toOrigin} className={linkClass}>
          Do Not Share My Personal Information
        </Link>
      </div>
    </footer>
  )
}

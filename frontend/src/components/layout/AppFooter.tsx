import { Link, useLocation } from 'react-router-dom'
import { Cookie } from 'lucide-react'
import { useCookiePreferences } from '../cookie/CookiePreferencesProvider'
import { originState } from './returnTarget'

const linkClass =
  'text-muted no-underline transition-colors hover:text-accent'

const FOOTER_LINKS: { label: string; to: string; title?: string }[] = [
  { label: 'Support', to: '/support' },
  { label: 'Privacy Notice', to: '/privacy' },
  { label: 'Privacy Rights', to: '/privacy/rights' },
  { label: 'Sub-processors', to: '/sub-processors' },
  { label: 'Terms of Use', to: '/terms' },
  {
    label: 'Report Security Issues',
    to: '/security',
    title: 'Report a security or privacy issue',
  },
]

/**
 * In-flow footer shown at the end of every page (app shell and public shell).
 *
 * It is intentionally **not** fixed and never spans under the app sidebar, so
 * on small screens no link is ever clipped by the navigation rail. It is placed
 * as the last child of a flex column, so `mt-auto` keeps it pinned to the bottom
 * of short pages while long pages scroll it into view naturally.
 *
 * Every link carries the current path as its navigation origin so the opened
 * page can offer a precise "Return to …" link, and pages reached from the
 * public landing surface stay in the minimal public shell.
 *
 * The row is kept deliberately short and `whitespace-nowrap` so it always fits on
 * **one line** at `lg` and up: `/docs` is reachable from the sidebar and top bar
 * (so it is not duplicated here), and the long CCPA opt-out label is shown as
 * "Privacy Choices" with the full wording in its `title` tooltip.
 */
export function AppFooter({ className = '' }: { className?: string } = {}) {
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
    <footer
      className={`relative z-10 mt-auto border-t border-border bg-canvas/95 px-6 py-3.5 backdrop-blur lg:px-8 ${className}`}
    >
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-center gap-x-2 gap-y-1.5 whitespace-nowrap text-[11px] text-subtle lg:flex-nowrap">
        <span>&copy; {new Date().getFullYear()} get1agent</span>
        {FOOTER_LINKS.map((link) => (
          <span key={link.label} className="flex items-center gap-2">
            <Link
              to={link.to}
              state={toOrigin}
              className={linkClass}
              title={link.title}
            >
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
          className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-accent/35 bg-accent-soft/60 px-2.5 py-1 font-medium text-accent transition-colors hover:border-accent/60 hover:bg-accent-soft hover:text-accent-hover focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
        >
          <Cookie className="size-3.5" />
          Cookie Preferences
        </button>
        <Link
          to="/privacy#cookies"
          state={toOrigin}
          className={linkClass}
          title="Do Not Sell or Share My Personal Information"
        >
          Privacy Choices
        </Link>
      </div>
    </footer>
  )
}

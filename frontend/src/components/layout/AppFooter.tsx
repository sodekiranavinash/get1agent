import { Link } from 'react-router-dom'
import { Cookie } from 'lucide-react'
import { useCookiePreferences } from '../cookie/CookiePreferencesProvider'

const linkClass =
  'text-muted no-underline transition-colors hover:text-accent'

const LEGAL_LINKS = [
  { label: 'Privacy Policy', to: '/privacy' },
  { label: 'Terms of Use', to: '/terms' },
  { label: 'Report Security Issues', to: '/security' },
]

/**
 * Fixed, full-width footer shown on every screen (including sign-in). Content
 * is centred like Cloudflare's, and every link is internal so it opens in the
 * current page instead of a new tab.
 */
export function AppFooter() {
  const { openPreferences } = useCookiePreferences()

  return (
    <footer className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-canvas/95 px-6 py-2.5 backdrop-blur lg:px-8">
      <div className="mx-auto flex max-w-[1440px] flex-wrap items-center justify-center gap-x-2.5 gap-y-1 text-[11px] text-subtle">
        <span>&copy; {new Date().getFullYear()} OneAgent, Inc.</span>
        <span className="text-border-strong" aria-hidden="true">
          |
        </span>
        {LEGAL_LINKS.map((link) => (
          <span key={link.label} className="flex items-center gap-x-2.5">
            <Link to={link.to} className={linkClass}>
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
          className={`inline-flex items-center gap-1.5 ${linkClass}`}
        >
          <Cookie className="size-3.5" />
          Cookie Preferences
        </button>
        <span className="text-border-strong" aria-hidden="true">
          |
        </span>
        <Link to="/privacy#cookies" className={linkClass}>
          Do Not Share My Personal Information
        </Link>
      </div>
    </footer>
  )
}

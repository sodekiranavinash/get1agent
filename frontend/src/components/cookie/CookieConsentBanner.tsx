import { Cookie } from 'lucide-react'
import { Button } from '../ui/Button'
import { useCookiePreferences } from './CookiePreferencesProvider'

/**
 * First-visit consent banner. It disappears as soon as the visitor accepts,
 * rejects, or saves a choice in the preference centre.
 */
export function CookieConsentBanner() {
  const { decided, open, openPreferences, acceptAll, rejectAll } =
    useCookiePreferences()

  if (decided || open) return null

  return (
    <div
      role="dialog"
      aria-label="Cookie consent"
      className="fixed inset-x-0 bottom-14 z-40 px-4 pb-4"
    >
      <div className="mx-auto flex max-w-[1200px] flex-col gap-3 rounded-xl border border-border bg-surface/95 p-4 shadow-panel backdrop-blur sm:flex-row sm:items-center sm:gap-4">
        <span className="flex size-9 shrink-0 items-center justify-center rounded-lg border border-border bg-raised text-accent">
          <Cookie className="size-4" />
        </span>
        <p className="min-w-0 flex-1 text-[12px] leading-relaxed text-muted">
          We use cookies to run OneAgent, remember your preferences, and
          understand how the product is used. You can allow optional categories
          or reject everything but the cookies needed to sign in.
        </p>
        <div className="flex flex-wrap items-center gap-2 sm:flex-nowrap">
          <Button variant="ghost" size="sm" onClick={rejectAll}>
            Reject non-essential
          </Button>
          <Button variant="outline" size="sm" onClick={openPreferences}>
            Cookie Preferences
          </Button>
          <Button size="sm" onClick={acceptAll}>
            Accept all
          </Button>
        </div>
      </div>
    </div>
  )
}

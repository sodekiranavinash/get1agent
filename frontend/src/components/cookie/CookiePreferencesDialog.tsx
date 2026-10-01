import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, Cookie, ShieldCheck } from 'lucide-react'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Dialog } from '../ui/Dialog'
import { Switch } from '../ui/Switch'
import { useCookiePreferences } from './CookiePreferencesProvider'
import {
  COOKIE_CATEGORIES,
  rejectedPreferences,
  type CookieCategoryId,
  type CookiePreference,
} from '../../lib/cookies'

/**
 * Cloudflare-style cookie preference centre: each category is a collapsible
 * row with a toggle, Strictly Necessary is locked on, and the footer offers
 * Reject / Confirm / Accept all in one place.
 */
export function CookiePreferencesDialog() {
  const { open, closePreferences, preferences, save, acceptAll, rejectAll } =
    useCookiePreferences()

  if (!open) return null

  return (
    <CookiePreferencesForm
      preferences={preferences}
      onClose={closePreferences}
      onSave={save}
      onAcceptAll={acceptAll}
      onRejectAll={rejectAll}
    />
  )
}

type FormProps = {
  preferences: CookiePreference
  onClose: () => void
  onSave: (preferences: CookiePreference) => void
  onAcceptAll: () => void
  onRejectAll: () => void
}

/**
 * Mounted only while the dialog is open, so the draft state is always seeded
 * from the saved choices without needing a sync effect.
 */
function CookiePreferencesForm({
  preferences,
  onClose,
  onSave,
  onAcceptAll,
  onRejectAll,
}: FormProps) {
  const [draft, setDraft] = useState<CookiePreference>(preferences)
  const [expanded, setExpanded] = useState<Set<CookieCategoryId>>(
    () => new Set<CookieCategoryId>(['necessary']),
  )

  const toggle = (id: CookieCategoryId) => {
    setDraft((current) =>
      id === 'necessary'
        ? { ...current, necessary: true }
        : { ...current, [id]: !current[id] },
    )
  }

  const toggleExpanded = (id: CookieCategoryId) => {
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const optional = COOKIE_CATEGORIES.filter((category) => !category.required)
  const optionalEnabled = optional.filter((category) => draft[category.id]).length

  return (
    <Dialog
      open
      onOpenChange={(next) => (next ? undefined : onClose())}
      title="Cookie Preferences"
      description="We use cookies to run the product, understand how it is used, and remember your preferences. Choose which optional categories you allow."
      icon={<Cookie className="size-4 text-accent" />}
      size="lg"
      footer={
        <>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setDraft(rejectedPreferences())}
          >
            Reject non-essential
          </Button>
          <Button variant="outline" size="sm" onClick={onRejectAll}>
            Reject all
          </Button>
          <Button variant="secondary" size="sm" onClick={onAcceptAll}>
            Accept all
          </Button>
          <Button size="sm" onClick={() => onSave(draft)}>
            Save preferences
          </Button>
        </>
      }
    >
      <div className="space-y-2.5">
        {COOKIE_CATEGORIES.map((category) => {
          const isOpen = expanded.has(category.id)
          const checked = category.required || draft[category.id]
          return (
            <section
              key={category.id}
              className="overflow-hidden rounded-lg border border-border bg-raised/40"
            >
              <div className="flex items-center gap-3 px-4 py-3">
                <button
                  type="button"
                  onClick={() => toggleExpanded(category.id)}
                  aria-expanded={isOpen}
                  className="flex min-w-0 flex-1 items-center gap-2 text-left"
                >
                  <ChevronDown
                    className={`size-4 shrink-0 text-subtle transition-transform duration-150 ${
                      isOpen ? 'rotate-0' : '-rotate-90'
                    }`}
                  />
                  <span className="flex items-center gap-2">
                    <span className="text-[13px] font-semibold text-foreground">
                      {category.title}
                    </span>
                    {category.required ? (
                      <Badge variant="success">
                        <ShieldCheck className="size-3" />
                        Always active
                      </Badge>
                    ) : null}
                  </span>
                </button>
                <Switch
                  checked={checked}
                  disabled={category.required}
                  onChange={() => toggle(category.id)}
                  label={`${category.title} ${checked ? 'allowed' : 'blocked'}`}
                />
              </div>

              {isOpen ? (
                <div className="border-t border-border px-4 py-3">
                  <p className="text-[12px] leading-relaxed text-muted">
                    {category.description}
                  </p>
                  <div className="mt-3 overflow-hidden rounded-md border border-border">
                    <table className="w-full border-collapse text-left text-[11px]">
                      <thead className="bg-canvas/60 text-subtle">
                        <tr>
                          <th className="px-2.5 py-1.5 font-medium">Cookie</th>
                          <th className="px-2.5 py-1.5 font-medium">Purpose</th>
                          <th className="px-2.5 py-1.5 font-medium">Duration</th>
                        </tr>
                      </thead>
                      <tbody>
                        {category.examples.map((example) => (
                          <tr key={example.name} className="border-t border-border">
                            <td className="px-2.5 py-1.5 font-mono text-foreground">
                              {example.name}
                            </td>
                            <td className="px-2.5 py-1.5 text-muted">
                              {example.purpose}
                            </td>
                            <td className="px-2.5 py-1.5 whitespace-nowrap text-muted">
                              {example.duration}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </section>
          )
        })}
      </div>

      <p className="mt-4 text-[11px] leading-relaxed text-subtle">
        Optional categories enabled: {optionalEnabled} of {optional.length}. You
        can change these at any time from the footer. See the{' '}
        <Link
          to="/privacy#cookies"
          onClick={onClose}
          className="font-medium text-accent hover:underline"
        >
          Privacy Statement
        </Link>{' '}
        for details on how we handle personal data.
      </p>
    </Dialog>
  )
}

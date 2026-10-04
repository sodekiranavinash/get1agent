/**
 * Cookie consent preferences.
 *
 * A small, self-contained consent store persisted in localStorage (not a
 * tracking cookie itself). Every category except "Strictly Necessary" is
 * opt-in and defaults to rejected until the visitor makes a choice. The active
 * choices are exposed to the rest of the app through `useCookiePreferences()`
 * and the `get1agent:consent` window event, so optional features (analytics,
 * preference memory, experiments) can gate themselves on real consent instead
 * of assuming one.
 */

export type CookieCategoryId =
  | 'necessary'
  | 'performance'
  | 'functional'
  | 'targeting'

export type CookiePreference = Record<CookieCategoryId, boolean>

export type CookieExample = {
  name: string
  purpose: string
  duration: string
}

export type CookieCategory = {
  id: CookieCategoryId
  title: string
  description: string
  /** Always-on categories cannot be disabled. */
  required: boolean
  examples: CookieExample[]
}

/**
 * Categories mirror the well-known cookie-consent classification: one
 * strictly-necessary bucket that keeps the product working, and three optional
 * buckets that are off until the visitor opts in.
 */
export const COOKIE_CATEGORIES: CookieCategory[] = [
  {
    id: 'necessary',
    title: 'Strictly Necessary Cookies',
    description:
      'Required to sign you in and keep the product secure. These cannot be turned off because the service cannot function without them.',
    required: true,
    examples: [
      {
        name: 'auth_session',
        purpose: 'Keeps you signed in and refreshes your access token',
        duration: 'Session',
      },
      {
        name: 'get1agent-cookie-consent',
        purpose: 'Remembers the cookie choices you make here',
        duration: '12 months',
      },
      {
        name: 'theme',
        purpose: 'Prevents a flash of the wrong colour theme on load',
        duration: '12 months',
      },
    ],
  },
  {
    id: 'performance',
    title: 'Performance Cookies',
    description:
      'Help us understand how the product is used so we can make it faster and more reliable. All data is aggregated and never used to identify you.',
    required: false,
    examples: [
      {
        name: 'g1a_analytics',
        purpose: 'Anonymous page and feature usage statistics',
        duration: '12 months',
      },
    ],
  },
  {
    id: 'functional',
    title: 'Functional Cookies',
    description:
      'Remember the preferences you set, such as your sidebar state, recent views and language, so the workspace feels like yours on return visits.',
    required: false,
    examples: [
      {
        name: 'sidebar-closed-sections',
        purpose: 'Keeps collapsed sidebar sections collapsed',
        duration: '12 months',
      },
      {
        name: 'get1agent-pg',
        purpose: 'Remembers Playground editor preferences',
        duration: '12 months',
      },
    ],
  },
  {
    id: 'targeting',
    title: 'Targeting Cookies',
    description:
      'Would be used to show you relevant content on other sites. We do not sell your data and do not enable these unless you ask us to.',
    required: false,
    examples: [
      {
        name: 'g1a_ads',
        purpose: 'Measures campaigns and limits repeated ads',
        duration: '90 days',
      },
    ],
  },
]

export const CONSENT_STORAGE_KEY = 'get1agent-cookie-consent'
export const CONSENT_VERSION = 1
export const CONSENT_EVENT = 'get1agent:consent'

export type ConsentRecord = {
  version: number
  updatedAt: string
  preferences: CookiePreference
}

/** Everything off except the always-on necessary bucket. */
export function rejectedPreferences(): CookiePreference {
  return {
    necessary: true,
    performance: false,
    functional: false,
    targeting: false,
  }
}

/** Everything on. */
export function acceptedPreferences(): CookiePreference {
  return {
    necessary: true,
    performance: true,
    functional: true,
    targeting: true,
  }
}

function coercePreferences(value: unknown): CookiePreference {
  const source =
    value && typeof value === 'object'
      ? (value as Partial<Record<CookieCategoryId, unknown>>)
      : {}
  const base = rejectedPreferences()
  return {
    necessary: true,
    performance: Boolean(source.performance) || base.performance,
    functional: Boolean(source.functional) || base.functional,
    targeting: Boolean(source.targeting) || base.targeting,
  }
}

export function readConsent(): ConsentRecord | null {
  try {
    const raw = localStorage.getItem(CONSENT_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ConsentRecord> | null
    if (!parsed || typeof parsed !== 'object') return null
    return {
      version: typeof parsed.version === 'number' ? parsed.version : CONSENT_VERSION,
      updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : '',
      preferences: coercePreferences(parsed.preferences),
    }
  } catch {
    return null
  }
}

function notify(record: ConsentRecord | null) {
  try {
    window.dispatchEvent(
      new CustomEvent<ConsentRecord | null>(CONSENT_EVENT, { detail: record }),
    )
  } catch {
    /* ignore */
  }
}

/** Persist a choice and broadcast it to listeners. */
export function writeConsent(preferences: CookiePreference): ConsentRecord {
  const record: ConsentRecord = {
    version: CONSENT_VERSION,
    updatedAt: new Date().toISOString(),
    preferences: coercePreferences(preferences),
  }
  try {
    localStorage.setItem(CONSENT_STORAGE_KEY, JSON.stringify(record))
  } catch {
    /* storage may be unavailable; the in-memory state still applies */
  }
  applyPreferencesToDocument(record.preferences)
  notify(record)
  return record
}

/** Forget the stored choice (used by tests / a full reset). */
export function clearConsent(): void {
  try {
    localStorage.removeItem(CONSENT_STORAGE_KEY)
  } catch {
    /* ignore */
  }
  applyPreferencesToDocument(rejectedPreferences())
  notify(null)
}

export function hasConsentDecision(): boolean {
  return readConsent() !== null
}

/**
 * True when a category is currently allowed. Strictly Necessary is always
 * allowed; everything else requires an explicit opt-in.
 */
export function isCategoryAllowed(id: CookieCategoryId): boolean {
  if (id === 'necessary') return true
  const record = readConsent()
  return Boolean(record?.preferences[id])
}

/**
 * Reflect the active consent on <html> so plain CSS / non-React scripts can
 * react without reading localStorage themselves.
 */
export function applyPreferencesToDocument(preferences: CookiePreference): void {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  root.dataset.consentPerformance = String(preferences.performance)
  root.dataset.consentFunctional = String(preferences.functional)
  root.dataset.consentTargeting = String(preferences.targeting)
}

export function subscribeConsent(
  listener: (record: ConsentRecord | null) => void,
): () => void {
  const onEvent = (event: Event) => {
    listener((event as CustomEvent<ConsentRecord | null>).detail ?? null)
  }
  const onStorage = (event: StorageEvent) => {
    if (event.key === CONSENT_STORAGE_KEY) listener(readConsent())
  }
  window.addEventListener(CONSENT_EVENT, onEvent)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(CONSENT_EVENT, onEvent)
    window.removeEventListener('storage', onStorage)
  }
}

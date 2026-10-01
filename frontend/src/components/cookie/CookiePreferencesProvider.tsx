import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  acceptedPreferences,
  applyPreferencesToDocument,
  readConsent,
  rejectedPreferences,
  subscribeConsent,
  writeConsent,
  type CookiePreference,
} from '../../lib/cookies'
import { CookieConsentBanner } from './CookieConsentBanner'
import { CookiePreferencesDialog } from './CookiePreferencesDialog'

type CookiePreferencesContextValue = {
  preferences: CookiePreference
  /** Whether the visitor has made an explicit choice yet. */
  decided: boolean
  open: boolean
  openPreferences: () => void
  closePreferences: () => void
  save: (preferences: CookiePreference) => void
  acceptAll: () => void
  rejectAll: () => void
}

const CookiePreferencesContext =
  createContext<CookiePreferencesContextValue | null>(null)

export function CookiePreferencesProvider({ children }: { children: ReactNode }) {
  const [preferences, setPreferences] = useState<CookiePreference>(
    () => readConsent()?.preferences ?? rejectedPreferences(),
  )
  const [decided, setDecided] = useState(() => readConsent() !== null)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    applyPreferencesToDocument(preferences)
  }, [preferences])

  // Keep multiple tabs in sync and reflect changes made elsewhere.
  useEffect(
    () =>
      subscribeConsent((record) => {
        if (record) {
          setPreferences(record.preferences)
          setDecided(true)
        } else {
          setPreferences(rejectedPreferences())
          setDecided(false)
        }
      }),
    [],
  )

  const save = useCallback((next: CookiePreference) => {
    const record = writeConsent(next)
    setPreferences(record.preferences)
    setDecided(true)
    setOpen(false)
  }, [])

  const acceptAll = useCallback(() => save(acceptedPreferences()), [save])
  const rejectAll = useCallback(() => save(rejectedPreferences()), [save])
  const openPreferences = useCallback(() => setOpen(true), [])
  const closePreferences = useCallback(() => setOpen(false), [])

  const value = useMemo(
    () => ({
      preferences,
      decided,
      open,
      openPreferences,
      closePreferences,
      save,
      acceptAll,
      rejectAll,
    }),
    [preferences, decided, open, openPreferences, closePreferences, save, acceptAll, rejectAll],
  )

  return (
    <CookiePreferencesContext.Provider value={value}>
      {children}
      <CookieConsentBanner />
      <CookiePreferencesDialog />
    </CookiePreferencesContext.Provider>
  )
}

export function useCookiePreferences(): CookiePreferencesContextValue {
  const context = useContext(CookiePreferencesContext)
  if (!context) {
    throw new Error(
      'useCookiePreferences must be used within CookiePreferencesProvider',
    )
  }
  return context
}

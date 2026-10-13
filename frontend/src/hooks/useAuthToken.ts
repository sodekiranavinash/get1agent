import { useEffect, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'

/**
 * The signed-in user's access token, refreshed for a streaming chat.
 *
 * AI Assistant streams over a WebSocket whose first message carries the token, so the
 * token must be a *current* string at send time rather than a stable callback.
 * Fetching it once per mount and refreshing shortly before a typical Auth0
 * expiry keeps the send path synchronous without handing the widget a stale
 * credential.
 */
const REFRESH_MARGIN_MS = 5 * 60 * 1000

export function useAuthToken(): string | undefined {
  const { isAuthenticated, getAccessTokenSilently } = useAuth0()
  const [token, setToken] = useState<string | undefined>(undefined)

  useEffect(() => {
    if (!isAuthenticated) {
      setToken(undefined)
      return
    }
    let cancelled = false
    let timer: number | undefined

    const load = async () => {
      try {
        const next = await getAccessTokenSilently()
        if (!cancelled) setToken(next)
        // Refresh a little before expiry so a long dialog keeps working.
        timer = window.setTimeout(load, 50 * 60 * 1000 - REFRESH_MARGIN_MS)
      } catch {
        if (!cancelled) setToken(undefined)
      }
    }

    void load()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [isAuthenticated, getAccessTokenSilently])

  return token
}

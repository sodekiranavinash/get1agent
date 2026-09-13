/**
 * Active view ("user" vs "admin") persistence + reset signalling.
 *
 * The selected view is stored in localStorage so page reloads keep it, but a
 * fresh Auth0 login clears it (the user picks again). `clearStoredView`
 * notifies the `ViewProvider` so in-memory state resets too.
 */

export type AppView = 'user' | 'admin'

export const ACTIVE_VIEW_KEY = 'get1agent-active-view'

const listeners = new Set<() => void>()

export function readStoredView(): AppView | null {
  try {
    const value = localStorage.getItem(ACTIVE_VIEW_KEY)
    return value === 'user' || value === 'admin' ? value : null
  } catch {
    return null
  }
}

export function writeStoredView(view: AppView): void {
  try {
    localStorage.setItem(ACTIVE_VIEW_KEY, view)
  } catch {
    /* ignore */
  }
}

export function clearStoredView(): void {
  try {
    localStorage.removeItem(ACTIVE_VIEW_KEY)
  } catch {
    /* ignore */
  }
  listeners.forEach((listener) => listener())
}

export function subscribeViewReset(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

/** The view the API client should send; defaults to user. */
export function readActiveView(): AppView {
  return readStoredView() ?? 'user'
}

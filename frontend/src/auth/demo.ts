/**
 * Read-only "View" (demo) mode.
 *
 * A visitor can browse the product UI without an Auth0 account. In this mode
 * the API client never reaches the network: reads return canned demo data and
 * every write is rejected client-side. The real API is JWT-protected anyway, so
 * nothing can be changed even if the UI were bypassed.
 */

export const DEMO_MODE_KEY = 'get1agent-demo'

const listeners = new Set<() => void>()

export function isDemoMode(): boolean {
  try {
    return localStorage.getItem(DEMO_MODE_KEY) === '1'
  } catch {
    return false
  }
}

export function setDemoMode(on: boolean): void {
  try {
    if (on) localStorage.setItem(DEMO_MODE_KEY, '1')
    else localStorage.removeItem(DEMO_MODE_KEY)
  } catch {
    /* ignore */
  }
  listeners.forEach((listener) => listener())
}

export function enterDemoMode(): void {
  setDemoMode(true)
}

export function exitDemoMode(): void {
  setDemoMode(false)
}

export function subscribeDemo(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

import { useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Outlet } from 'react-router-dom'
import { AuthStatusScreen } from './AuthStatusScreen'
import { enterDemoMode } from './demo'
import { useDemoMode } from './useDemoMode'

/**
 * Where a signed-out visitor lands when a link points into the app.
 *
 * `/` **is** the sign-in page, so bouncing them there was never a page load — the
 * URL changed to the cited page and was replaced by the landing page a frame
 * later. That is the whole of "the link doesn't work": Avi answers a guest with
 * "open [Metrics](/metrics)", the visitor clicks it, sees `/metrics` in the
 * address bar, and is back on the landing page before anything renders. The same
 * happened to any deep link into the app.
 *
 * So a guest deep link now admits the visitor to the **read-only demo** and
 * renders the page they asked for. The demo is a labelled state (`DEMO MODE` in
 * the top bar), every write is refused client-side, `RequireAdmin` sends it to
 * the dashboard rather than the console, and the account menu still signs in and
 * returns to this exact URL. Seeing the page they were promised — even with demo
 * data — beats being replaced by a page they did not ask for.
 *
 * This lives in the guard rather than at the link, because the guard is the only
 * thing that knows a route is protected. A public citation (`/docs#metrics`) is
 * outside `RequireAuth` and never passes through here, so it keeps its plain
 * public chrome instead of being dragged into the demo shell.
 */
function GuestDemoEntry() {
  // Subscribe *and* trigger from the same component, in that order. `useDemoMode`
  // registers its listener in an effect declared before the one below, so the
  // notification from `enterDemoMode` cannot be missed — leaning on
  // `RequireAuth`'s own subscription would depend on mount order, because a
  // child's effects run before its parent's.
  const demo = useDemoMode()

  useEffect(() => {
    if (!demo) enterDemoMode()
  }, [demo])

  if (demo) return <Outlet />

  // The same bare canvas the Auth0-loading branch shows. The page must not mount
  // before the demo flag is on, or it would render against the real API client
  // with no token and paint a wall of 401s.
  return <main className="min-h-screen bg-canvas" />
}

export function RequireAuth() {
  const { isLoading, isAuthenticated, error } = useAuth0()
  const demo = useDemoMode()

  // Read-only demo: allow the shell without an account (no API is called).
  if (demo) {
    return <Outlet />
  }

  if (error) {
    return <AuthStatusScreen tone="error">{error.message}</AuthStatusScreen>
  }

  if (isLoading) {
    // Render a bare canvas while the Auth0 SDK initializes — no loading card.
    // Once auth resolves, the page mounts directly and shows its own data
    // skeleton if the API is slow.
    return <main className="min-h-screen bg-canvas" />
  }

  if (!isAuthenticated) {
    return <GuestDemoEntry />
  }

  return <Outlet />
}

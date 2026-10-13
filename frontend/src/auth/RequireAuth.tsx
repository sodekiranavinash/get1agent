import { useAuth0 } from '@auth0/auth0-react'
import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { AUTH_PATHS } from './authUrls'
import { AuthStatusScreen } from './AuthStatusScreen'
import { useDemoMode } from './useDemoMode'

export function RequireAuth() {
  const { isLoading, isAuthenticated, error } = useAuth0()
  const demo = useDemoMode()
  const location = useLocation()

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
    // `/` is the sign-in page, so this is not a page load — but the destination
    // used to be thrown away: a source citation (or any deep link) into the app
    // showed its URL and was replaced by the landing page a frame later, with no
    // way to get where you were going. Carry it instead, and let the sign-in
    // button hand it to Auth0 as `returnTo`.
    const target = `${location.pathname}${location.search}${location.hash}`
    return (
      <Navigate
        to={AUTH_PATHS.login}
        replace
        state={target && target !== '/' ? { returnTo: target } : undefined}
      />
    )
  }

  return <Outlet />
}

import { useAuth0 } from '@auth0/auth0-react'
import { Navigate, Outlet } from 'react-router-dom'
import { AUTH_PATHS } from './authUrls'
import { AuthStatusScreen } from './AuthStatusScreen'

export function RequireAuth() {
  const { isLoading, isAuthenticated, error } = useAuth0()

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
    return <Navigate to={AUTH_PATHS.login} replace />
  }

  return <Outlet />
}

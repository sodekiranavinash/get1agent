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
    return <AuthStatusScreen>Loading…</AuthStatusScreen>
  }

  if (!isAuthenticated) {
    return <Navigate to={AUTH_PATHS.login} replace />
  }

  return <Outlet />
}

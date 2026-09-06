import { useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Navigate } from 'react-router-dom'
import { AuthStatusScreen } from '../auth/AuthStatusScreen'
import { AUTH_PATHS, authAbsoluteUrl } from '../auth/authUrls'

export function LogoutPage() {
  const { isLoading, isAuthenticated, logout, error } = useAuth0()

  useEffect(() => {
    if (isLoading || !isAuthenticated) {
      return
    }

    logout({
      logoutParams: { returnTo: authAbsoluteUrl(AUTH_PATHS.logout) },
    })
  }, [isLoading, isAuthenticated, logout])

  if (error) {
    return <AuthStatusScreen tone="error">{error.message}</AuthStatusScreen>
  }

  if (isLoading || isAuthenticated) {
    return <AuthStatusScreen>Signing you out…</AuthStatusScreen>
  }

  return <Navigate to={AUTH_PATHS.login} replace />
}

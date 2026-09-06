import { useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Navigate } from 'react-router-dom'
import { AuthStatusScreen } from '../auth/AuthStatusScreen'

export function LoginPage() {
  const { isLoading, isAuthenticated, loginWithRedirect, error } = useAuth0()

  useEffect(() => {
    if (isLoading || isAuthenticated) {
      return
    }

    loginWithRedirect({ appState: { returnTo: '/' } })
  }, [isLoading, isAuthenticated, loginWithRedirect])

  if (error) {
    return <AuthStatusScreen tone="error">{error.message}</AuthStatusScreen>
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return <AuthStatusScreen>Redirecting to sign in…</AuthStatusScreen>
}

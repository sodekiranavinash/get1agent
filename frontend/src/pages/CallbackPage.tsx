import { useAuth0 } from '@auth0/auth0-react'
import { AuthStatusScreen } from '../auth/AuthStatusScreen'

export function CallbackPage() {
  const { error } = useAuth0()

  if (error) {
    return <AuthStatusScreen tone="error">{error.message}</AuthStatusScreen>
  }

  return <AuthStatusScreen>Signing you in…</AuthStatusScreen>
}

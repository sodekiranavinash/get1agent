import { useAuth0 } from '@auth0/auth0-react'
import { AuthStatusScreen } from '../auth/AuthStatusScreen'

const AUTH_ERROR_MESSAGES: Record<string, string> = {
  access_denied: 'This app is private for now. Ask the owner to add your email.',
}

export function CallbackPage() {
  const { error } = useAuth0()

  if (error) {
    const code = (error as { error?: string }).error
    const message = (code && AUTH_ERROR_MESSAGES[code]) || error.message
    return <AuthStatusScreen tone="error">{message}</AuthStatusScreen>
  }

  return <AuthStatusScreen>Signing you in…</AuthStatusScreen>
}

import { useAuth0 } from '@auth0/auth0-react'
import { Navigate, useNavigate } from 'react-router-dom'
import { ChevronRight, Eye, Loader2, ShieldCheck } from 'lucide-react'
import { AuthStatusScreen } from '../auth/AuthStatusScreen'
import { enterDemoMode, exitDemoMode } from '../auth/demo'
import { googleLoginOptions } from '../auth/login'
import { GoogleIcon } from '../components/ui/GoogleIcon'
import { useTheme } from '../theme/ThemeProvider'

/**
 * Entry screen: sign in, or explore the product read-only without an account.
 * There is no silent redirect — the visitor chooses.
 */
export function LoginPage() {
  const { isLoading, isAuthenticated, loginWithRedirect, error } = useAuth0()
  const navigate = useNavigate()
  const { theme } = useTheme()
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'

  if (error) {
    return <AuthStatusScreen tone="error">{error.message}</AuthStatusScreen>
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  const signIn = () => {
    exitDemoMode()
    void loginWithRedirect(googleLoginOptions('/'))
  }

  const viewDemo = () => {
    enterDemoMode()
    navigate('/dashboard', { replace: true })
  }

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden bg-canvas px-6 pt-12 pb-20 text-foreground">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute -top-44 left-1/2 h-[440px] w-[760px] -translate-x-1/2 rounded-full bg-accent-soft/50 blur-3xl"
      />

      <div className="relative w-full max-w-lg">
        <div className="mb-4 flex justify-center">
          <img
            src={logoSrc}
            alt="OneAgent"
            className="h-44 w-auto max-w-full object-contain sm:h-56"
          />
        </div>

        <h1 className="bg-gradient-to-b from-foreground to-muted bg-clip-text text-center text-[18px] leading-snug font-semibold tracking-tight whitespace-nowrap text-transparent sm:text-[24px]">
          Build and run AI agents on your own data.
        </h1>

        <div className="mx-auto mt-6 w-full max-w-md overflow-hidden rounded-xl border border-border bg-surface shadow-panel">
          <button
            type="button"
            onClick={signIn}
            disabled={isLoading}
            className="flex w-full items-center gap-4 px-5 py-5 text-left transition-colors hover:bg-raised/50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-border bg-canvas">
              {isLoading ? (
                <Loader2 className="size-5 animate-spin text-accent" />
              ) : (
                <GoogleIcon className="size-5" />
              )}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[15px] font-semibold text-foreground">
                Continue with Google
              </span>
              <span className="block text-[12.5px] text-subtle">No password needed</span>
            </span>
            <ChevronRight className="size-5 shrink-0 text-subtle" />
          </button>

          <div className="border-t border-border">
            <button
              type="button"
              onClick={viewDemo}
              className="flex w-full items-center gap-4 px-5 py-5 text-left transition-colors hover:bg-raised/50"
            >
              <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-border bg-raised text-accent">
                <Eye className="size-5" strokeWidth={1.75} />
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-[15px] font-semibold text-foreground">
                  View demo
                  <span className="ml-2 align-middle text-[11px] font-medium tracking-wide text-subtle uppercase">
                    Read-only
                  </span>
                </span>
              </span>
              <ChevronRight className="size-5 shrink-0 text-subtle" />
            </button>
          </div>
        </div>

        <p className="mt-4 flex items-center justify-center gap-1.5 text-[11px] text-subtle">
          <ShieldCheck className="size-3.5 shrink-0 text-accent" />
          The demo is read-only until you sign in.
        </p>
      </div>
    </div>
  )
}

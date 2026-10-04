import { useAuth0 } from '@auth0/auth0-react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { BookText, Eye, Loader2 } from 'lucide-react'
import { enterDemoMode, exitDemoMode } from '../../auth/demo'
import { useDemoMode } from '../../auth/useDemoMode'
import { googleLoginOptions } from '../../auth/login'
import { Button } from '../ui/Button'
import { GithubIcon } from '../ui/GithubIcon'
import { GoogleIcon } from '../ui/GoogleIcon'
import { ThemeSwitch } from '../layout/ThemeSwitch'
import { originState } from '../layout/returnTarget'
import { useTheme } from '../../theme/ThemeProvider'

const GITHUB_URL = 'https://github.com/sodekiranavinash/get1agent'

/**
 * Fixed public navbar shared by the landing and architecture pages: logo,
 * theme switch, icon-only Architecture / Docs / GitHub links, then the two ways
 * in (Demo and Google sign-in). Icon links carry the public origin so the pages
 * they open offer a precise "Return to home" and stay in the public shell.
 */
export function LandingNav({ wide = false }: { wide?: boolean } = {}) {
  const { isLoading, isAuthenticated, loginWithRedirect } = useAuth0()
  const demo = useDemoMode()
  const navigate = useNavigate()
  const location = useLocation()
  const { theme } = useTheme()
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'
  const toOrigin = originState(location.pathname, { isPublic: true })

  const iconLink =
    'hidden size-9 shrink-0 items-center justify-center rounded-md border border-border-strong bg-transparent text-foreground transition-colors hover:border-accent/50 hover:bg-raised hover:text-accent focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none sm:inline-flex'

  const signIn = () => {
    exitDemoMode()
    void loginWithRedirect(googleLoginOptions('/dashboard'))
  }

  const viewDemo = () => {
    enterDemoMode()
    navigate('/dashboard', { replace: true })
  }

  return (
    <header className="fixed inset-x-0 top-0 z-40 border-b border-border/60 bg-canvas/70 backdrop-blur-xl">
      <div
        className={`mx-auto flex h-[4.5rem] w-full items-center justify-between gap-3 px-4 sm:h-20 sm:px-6 lg:px-8 ${
          wide ? 'max-w-[1800px]' : 'max-w-6xl'
        }`}
      >
        <Link to="/" className="flex shrink-0 items-center" aria-label="OneAgent home">
          <img
            src={logoSrc}
            alt="OneAgent"
            className="h-11 w-auto object-contain sm:h-16"
          />
        </Link>
        <nav className="flex items-center gap-2">
          <ThemeSwitch />
          <Link
            to="/docs"
            state={toOrigin}
            aria-label="Documentation"
            title="Documentation"
            className={iconLink}
          >
            <BookText className="size-[22px]" strokeWidth={1.8} />
          </Link>
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noreferrer"
            aria-label="GitHub"
            title="sodekiranavinash/get1agent"
            className={iconLink}
          >
            <GithubIcon className="size-[22px]" />
          </a>
          {isAuthenticated ? (
            <Button
              size="lg"
              onClick={() => navigate('/dashboard')}
              icon={<Eye className="size-4" />}
            >
              <span className="hidden sm:inline">Open workspace</span>
              <span className="sm:hidden">Open</span>
            </Button>
          ) : (
            <>
              <Button size="lg" onClick={viewDemo}>
                {demo ? 'Open Demo' : 'Demo'}
              </Button>
              <Button
                variant="outline"
                size="lg"
                onClick={signIn}
                disabled={isLoading}
                icon={
                  isLoading ? (
                    <Loader2 className="size-4 animate-spin" />
                  ) : (
                    <GoogleIcon className="size-4" />
                  )
                }
              >
                Sign In
              </Button>
            </>
          )}
        </nav>
      </div>
    </header>
  )
}

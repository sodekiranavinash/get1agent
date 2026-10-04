import { BookText, Eye, LifeBuoy } from 'lucide-react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link, useLocation } from 'react-router-dom'
import { AccountMenu } from './AccountMenu'
import { NotificationsMenu } from './NotificationsMenu'
import { ThemeSwitch } from './ThemeSwitch'
import { CommandPalette } from '../CommandPalette'
import { originState } from './returnTarget'
import { exitDemoMode } from '../../auth/demo'
import { googleLoginOptions } from '../../auth/login'
import { useDemoMode } from '../../auth/useDemoMode'
import { useView } from '../../auth/ViewProvider'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '../ui/tooltip'

type TopBarProps = {
  extraLinks?: { label: string; to: string; section?: string }[]
  /** Where Settings points in the account menu; null hides it (admin). */
  settingsPath?: string | null
}

const iconButton =
  'inline-flex size-9 shrink-0 items-center justify-center rounded-md border border-transparent text-muted transition-colors hover:border-border hover:bg-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none'

/**
 * Prominent "Demo mode" pill shown only in the read-only demo. It replaces the
 * old top banner: it sits left of the theme switch and clicking it exits the
 * demo and starts sign-in.
 */
function DemoModeBadge() {
  const demo = useDemoMode()
  const { loginWithRedirect } = useAuth0()
  if (!demo) return null
  return (
    <button
      type="button"
      title="Read-only demo — sign in to make changes"
      onClick={() => {
        exitDemoMode()
        void loginWithRedirect(googleLoginOptions('/dashboard'))
      }}
      className="mr-1 inline-flex shrink-0 items-center gap-2 rounded-full border border-accent/35 bg-accent-soft/70 px-3.5 py-1.5 text-[12.5px] font-semibold text-accent transition-colors hover:border-accent/60 hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
    >
      <Eye className="size-4 shrink-0" strokeWidth={2} />
      <span className="whitespace-nowrap">Demo mode · read-only</span>
    </button>
  )
}

/** Slim global bar: command palette, theme, docs, support, notifications, account. */
export function TopBar({ extraLinks, settingsPath = '/settings' }: TopBarProps) {
  const { view } = useView()
  const adminView = view === 'admin'
  const supportPath = adminView ? '/admin/support' : '/support'
  const location = useLocation()
  const toOrigin = originState(location.pathname + location.search)

  return (
    <header className="sticky top-0 z-10 flex h-16 shrink-0 items-center justify-between gap-3 border-b border-border bg-canvas/85 px-4 backdrop-blur-md lg:px-6">
      <CommandPalette extraLinks={extraLinks} />

      <div className="flex items-center gap-1.5">
        <DemoModeBadge />
        <ThemeSwitch />

        {/* Docs is an end-user surface, so it is hidden in the admin console. */}
        {adminView ? null : (
          <Tooltip>
            <TooltipTrigger asChild>
              <Link to="/docs" state={toOrigin} className={iconButton} aria-label="Documentation">
                <BookText className="size-[22px]" strokeWidth={1.75} />
              </Link>
            </TooltipTrigger>
            <TooltipContent>Documentation</TooltipContent>
          </Tooltip>
        )}

        <Tooltip>
          <TooltipTrigger asChild>
            <Link to={supportPath} state={toOrigin} className={iconButton} aria-label="Support">
              <LifeBuoy className="size-[22px]" strokeWidth={1.75} />
            </Link>
          </TooltipTrigger>
          <TooltipContent>{adminView ? 'Support inbox' : 'Support'}</TooltipContent>
        </Tooltip>

        {/* Notifications call a user-view route, so they are hidden in the
            admin console (which sends x-active-view: admin). */}
        {adminView ? null : <NotificationsMenu />}

        <span className="mx-0.5 h-5 w-px bg-border" aria-hidden="true" />

        <AccountMenu settingsPath={settingsPath} />
      </div>
    </header>
  )
}

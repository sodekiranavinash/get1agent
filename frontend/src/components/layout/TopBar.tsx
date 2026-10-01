import { Bell, Check, CircleHelp, Eye, LifeBuoy } from 'lucide-react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { AccountMenu } from './AccountMenu'
import { ThemeSwitch } from './ThemeSwitch'
import { CommandPalette } from '../CommandPalette'
import { exitDemoMode } from '../../auth/demo'
import { googleLoginOptions } from '../../auth/login'
import { useDemoMode } from '../../auth/useDemoMode'
import { useView } from '../../auth/ViewProvider'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'
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

const notifications = [
  { title: 'Ingestion finished', detail: 'product-documentation · 12 files', time: '2m' },
  { title: 'Schedule failed', detail: 'Customer Support Flow', time: '1h' },
  { title: 'Credits low', detail: '$12.80 remaining', time: '3h' },
]

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
        void loginWithRedirect(googleLoginOptions('/'))
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
              <Link to="/docs" className={iconButton} aria-label="Documentation">
                <CircleHelp className="size-5" strokeWidth={1.75} />
              </Link>
            </TooltipTrigger>
            <TooltipContent>Documentation</TooltipContent>
          </Tooltip>
        )}

        <Tooltip>
          <TooltipTrigger asChild>
            <Link to={supportPath} className={iconButton} aria-label="Support">
              <LifeBuoy className="size-5" strokeWidth={1.75} />
            </Link>
          </TooltipTrigger>
          <TooltipContent>{adminView ? 'Support inbox' : 'Support'}</TooltipContent>
        </Tooltip>

        <DropdownMenu>
          <Tooltip>
            <TooltipTrigger asChild>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  className={`${iconButton} relative`}
                  aria-label="Notifications"
                >
                  <Bell className="size-5" strokeWidth={1.75} />
                  <span className="absolute top-2 right-2 size-2 rounded-full bg-accent ring-2 ring-canvas" />
                </button>
              </DropdownMenuTrigger>
            </TooltipTrigger>
            <TooltipContent>Notifications</TooltipContent>
          </Tooltip>
          <DropdownMenuContent align="end" className="w-80">
            <DropdownMenuLabel>Notifications</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {notifications.map((item) => (
              <DropdownMenuItem key={item.title} className="items-start gap-2.5 py-2">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-success-soft text-success">
                  <Check className="size-3" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[13px] font-medium text-foreground">
                    {item.title}
                  </span>
                  <span className="block truncate text-xs text-muted">
                    {item.detail}
                  </span>
                </span>
                <span className="shrink-0 text-[11px] text-subtle">{item.time}</span>
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>

        <span className="mx-0.5 h-5 w-px bg-border" aria-hidden="true" />

        <AccountMenu settingsPath={settingsPath} />
      </div>
    </header>
  )
}

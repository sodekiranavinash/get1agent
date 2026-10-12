import type { LucideIcon } from 'lucide-react'
import { BookText, CreditCard, KeyRound, LifeBuoy } from 'lucide-react'
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
type TopBarProps = {
  extraLinks?: { label: string; to: string; section?: string }[]
  /** Where Settings points in the account menu; null hides it (admin). */
  settingsPath?: string | null
}

/**
 * A top-bar destination rendered as icon + label. The label hides below `md` so
 * the bar stays usable on a phone, where the icon alone carries the meaning
 * (with a tooltip and an aria-label).
 */
function NavLinkItem({
  to,
  label,
  icon: Icon,
  state,
}: {
  to: string
  label: string
  icon: LucideIcon
  state?: unknown
}) {
  return (
    <Link
      to={to}
      state={state}
      aria-label={label}
      title={label}
      className="inline-flex h-9 shrink-0 items-center gap-2 rounded-md border border-transparent px-2.5 text-[12.5px] font-medium text-muted transition-colors hover:border-border hover:bg-raised hover:text-foreground focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
    >
      <Icon className="size-[18px] shrink-0" strokeWidth={1.75} />
      <span className="hidden whitespace-nowrap md:inline">{label}</span>
    </Link>
  )
}

/**
 * The "DEMO MODE" tag shown only in the read-only demo. It sits left of the
 * theme switch and clicking it exits the demo and starts sign-in.
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
      className="mr-1 inline-flex shrink-0 items-center rounded-md border border-accent/35 bg-accent-soft/70 px-2.5 py-1 text-[11px] font-semibold tracking-[0.08em] text-accent uppercase transition-colors hover:border-accent/60 hover:bg-accent-soft focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:outline-none"
    >
      Demo mode
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

      <div className="flex min-w-0 items-center gap-1.5">
        <DemoModeBadge />

        {/* Vault + Usage live here (not in the sidebar): account-level surfaces.
            Both are user-view routes, so they are hidden in the admin console. */}
        {adminView ? null : (
          <>
            <NavLinkItem to="/vault" label="Vault" icon={KeyRound} state={toOrigin} />
            <NavLinkItem to="/usage" label="Usage" icon={CreditCard} state={toOrigin} />
          </>
        )}

        {/* Docs is an end-user surface, so it is hidden in the admin console. */}
        {adminView ? null : (
          <NavLinkItem to="/docs" label="Docs" icon={BookText} state={toOrigin} />
        )}
        <NavLinkItem
          to={supportPath}
          label={adminView ? 'Support inbox' : 'Support'}
          icon={LifeBuoy}
          state={toOrigin}
        />

        {/* Notifications call a user-view route, so they are hidden in the
            admin console (which sends x-active-view: admin). */}
        {adminView ? null : <NotificationsMenu />}

        <span className="mx-1 hidden h-5 w-px bg-border sm:block" aria-hidden="true" />

        {/* Theme sits with the account card, as the last two actions. */}
        <ThemeSwitch />
        <AccountMenu settingsPath={settingsPath} />
      </div>
    </header>
  )
}

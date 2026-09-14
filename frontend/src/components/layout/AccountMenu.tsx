import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import {
  ArrowLeftRight,
  ChevronsUpDown,
  LogOut,
  Settings,
} from 'lucide-react'
import { AUTH_PATHS } from '../../auth/authUrls'
import { getUserProfile } from '../../auth/userProfile'
import { useView } from '../../auth/ViewProvider'
import { Avatar, AvatarFallback, AvatarImage } from '../ui/avatar'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '../ui/dropdown-menu'

type AccountMenuProps = {
  /** Where the Settings link points; pass null to hide it (admin console). */
  settingsPath?: string | null
}

/** Account card shown at the right of the top bar. */
export function AccountMenu({ settingsPath = '/settings' }: AccountMenuProps) {
  const { user } = useAuth0()
  const { view, canSwitch, chooseView } = useView()
  const profile = getUserProfile(user)
  const displayName = [profile.firstName, profile.lastName].filter(Boolean).join(' ')

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className="flex h-9 items-center gap-2 rounded-md border border-border bg-raised/40 px-1.5 pr-2 text-left transition-colors hover:border-border-strong hover:bg-raised"
        >
          <Avatar className="size-6">
            {profile.picture ? (
              <AvatarImage src={profile.picture} alt={displayName || 'Account'} />
            ) : null}
            <AvatarFallback>{profile.initial}</AvatarFallback>
          </Avatar>
          <span className="hidden max-w-[9rem] truncate text-[13px] font-medium text-foreground lg:block">
            {displayName || profile.email || 'Account'}
          </span>
          <ChevronsUpDown className="size-3.5 shrink-0 text-subtle" />
        </button>
      </DropdownMenuTrigger>

      <DropdownMenuContent side="bottom" align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col gap-0.5 py-1.5 normal-case tracking-normal">
          <span className="text-[13px] font-medium text-foreground">
            {displayName || 'Account'}
          </span>
          {profile.email ? (
            <span className="text-[11px] font-normal text-subtle">{profile.email}</span>
          ) : null}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {canSwitch ? (
          <>
            <DropdownMenuItem
              onSelect={() => chooseView(view === 'admin' ? 'user' : 'admin')}
            >
              <ArrowLeftRight className="size-3.5" />
              Switch to {view === 'admin' ? 'User' : 'Admin'} view
            </DropdownMenuItem>
            <DropdownMenuSeparator />
          </>
        ) : null}

        {settingsPath ? (
          <DropdownMenuItem asChild>
            <Link to={settingsPath}>
              <Settings className="size-3.5" />
              Settings
            </Link>
          </DropdownMenuItem>
        ) : null}
        <DropdownMenuItem asChild variant="destructive">
          <Link to={AUTH_PATHS.logout}>
            <LogOut className="size-3.5" />
            Log out
          </Link>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

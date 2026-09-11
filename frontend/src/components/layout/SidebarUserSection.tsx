import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { LogOut, Settings } from 'lucide-react'
import { AUTH_PATHS } from '../../auth/authUrls'
import { getUserProfile } from '../../auth/userProfile'
import { UserAvatar } from '../UserAvatar'

type SidebarUserSectionProps = {
  collapsed: boolean
}

export function SidebarUserSection({ collapsed }: SidebarUserSectionProps) {
  const { user } = useAuth0()
  const profile = getUserProfile(user)
  const displayName = [profile.firstName, profile.lastName].filter(Boolean).join(' ')

  if (collapsed) {
    return (
      <div className="flex w-full flex-col items-center gap-2">
        <UserAvatar
          picture={profile.picture}
          initial={profile.initial}
          alt={displayName || 'Account'}
          className="h-9 w-9"
        />
        <Link
          to="/settings"
          title="Settings"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted no-underline transition-colors hover:bg-raised hover:text-foreground"
        >
          <Settings className="h-4 w-4" strokeWidth={1.75} />
          <span className="sr-only">Settings</span>
        </Link>
        <Link
          to={AUTH_PATHS.logout}
          title="Log out"
          className="inline-flex h-8 w-8 items-center justify-center rounded-lg text-muted no-underline transition-colors hover:bg-raised hover:text-accent"
        >
          <LogOut className="h-4 w-4" strokeWidth={1.75} />
          <span className="sr-only">Log out</span>
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 rounded-xl border border-border/80 bg-raised/50 px-3 py-2.5">
        <UserAvatar
          picture={profile.picture}
          initial={profile.initial}
          alt={displayName || 'Account'}
          className="h-10 w-10"
        />
        <div className="min-w-0 flex-1">
          {displayName ? (
            <p className="truncate text-sm font-semibold text-foreground">{displayName}</p>
          ) : null}
          {profile.email ? (
            <p className="mt-0.5 truncate text-xs text-muted">{profile.email}</p>
          ) : null}
        </div>
      </div>

      <div className="space-y-0.5">
        <Link
          to="/settings"
          className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium text-muted no-underline transition-colors hover:bg-raised hover:text-foreground"
        >
          <Settings className="h-4 w-4 shrink-0" strokeWidth={1.75} />
          Settings
        </Link>
        <Link
          to={AUTH_PATHS.logout}
          className="flex items-center gap-2.5 rounded-xl px-3 py-2 text-sm font-medium text-muted no-underline transition-colors hover:bg-accent-soft hover:text-accent"
        >
          <LogOut className="h-4 w-4 shrink-0" strokeWidth={1.75} />
          Log out
        </Link>
      </div>
    </div>
  )
}

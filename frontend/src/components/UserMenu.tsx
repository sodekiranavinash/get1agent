import { useEffect, useId, useRef, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { AUTH_PATHS } from '../auth/authUrls'
import { getUserProfile } from '../auth/userProfile'
import { UserAvatar } from './UserAvatar'

export function UserMenu() {
  const { user } = useAuth0()
  const profile = getUserProfile(user)
  const [open, setOpen] = useState(false)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuId = useId()
  const displayName = [profile.firstName, profile.lastName]
    .filter(Boolean)
    .join(' ')

  useEffect(() => {
    if (!open) {
      return
    }

    const onPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setOpen(false)
      }
    }

    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)

    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  return (
    <div ref={menuRef} className="relative flex items-center">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-9 w-9 items-center justify-center rounded-full outline-offset-2 transition-opacity hover:opacity-90"
      >
        <UserAvatar
          picture={profile.picture}
          initial={profile.initial}
          alt={displayName || 'Account'}
        />
      </button>

      {open ? (
        <div
          id={menuId}
          role="menu"
          className="absolute right-0 top-[calc(100%+0.5rem)] z-40 w-64 origin-top-right rounded-2xl border border-border bg-raised p-2 shadow-xl"
        >
          <div className="px-3 py-2.5">
            {displayName ? (
              <p className="truncate text-sm font-medium text-foreground">
                {displayName}
              </p>
            ) : null}
            {profile.email ? (
              <p className="mt-0.5 truncate text-xs text-muted">
                {profile.email}
              </p>
            ) : null}
          </div>
          <div className="my-1 h-px bg-border" />
          <Link
            role="menuitem"
            to={AUTH_PATHS.logout}
            className="flex w-full items-center rounded-xl px-3 py-2 text-sm text-foreground no-underline transition-colors hover:bg-canvas"
            onClick={() => setOpen(false)}
          >
            Log out
          </Link>
        </div>
      ) : null}
    </div>
  )
}

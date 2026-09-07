import { useEffect, useId, useRef, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { LogOut, Settings } from 'lucide-react'
import { AUTH_PATHS } from '../auth/authUrls'
import { getUserProfile } from '../auth/userProfile'
import { NavControlButton } from './NavControlButton'
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
    if (!open) return

    const onPointerDown = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) {
        setOpen(false)
      }
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
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
      <NavControlButton
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        active={open}
        onClick={() => setOpen((current) => !current)}
        className="h-9 w-9 p-0.5"
      >
        <UserAvatar
          picture={profile.picture}
          initial={profile.initial}
          alt={displayName || 'Account'}
          className="h-full w-full"
        />
      </NavControlButton>

      <AnimatePresence>
        {open ? (
          <motion.div
            id={menuId}
            role="menu"
            initial={{ opacity: 0, scale: 0.95, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-[calc(100%+0.5rem)] z-40 w-64 origin-top-right overflow-hidden rounded-2xl border border-border bg-surface shadow-panel"
          >
            <div className="border-b border-border bg-raised/80 px-4 py-3">
              {displayName ? (
                <p className="truncate text-sm font-semibold text-foreground">
                  {displayName}
                </p>
              ) : null}
              {profile.email ? (
                <p className="mt-0.5 truncate text-xs text-muted">
                  {profile.email}
                </p>
              ) : null}
            </div>

            <div className="p-1.5">
              <Link
                role="menuitem"
                to="/settings"
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium text-foreground no-underline transition-colors hover:bg-accent-soft hover:text-accent"
                onClick={() => setOpen(false)}
              >
                <Settings className="h-4 w-4" strokeWidth={1.75} />
                Settings
              </Link>
              <Link
                role="menuitem"
                to={AUTH_PATHS.logout}
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-sm font-medium text-foreground no-underline transition-colors hover:bg-accent-soft hover:text-accent"
                onClick={() => setOpen(false)}
              >
                <LogOut className="h-4 w-4" strokeWidth={1.75} />
                Log out
              </Link>
            </div>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

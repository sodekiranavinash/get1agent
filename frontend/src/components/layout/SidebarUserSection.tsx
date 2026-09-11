import { useEffect, useRef, useState } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Check, ChevronRight, LogOut, Moon, Settings, Sun } from 'lucide-react'
import { AUTH_PATHS } from '../../auth/authUrls'
import { getUserProfile } from '../../auth/userProfile'
import { useTheme, type Theme } from '../../theme/ThemeProvider'
import { UserAvatar } from '../UserAvatar'

type SidebarUserSectionProps = {
  collapsed: boolean
}

const themeOptions: { id: Theme; label: string; icon: typeof Sun }[] = [
  { id: 'light', label: 'Light', icon: Sun },
  { id: 'dark', label: 'Dark', icon: Moon },
]

export function SidebarUserSection({ collapsed }: SidebarUserSectionProps) {
  const { user } = useAuth0()
  const { theme, setTheme } = useTheme()
  const profile = getUserProfile(user)
  const displayName = [profile.firstName, profile.lastName].filter(Boolean).join(' ')
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const handlePointerDown = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', handlePointerDown)
    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('mousedown', handlePointerDown)
      document.removeEventListener('keydown', handleKeyDown)
    }
  }, [open])

  return (
    <div ref={containerRef} className="relative w-full">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={collapsed ? displayName || 'Account' : undefined}
        className={
          collapsed
            ? 'flex w-full items-center justify-center rounded-xl py-2 text-muted transition-colors hover:bg-raised hover:text-foreground'
            : 'flex w-full items-center gap-3 rounded-xl border border-border/80 bg-raised/50 px-3 py-2.5 text-left transition-colors hover:bg-raised'
        }
      >
        <UserAvatar
          picture={profile.picture}
          initial={profile.initial}
          alt={displayName || 'Account'}
          className={collapsed ? 'h-9 w-9' : 'h-10 w-10'}
        />
        {!collapsed ? (
          <>
            <span className="min-w-0 flex-1">
              {displayName ? (
                <span className="block truncate text-sm font-semibold text-foreground">
                  {displayName}
                </span>
              ) : null}
              {profile.email ? (
                <span className="mt-0.5 block truncate text-xs text-muted">
                  {profile.email}
                </span>
              ) : null}
            </span>
            <ChevronRight
              className={`h-4 w-4 shrink-0 text-subtle transition-transform duration-200 ${
                open ? 'rotate-180' : ''
              }`}
              strokeWidth={1.75}
            />
          </>
        ) : null}
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            role="menu"
            initial={{ opacity: 0, x: -8, scale: 0.98 }}
            animate={{ opacity: 1, x: 0, scale: 1 }}
            exit={{ opacity: 0, x: -8, scale: 0.98 }}
            transition={{ duration: 0.16, ease: 'easeOut' }}
            className="absolute bottom-0 left-full z-50 ml-4 w-56 origin-bottom-left overflow-hidden rounded-xl border border-border-strong bg-surface p-1.5 shadow-panel"
          >
            <p className="px-2.5 py-1.5 text-[10px] font-bold tracking-[0.16em] text-subtle uppercase">
              Appearance
            </p>
            {themeOptions.map((option) => {
              const Icon = option.icon
              const isActive = theme === option.id
              return (
                <button
                  key={option.id}
                  type="button"
                  role="menuitemradio"
                  aria-checked={isActive}
                  onClick={() => setTheme(option.id)}
                  className="flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-muted transition-colors hover:bg-raised hover:text-foreground"
                >
                  <Icon className="h-4 w-4 shrink-0" strokeWidth={1.75} />
                  <span className="flex-1 text-left">{option.label}</span>
                  {isActive ? (
                    <Check className="h-3.5 w-3.5 text-accent" strokeWidth={2.25} />
                  ) : null}
                </button>
              )
            })}

            <div className="my-1 h-px bg-border" />

            <Link
              to="/settings"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-muted no-underline transition-colors hover:bg-raised hover:text-foreground"
            >
              <Settings className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              Settings
            </Link>
            <Link
              to={AUTH_PATHS.logout}
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium text-muted no-underline transition-colors hover:bg-accent-soft hover:text-accent"
            >
              <LogOut className="h-4 w-4 shrink-0" strokeWidth={1.75} />
              Log out
            </Link>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  )
}

import { motion } from 'framer-motion'
import { Moon, Sun } from 'lucide-react'
import { useTheme, type Theme } from '../../theme/ThemeProvider'

type SidebarThemeSwitcherProps = {
  collapsed: boolean
}

const themes: { id: Theme; icon: typeof Sun }[] = [
  { id: 'light', icon: Sun },
  { id: 'dark', icon: Moon },
]

export function SidebarThemeSwitcher({ collapsed }: SidebarThemeSwitcherProps) {
  const { theme, setTheme, toggleTheme } = useTheme()
  const isDark = theme === 'dark'

  if (collapsed) {
    return (
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={isDark ? 'Switch to light mode' : 'Switch to dark mode'}
        title={isDark ? 'Light mode' : 'Dark mode'}
        className="flex w-full items-center justify-center rounded-xl py-2.5 text-muted transition-colors hover:bg-raised hover:text-foreground"
      >
        {isDark ? (
          <Sun className="h-[18px] w-[18px]" strokeWidth={1.75} />
        ) : (
          <Moon className="h-[18px] w-[18px]" strokeWidth={1.75} />
        )}
      </button>
    )
  }

  return (
    <div
      className="relative flex h-8 rounded-lg border border-border bg-raised/60 p-0.5"
      role="group"
      aria-label="Theme"
    >
      {themes.map((option) => {
        const Icon = option.icon
        const isActive = theme === option.id

        return (
          <button
            key={option.id}
            type="button"
            onClick={() => setTheme(option.id)}
            aria-pressed={isActive}
            aria-label={option.id === 'light' ? 'Light mode' : 'Dark mode'}
            title={option.id === 'light' ? 'Light mode' : 'Dark mode'}
            className={`relative z-10 flex flex-1 items-center justify-center rounded-md transition-colors duration-200 ${
              isActive ? 'text-accent' : 'text-muted hover:text-foreground'
            }`}
          >
            <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
          </button>
        )
      })}
      <motion.span
        layoutId="sidebar-theme-pill"
        className="absolute inset-y-0.5 w-[calc(50%-2px)] rounded-md bg-accent-soft"
        style={{ left: theme === 'light' ? '2px' : 'calc(50% + 0px)' }}
        transition={{ type: 'spring', stiffness: 420, damping: 32 }}
        aria-hidden="true"
      />
    </div>
  )
}

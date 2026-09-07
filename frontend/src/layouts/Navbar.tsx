import { Link } from 'react-router-dom'
import { Search } from 'lucide-react'
import { UserMenu } from '../components/UserMenu'
import { ThemeToggle } from '../theme/ThemeToggle'
import { useTheme } from '../theme/ThemeProvider'
import { useSidebar } from '../components/layout/SidebarProvider'

export function Navbar() {
  const { theme } = useTheme()
  const { collapsed } = useSidebar()
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'

  return (
    <div className="flex h-full w-full items-center justify-between gap-4 px-4 lg:px-6">
      <div className="flex min-w-0 items-center gap-4">
        <Link
          to="/dashboard"
          className="flex shrink-0 items-center rounded-xl bg-accent-soft/40 px-3 py-1.5 transition-colors hover:bg-accent-soft"
        >
          <img
            src={logoSrc}
            alt="OneAgent"
            className={`object-contain object-center transition-all duration-300 ${
              collapsed ? 'h-8 w-28' : 'h-9 w-32'
            }`}
          />
        </Link>

        <div className="hidden md:flex">
          <label className="relative">
            <span className="sr-only">Search workspace</span>
            <Search
              className="pointer-events-none absolute top-1/2 left-3 h-4 w-4 -translate-y-1/2 text-subtle"
              strokeWidth={1.75}
            />
            <input
              type="search"
              placeholder="Search agents, workflows…"
              disabled
              className="h-9 w-64 rounded-xl border border-border bg-raised pl-9 pr-4 text-sm text-foreground placeholder:text-subtle transition-colors focus:border-accent/40 focus:outline-none focus:ring-2 focus:ring-accent/20 lg:w-72"
            />
          </label>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <ThemeToggle />
        <div className="hidden h-6 w-px bg-border sm:block" aria-hidden="true" />
        <UserMenu />
      </div>
    </div>
  )
}

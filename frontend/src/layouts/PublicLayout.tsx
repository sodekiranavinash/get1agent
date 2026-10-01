import { Link, Outlet } from 'react-router-dom'
import type { ReactNode } from 'react'
import { useTheme } from '../theme/ThemeProvider'

/**
 * Minimal shell for public pages (legal, docs, status, support) that must be
 * reachable from the footer even when signed out. The fixed `AppFooter` is
 * rendered globally in `App`, so this only provides a small header and the
 * space reserved for that footer.
 */
export function PublicLayout({ children }: { children?: ReactNode }) {
  const { theme } = useTheme()
  const logoSrc = theme === 'light' ? '/white_logo.png' : '/dark_logo.png'

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-foreground">
      <header className="border-b border-border px-6 py-3.5 lg:px-8">
        <Link
          to="/"
          className="mx-auto flex max-w-[1440px] items-center"
          aria-label="OneAgent home"
        >
          <img src={logoSrc} alt="OneAgent" className="h-8 w-auto object-contain" />
        </Link>
      </header>
      <main className="flex min-h-0 flex-1 flex-col pb-16">
        {children ?? <Outlet />}
      </main>
    </div>
  )
}

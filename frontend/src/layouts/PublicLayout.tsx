import { Outlet } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AuroraBackground } from '../components/landing/AuroraBackground'
import { LandingNav } from '../components/landing/LandingNav'
import { AppFooter } from '../components/layout/AppFooter'

/**
 * Minimal public shell for information pages (legal, docs, status, support).
 * It reuses the landing navbar so a visitor keeps the same header they arrived
 * with, and ends with the shared in-flow footer. There is no app sidebar and no
 * demo chrome here — just the page, its "Return to …" link and the footer.
 *
 * `--page-sticky-top` is the shell-level offset any `sticky` child must clear so
 * it is not covered by the **fixed** `LandingNav` (4.5rem / 5rem at `sm`). The
 * app shell scrolls *below* its top bar, so it keeps the 1.5rem default.
 */
export function PublicLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="relative flex min-h-screen flex-col bg-canvas text-foreground">
      <AuroraBackground />
      <LandingNav />
      <main className="relative z-10 flex-1 pt-[4.5rem] pb-16 [--page-sticky-top:6rem] sm:pt-20">
        {children ?? <Outlet />}
      </main>
      <AppFooter />
    </div>
  )
}

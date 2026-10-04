import { Outlet } from 'react-router-dom'
import type { ReactNode } from 'react'
import { AuroraBackground } from '../components/landing/AuroraBackground'
import { LandingNav } from '../components/landing/LandingNav'

/**
 * Minimal public shell for information pages (legal, docs, status, support).
 * It reuses the landing navbar so a visitor keeps the same header they arrived
 * with, and reserves space for the fixed footer. There is no app sidebar and no
 * demo chrome here — just the page and its "Return to …" link.
 */
export function PublicLayout({ children }: { children?: ReactNode }) {
  return (
    <div className="relative min-h-screen bg-canvas text-foreground">
      <AuroraBackground />
      <LandingNav />
      <main className="relative z-10 pt-[4.5rem] pb-24 sm:pt-20">
        {children ?? <Outlet />}
      </main>
    </div>
  )
}

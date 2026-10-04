import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import { useDemoMode } from '../auth/useDemoMode'
import { useView } from '../auth/ViewProvider'
import { ReturnLink } from '../components/layout/ReturnLink'
import type { OriginState } from '../components/layout/returnTarget'
import { MainLayout } from './MainLayout'
import { PublicLayout } from './PublicLayout'

/**
 * Footer pages (legal, docs, status, support, security) that need to work from
 * two places:
 *
 * - inside the app, where they must keep the sidebar and top bar intact, and
 * - from the landing page, where they must stay in the minimal public shell.
 *
 * The shell is chosen from the navigation origin: a page opened from the public
 * landing surface (marked `public` on `location.state`) stays public even if a
 * demo session happens to be active, so a visitor never lands in an app sidebar
 * they did not ask for. Every page gets a "Return to …" link back to where it
 * was opened from.
 *
 * Admins in the admin view are sent to the admin console's own support and
 * security pages, since the user-facing ones call the user API (which the
 * backend rejects while the admin view is active).
 */
export function AdaptiveLayout() {
  const { isAuthenticated } = useAuth0()
  const demo = useDemoMode()
  const { view } = useView()
  const location = useLocation()

  if (isAuthenticated && view === 'admin') {
    if (location.pathname === '/support') {
      return <Navigate to="/admin/support" replace />
    }
    if (location.pathname === '/security') {
      return <Navigate to="/admin/security-reports" replace />
    }
  }

  const content = (
    <>
      <div className="mx-auto w-full max-w-[1440px] px-6 pt-5 lg:px-8">
        <ReturnLink />
      </div>
      <Outlet />
    </>
  )

  const origin = (location.state ?? null) as OriginState | null
  // Opened from the landing/architecture surface → keep the public shell even
  // when a demo session or login happens to be active.
  const openedFromPublic =
    origin?.public === true ||
    origin?.from === '/' ||
    origin?.from === '/architecture'
  const inApp = isAuthenticated || demo

  if (inApp && !openedFromPublic) {
    return <MainLayout>{content}</MainLayout>
  }

  return <PublicLayout>{content}</PublicLayout>
}

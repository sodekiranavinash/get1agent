import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import { useDemoMode } from '../auth/useDemoMode'
import { useView } from '../auth/ViewProvider'
import { MainLayout } from './MainLayout'
import { PublicLayout } from './PublicLayout'

/**
 * Footer pages (legal, docs, status, support, security) that need to work from
 * two places:
 *
 * - inside the app, where they must keep the sidebar and top bar intact, and
 * - from the sign-in screen, where there is no workspace shell yet.
 *
 * It renders the real app shell for signed-in users (and the read-only demo)
 * and falls back to the minimal public shell for everyone else.
 *
 * Admins in the admin view are sent to the admin console's own support and
 * security pages, since the user-facing ones call the user API (which the
 * backend rejects while the admin view is active).
 */
export function AdaptiveLayout() {
  const { isAuthenticated } = useAuth0()
  const demo = useDemoMode()
  const { view } = useView()
  const { pathname } = useLocation()

  if (isAuthenticated && view === 'admin') {
    if (pathname === '/support') {
      return <Navigate to="/admin/support" replace />
    }
    if (pathname === '/security') {
      return <Navigate to="/admin/security-reports" replace />
    }
  }

  if (isAuthenticated || demo) {
    return (
      <MainLayout>
        <Outlet />
      </MainLayout>
    )
  }

  return (
    <PublicLayout>
      <Outlet />
    </PublicLayout>
  )
}

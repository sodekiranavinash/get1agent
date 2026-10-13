import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useView } from './ViewProvider'
import { useDemoMode } from './useDemoMode'

/**
 * User-view route group. An admin who chose the admin view is redirected to
 * the console; someone who hasn't chosen a view is sent to the picker. The
 * user APIs independently require the user view.
 */
export function RequireUser() {
  const { view } = useView()
  const demo = useDemoMode()
  const location = useLocation()
  if (demo) return <Outlet />
  if (view === null) {
    // Carry the page they wanted through the picker: a fresh login always lands
    // on it, so this is the last place a deep link can be lost.
    return (
      <Navigate
        to="/select-view"
        replace
        state={{
          returnTo: `${location.pathname}${location.search}${location.hash}`,
        }}
      />
    )
  }
  if (view !== 'user') return <Navigate to="/admin/mcp-tools" replace />
  return <Outlet />
}

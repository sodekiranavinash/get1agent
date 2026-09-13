import { Navigate, Outlet } from 'react-router-dom'
import { useView } from './ViewProvider'

/**
 * User-view route group. An admin who chose the admin view is redirected to
 * the console; someone who hasn't chosen a view is sent to the picker. The
 * user APIs independently require the user view.
 */
export function RequireUser() {
  const { view } = useView()
  if (view === null) return <Navigate to="/select-view" replace />
  if (view !== 'user') return <Navigate to="/admin/mcp-tools" replace />
  return <Outlet />
}

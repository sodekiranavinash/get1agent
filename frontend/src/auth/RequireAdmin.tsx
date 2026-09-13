import { Navigate, Outlet } from 'react-router-dom'
import { useView } from './ViewProvider'

/**
 * Admin-view route group. A user in the user view is redirected to their
 * dashboard; someone who hasn't chosen a view is sent to the picker. The
 * admin APIs independently require the admin view.
 */
export function RequireAdmin() {
  const { view } = useView()
  if (view === null) return <Navigate to="/select-view" replace />
  if (view !== 'admin') return <Navigate to="/dashboard" replace />
  return <Outlet />
}

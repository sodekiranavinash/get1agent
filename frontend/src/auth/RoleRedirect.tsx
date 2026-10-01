import { Navigate } from 'react-router-dom'
import { useView } from './ViewProvider'
import { useDemoMode } from './useDemoMode'

/**
 * Landing decision after login: send the user to the view picker if a choice
 * is still needed, otherwise to the selected view's home page.
 */
export function RoleRedirect() {
  const { view } = useView()
  const demo = useDemoMode()
  // The read-only demo always lands on the dashboard (no view picker).
  if (demo) return <Navigate to="/dashboard" replace />
  if (view === null) return <Navigate to="/select-view" replace />
  return (
    <Navigate
      to={view === 'admin' ? '/admin/mcp-tools' : '/dashboard'}
      replace
    />
  )
}

import { Navigate } from 'react-router-dom'
import { useView } from './ViewProvider'

/**
 * Landing decision after login: send the user to the view picker if a choice
 * is still needed, otherwise to the selected view's home page.
 */
export function RoleRedirect() {
  const { view } = useView()
  if (view === null) return <Navigate to="/select-view" replace />
  return (
    <Navigate
      to={view === 'admin' ? '/admin/mcp-tools' : '/dashboard'}
      replace
    />
  )
}

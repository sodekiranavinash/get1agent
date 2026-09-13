import { Sidebar } from '../../layouts/Sidebar'
import {
  adminSectionOrder,
  adminSections,
  adminSidebarLinks,
} from '../navigation/adminSidebarLinks'

/** Admin console sidebar: same shell as the app, one item for now. */
export function AdminSidebar() {
  return (
    <Sidebar
      links={adminSidebarLinks}
      sections={adminSections}
      order={adminSectionOrder}
      homePath="/admin/mcp-tools"
      settingsPath={null}
    />
  )
}

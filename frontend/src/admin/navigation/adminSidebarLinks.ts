import { Plug } from 'lucide-react'
import type { SidebarLink } from '../../navigation/sidebarLinks'

/** Sidebar config for the admin console (extend as more admin pages land). */
export const adminSections: Record<string, string> = {
  admin: 'Admin',
}

export const adminSidebarLinks: SidebarLink[] = [
  {
    to: '/admin/mcp-tools',
    label: 'MCP Tools',
    tooltip: 'MCP Tools',
    icon: Plug,
    section: 'admin',
  },
]

export const adminSectionOrder: string[] = ['admin']

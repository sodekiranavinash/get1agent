import { useMemo } from 'react'
import { Sidebar } from '../../layouts/Sidebar'
import { useMcpTools } from '../lib/mcpAdmin'
import { adminSectionOrder, adminSections, buildAdminLinks } from '../navigation/adminSidebarLinks'

/**
 * Admin console sidebar: the "MCP Tools" group expands into one entry per MCP
 * server (discovered from the tools list), each pointing at its own test page.
 */
export function AdminSidebar() {
  // Cache-only: the MCP page owns the fetch so its loading state is not masked
  // by the sidebar prefetching the same query on mount.
  const { data, isPending } = useMcpTools({ enabled: false })
  const links = useMemo(() => buildAdminLinks(data?.tools), [data?.tools])

  return (
    <Sidebar
      links={links}
      sections={adminSections}
      order={adminSectionOrder}
      homePath="/admin/mcp-tools"
      loading={isPending}
    />
  )
}

import {
  Code2,
  Coins,
  Download,
  FileStack,
  Globe,
  LifeBuoy,
  Plug,
  Server,
  ShieldAlert,
  type LucideIcon,
} from 'lucide-react'
import type { SidebarLink } from '../../navigation/sidebarLinks'
import type { McpTool } from '../lib/mcpAdmin'

/**
 * Sidebar config for the admin console. There is no visible section header —
 * the "MCP" group already carries the context — so the map stays empty and the
 * sidebar simply renders the group on its own.
 */
export const adminSections: Record<string, string> = {}

export const adminSectionOrder: string[] = ['admin']

/** Root route for the MCP tester; per-server pages hang off this path. */
export const MCP_TOOLS_PATH = '/admin/mcp-tools'

/** Admin route for AI-credit management. */
export const ADMIN_USERS_PATH = '/admin/users'

/** Admin route for the support inbox. */
export const ADMIN_SUPPORT_PATH = '/admin/support'

/** Admin route for the security-report inbox. */
export const ADMIN_SECURITY_PATH = '/admin/security-reports'

/** `get1agent-prod-knowledge-mcp` -> `knowledge-mcp` (stable route segment). */
export function mcpServerSlug(server: string): string {
  return server.replace(/^get1agent-(?:prod|local)-/, '')
}

export type McpServerMeta = {
  label: string
  description: string
  icon: LucideIcon
}

const SERVER_META: Record<string, McpServerMeta> = {
  'knowledge-mcp': {
    label: 'Knowledge',
    description: "Query and search the caller's knowledge bases.",
    icon: FileStack,
  },
  'web-search': {
    label: 'Web Search',
    description: 'Search the live web with Exa.',
    icon: Globe,
  },
  'code-interpreter': {
    label: 'Code Interpreter',
    description: 'Run Python in an isolated sandbox.',
    icon: Code2,
  },
  'http-fetch': {
    label: 'HTTP Fetch',
    description: 'Fetch a public URL and read stored files.',
    icon: Download,
  },
}

function titleize(value: string): string {
  return value.replace(/[-_]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

export function serverMeta(server: string): McpServerMeta {
  const slug = mcpServerSlug(server)
  return (
    SERVER_META[slug] ?? {
      label: titleize(slug),
      description: `Tools exposed by ${server}.`,
      icon: Server,
    }
  )
}

export type McpServerGroup = {
  server: string
  slug: string
  tools: McpTool[]
}

/** Group tools by their owning MCP server, preserving first-seen order. */
export function groupToolsByServer(tools: McpTool[] = []): McpServerGroup[] {
  const groups = new Map<string, McpServerGroup>()
  for (const tool of tools) {
    const server = tool.server ?? 'unknown'
    const existing = groups.get(server)
    if (existing) existing.tools.push(tool)
    else groups.set(server, { server, slug: mcpServerSlug(server), tools: [tool] })
  }
  return Array.from(groups.values())
}

/** Build the admin sidebar: one "MCP Tools" group with a server per child. */
export function buildAdminLinks(tools?: McpTool[]): SidebarLink[] {
  const children = groupToolsByServer(tools).map((group) => ({
    to: `${MCP_TOOLS_PATH}/${group.slug}`,
    label: serverMeta(group.server).label,
  }))

  return [
    {
      to: MCP_TOOLS_PATH,
      label: 'MCP',
      tooltip: 'MCP',
      icon: Plug,
      section: 'admin',
      children,
    },
    {
      to: ADMIN_USERS_PATH,
      label: 'AI Credits',
      tooltip: 'AI Credits',
      icon: Coins,
      section: 'admin',
    },
    {
      to: ADMIN_SUPPORT_PATH,
      label: 'Support',
      tooltip: 'Support inbox',
      icon: LifeBuoy,
      section: 'admin',
    },
    {
      to: ADMIN_SECURITY_PATH,
      label: 'Security',
      tooltip: 'Security reports',
      icon: ShieldAlert,
      section: 'admin',
    },
  ]
}

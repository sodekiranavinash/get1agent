import { Code2, Globe, List, Search, Wrench, type LucideIcon } from 'lucide-react'

/** Friendly labels for the MCP tools shown across the admin tester. */
const TOOL_LABELS: Record<string, string> = {
  'get-user-knowledge-bases': 'List knowledge bases',
  'search-user-knowledge-bases': 'Search knowledge bases',
  'code-interpreter': 'Code interpreter',
  'web-search': 'Web search',
}

const TOOL_ICONS: Record<string, LucideIcon> = {
  'get-user-knowledge-bases': List,
  'search-user-knowledge-bases': Search,
  'code-interpreter': Code2,
  'web-search': Globe,
}

export function toolLabel(name: string): string {
  return (
    TOOL_LABELS[name] ??
    name.replace(/[-_]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
  )
}

export function toolIcon(name: string): LucideIcon {
  return TOOL_ICONS[name] ?? Wrench
}

/**
 * Tools with a long argument list keep only the everyday fields visible and
 * collapse everything from this field onward into an "Advanced options"
 * section. The field name must match the tool's `inputSchema` key.
 */
const ADVANCED_FROM: Record<string, string> = {
  'web-search': 'includeDomains',
}

export function advancedFrom(toolName: string): string | undefined {
  return ADVANCED_FROM[toolName]
}

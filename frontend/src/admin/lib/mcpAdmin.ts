import { useCallback } from 'react'
import { usePageQuery } from '../../hooks/usePageQuery'
import { useApiClient } from '../../lib/api'

export type McpProperty = {
  type?: string
  description?: string
  enum?: string[]
  items?: { type?: string }
  default?: unknown
}

export type McpInputSchema = {
  type?: string
  properties?: Record<string, McpProperty>
  required?: string[]
}

export type McpTool = {
  name: string
  description?: string
  inputSchema?: McpInputSchema
  /** The MCP server function that exposes this tool. */
  server?: string
}

export type McpToolsResponse = {
  ok: boolean
  tools: McpTool[]
  servers?: unknown[]
  userId?: string
  error?: { code?: number; message?: string }
  request?: unknown
  response?: unknown
  durationMs: number
}

export type McpCallResponse = {
  ok: boolean
  tool: string
  server?: string
  userId?: string
  arguments: Record<string, unknown>
  result?: unknown
  data?: unknown
  error?: { code?: number; message?: string }
  request: unknown
  response: unknown
  durationMs: number
}

export const MCP_TOOLS_QUERY_KEY = 'admin-mcp-tools'

export function useMcpTools(options?: { enabled?: boolean }) {
  const api = useApiClient()
  return usePageQuery(
    MCP_TOOLS_QUERY_KEY,
    () => api.get<McpToolsResponse>('/v1/admin/mcp/tools'),
    { refetchOnMount: true, enabled: options?.enabled ?? true },
  )
}

/** Returns a stable caller for the admin MCP `tools/call` endpoint. */
export function useMcpCaller() {
  const api = useApiClient()
  return useCallback(
    (name: string, args: Record<string, unknown>) =>
      api.post<McpCallResponse>('/v1/admin/mcp/call', {
        name,
        arguments: args,
      }),
    [api],
  )
}

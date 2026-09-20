import { type ApiClient } from './api'
import { invalidateQuery } from './query'

export const MCP_CONNECTIONS_QUERY_KEY = 'mcp-connections'
export const MCP_CATALOG_QUERY_KEY = 'mcp-catalog'

export type McpConnectionStatus =
  | 'pending'
  | 'connected'
  | 'reauth_required'
  | 'error'

export type McpAuthType = 'oauth' | 'none' | 'apikey'

export type McpServerOrigin = 'builtin' | 'remote' | 'marketplace' | 'public' | 'registry'

export type McpConnection = {
  id: string
  name: string
  description: string | null
  serverUrl: string
  transport: string
  authType: McpAuthType
  catalogId: string | null
  status: McpConnectionStatus
  enabled: boolean
  toolCount: number
  lastError: string | null
  lastRefreshedAt: string | null
  createdAt: string
  updatedAt: string
}

export type McpCatalogServer = {
  id: string
  name: string
  description: string
  category: string | null
  source: 'public' | 'marketplace'
  docsUrl: string | null
  serverUrl: string
  transport: string
  authType: string
}

export type McpTool = {
  name: string
  description?: string | null
  inputSchema?: unknown
  enabled: boolean
}

export type McpRegistryServer = {
  id: string
  name: string
  description: string
  category: string | null
  source: 'public' | 'marketplace'
  docsUrl: string | null
  serverUrl: string
  transport: string
  auth?: 'oauth' | 'none' | 'unknown' | null
}

export type McpRegistryResult = {
  servers: McpRegistryServer[]
  nextCursor: string | null
}

export type StartConnectionResult = {
  connection: McpConnection
  authorizationUrl: string | null
}

// --- API calls ---------------------------------------------------------------

export async function startMcpConnection(
  api: ApiClient,
  payload: { name?: string; url?: string; catalogId?: string; description?: string },
): Promise<StartConnectionResult> {
  return api.post<StartConnectionResult>('/v1/mcp/connections', payload)
}

export async function deleteMcpConnection(api: ApiClient, id: string): Promise<void> {
  await api.delete(`/v1/mcp/connections/${id}`)
}

export async function setMcpConnectionEnabled(
  api: ApiClient,
  id: string,
  enabled: boolean,
): Promise<McpConnection> {
  return api.patch<McpConnection>(`/v1/mcp/connections/${id}`, { enabled })
}

export async function refreshMcpConnection(
  api: ApiClient,
  id: string,
): Promise<McpConnection> {
  return api.post<McpConnection>(`/v1/mcp/connections/${id}/refresh`)
}

export async function authorizeMcpConnection(
  api: ApiClient,
  id: string,
): Promise<StartConnectionResult> {
  return api.post<StartConnectionResult>(`/v1/mcp/connections/${id}/authorize`)
}

export async function setMcpApiKey(
  api: ApiClient,
  id: string,
  token: string,
): Promise<McpConnection> {
  return api.post<McpConnection>(`/v1/mcp/connections/${id}/token`, { token })
}

export async function fetchMcpTools(api: ApiClient, id: string): Promise<McpTool[]> {
  const cached = toolsCache.get(id)
  if (cached) return cached
  const response = await api.get<{ tools: McpTool[] }>(`/v1/mcp/connections/${id}/tools`)
  toolsCache.set(id, response.tools)
  return response.tools
}

/**
 * Tool schemas are stable for a connection, so they are fetched once per
 * session and reused. This avoids re-hitting the connection endpoint (and
 * flashing a spinner) every time a dialog is opened.
 */
const toolsCache = new Map<string, McpTool[]>()

export function getCachedMcpTools(id: string): McpTool[] | undefined {
  return toolsCache.get(id)
}

export function invalidateMcpTools(id?: string): void {
  if (id) toolsCache.delete(id)
  else toolsCache.clear()
}

export async function setMcpToolEnabled(
  api: ApiClient,
  id: string,
  name: string,
  enabled: boolean,
): Promise<McpTool[]> {
  const response = await api.patch<{ tools: McpTool[] }>(
    `/v1/mcp/connections/${id}/tools`,
    { name, enabled },
  )
  toolsCache.set(id, response.tools)
  return response.tools
}

export async function searchMcpRegistry(
  api: ApiClient,
  params: { search?: string; cursor?: string; limit?: number; auth?: 'oauth' | 'none' } = {},
): Promise<McpRegistryResult> {
  const query = new URLSearchParams()
  if (params.search) query.set('search', params.search)
  if (params.cursor) query.set('cursor', params.cursor)
  if (params.limit) query.set('limit', String(params.limit))
  if (params.auth) query.set('auth', params.auth)
  const suffix = query.toString()
  return api.get<McpRegistryResult>(`/v1/mcp/registry${suffix ? `?${suffix}` : ''}`)
}

// --- hooks -------------------------------------------------------------------

export function invalidateMcpConnections(): void {
  invalidateQuery(MCP_CONNECTIONS_QUERY_KEY)
  invalidateMcpTools()
}

/**
 * Open the provider's authorization page in a popup and resolve when the SPA
 * callback posts back. The backend owns the token exchange; the popup only
 * carries the user through consent.
 */
export function openMcpOAuthPopup(authorizationUrl: string): Promise<boolean> {
  return new Promise((resolve) => {
    const popup = window.open(
      authorizationUrl,
      'mcp-oauth',
      'width=600,height=760,menubar=no,toolbar=no',
    )
    if (!popup) {
      resolve(false)
      return
    }

    let settled = false
    const finish = (ok: boolean) => {
      if (settled) return
      settled = true
      window.removeEventListener('message', onMessage)
      window.clearInterval(poll)
      resolve(ok)
    }

    const onMessage = (event: MessageEvent) => {
      if (event.origin !== window.location.origin) return
      const data = event.data as { type?: string; status?: string } | null
      if (data?.type !== 'mcp-oauth') return
      finish(data.status === 'connected')
    }
    window.addEventListener('message', onMessage)

    // Fallback for a closed popup (the message may never arrive).
    const poll = window.setInterval(() => {
      if (popup.closed) finish(false)
    }, 500)
  })
}

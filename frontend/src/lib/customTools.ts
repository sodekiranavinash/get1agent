import { useApiClient, type ApiClient } from './api'
import { invalidateQuery, useQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'

export const CUSTOM_TOOLS_QUERY_KEY = 'custom-tools'

// Keep these in sync with backend/services/apis/user-api/src/custom_tools/spec.py.
export const MAX_CUSTOM_SERVERS_PER_USER = 20
export const MAX_CUSTOM_TOOLS_PER_SERVER = 20
export const MAX_CUSTOM_TOOL_CODE_BYTES = 64 * 1024

export type JsonSchema = {
  type?: string | string[]
  properties?: Record<string, JsonSchema>
  required?: string[]
  items?: JsonSchema
  enum?: unknown[]
  description?: string
  [key: string]: unknown
}

export type CustomTool = {
  id: string
  serverId: string
  name: string
  description: string
  inputSchema: JsonSchema
  outputSchema: JsonSchema
  entrypoint: string
  code?: string
  createdAt: string
  updatedAt: string
}

export type CustomServer = {
  id: string
  name: string
  slug: string
  description: string
  toolCount: number
  tools: CustomTool[]
  createdAt: string
  updatedAt: string
}

export type CustomToolsUsage = {
  servers: number
  tools: number
  limits: { servers: number; toolsPerServer: number; codeBytes: number }
}

export type CustomToolsList = {
  servers: CustomServer[]
  usage: CustomToolsUsage
}

export type GeneratedTool = {
  name: string
  description: string
  code: string
  inputSchema: JsonSchema
  outputSchema: JsonSchema
}

export type CustomToolError = {
  code?: string
  message?: string
  detail?: string
  traceback?: string
}

export type CustomToolTestResult = {
  ok: boolean
  result?: unknown
  error?: CustomToolError
  outputSchemaErrors?: string[]
  output?: string
  durationMs?: number
}

export type CustomToolPayload = {
  name: string
  description: string
  code: string
  inputSchema: JsonSchema
  outputSchema: JsonSchema
  entrypoint?: string
}

export const EMPTY_SCHEMA: JsonSchema = { type: 'object', properties: {} }

/** Build a test-arguments skeleton from a tool's input schema. */
export function skeletonFromSchema(schema: JsonSchema | undefined): Record<string, unknown> {
  const properties = schema?.properties ?? {}
  const result: Record<string, unknown> = {}
  for (const [name, prop] of Object.entries(properties)) {
    result[name] = sampleValue(prop)
  }
  return result
}

function sampleValue(prop: JsonSchema): unknown {
  if (prop.enum?.length) return prop.enum[0]
  const type = Array.isArray(prop.type) ? prop.type[0] : prop.type
  switch (type) {
    case 'integer':
    case 'number':
      return 0
    case 'boolean':
      return false
    case 'array':
      return []
    case 'object':
      return skeletonFromSchema(prop)
    default:
      return ''
  }
}

// --- API calls ---------------------------------------------------------------

export async function fetchCustomServers(api: ApiClient): Promise<CustomToolsList> {
  return api.get<CustomToolsList>('/v1/custom-tools')
}

export async function fetchCustomServer(api: ApiClient, id: string): Promise<CustomServer> {
  return api.get<CustomServer>(`/v1/custom-tools/${id}`)
}

export async function createCustomServer(
  api: ApiClient,
  payload: { name: string; description?: string },
): Promise<CustomServer> {
  return api.post<CustomServer>('/v1/custom-tools', payload)
}

export async function updateCustomServer(
  api: ApiClient,
  id: string,
  payload: { name: string; description?: string },
): Promise<CustomServer> {
  return api.put<CustomServer>(`/v1/custom-tools/${id}`, payload)
}

export async function deleteCustomServer(api: ApiClient, id: string): Promise<void> {
  await api.delete(`/v1/custom-tools/${id}`)
}

export async function fetchCustomTool(
  api: ApiClient,
  serverId: string,
  toolId: string,
): Promise<CustomTool> {
  return api.get<CustomTool>(`/v1/custom-tools/${serverId}/tools/${toolId}`)
}

export async function createCustomTool(
  api: ApiClient,
  serverId: string,
  payload: CustomToolPayload,
): Promise<CustomTool> {
  return api.post<CustomTool>(`/v1/custom-tools/${serverId}/tools`, payload)
}

export async function updateCustomTool(
  api: ApiClient,
  serverId: string,
  toolId: string,
  payload: CustomToolPayload,
): Promise<CustomTool> {
  return api.put<CustomTool>(`/v1/custom-tools/${serverId}/tools/${toolId}`, payload)
}

export async function deleteCustomTool(
  api: ApiClient,
  serverId: string,
  toolId: string,
): Promise<void> {
  await api.delete(`/v1/custom-tools/${serverId}/tools/${toolId}`)
}

export async function generateCustomTool(
  api: ApiClient,
  payload: {
    description: string
    code?: string
    inputSchema?: JsonSchema
    outputSchema?: JsonSchema
    lastError?: string
  },
): Promise<GeneratedTool> {
  return api.post<GeneratedTool>('/v1/custom-tools/generate', payload)
}

export async function testCustomTool(
  api: ApiClient,
  payload: {
    code?: string
    toolId?: string
    args: Record<string, unknown>
    inputSchema?: JsonSchema
    outputSchema?: JsonSchema
    entrypoint?: string
  },
): Promise<CustomToolTestResult> {
  return api.post<CustomToolTestResult>('/v1/custom-tools/test', payload)
}

// --- hooks -------------------------------------------------------------------

export function useCustomTools() {
  const api = useApiClient()
  return usePageQuery(
    CUSTOM_TOOLS_QUERY_KEY,
    () => fetchCustomServers(api),
    { refetchOnMount: true },
  )
}

/** Custom servers for the agent builder's tools node. */
export function useCustomServerOptions() {
  const api = useApiClient()
  const query = useQuery(CUSTOM_TOOLS_QUERY_KEY, () => fetchCustomServers(api))
  return { servers: query.data?.servers ?? [], refetch: query.refetch }
}

export function invalidateCustomTools(): void {
  invalidateQuery(CUSTOM_TOOLS_QUERY_KEY)
}

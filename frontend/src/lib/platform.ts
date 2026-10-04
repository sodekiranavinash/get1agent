import { type ApiClient } from './api'

/**
 * Platform capabilities surfaced from the AWS-native backend:
 * AgentCore Identity, Registry, Browser, Optimization, and the Bedrock
 * cost/latency levers. Each maps to a `/v1/...` route in user-api.
 */

// --- AgentCore Identity -------------------------------------------------------

export type IdentityStatus = {
  configured: boolean
  workloadIdentityArn: string | null
  tokenVaultId: string | null
  providers: string[]
  region: string
}

export type IdentityTokenResult = {
  provider: string
  obtained: boolean
  expiresAt: string | null
  scopes: string[]
}

export function fetchIdentity(api: ApiClient): Promise<IdentityStatus> {
  return api.get<IdentityStatus>('/v1/identity')
}

export function requestIdentityToken(
  api: ApiClient,
  payload: { provider: string; scopes?: string[] },
): Promise<IdentityTokenResult> {
  return api.post<IdentityTokenResult>('/v1/identity/token', payload)
}

// --- AgentCore Registry -------------------------------------------------------

export type RegistryStatus = {
  configured: boolean
  registryId: string | null
  registryArn: string | null
  region: string
}

export type RegistryRecord = {
  id?: string
  name?: string
  description?: string
  recordType?: string
}

export function fetchRegistry(api: ApiClient): Promise<RegistryStatus> {
  return api.get<RegistryStatus>('/v1/registry')
}

export function publishRegistryRecord(
  api: ApiClient,
  payload: {
    name: string
    description: string
    recordType: 'AGENT' | 'MCP_SERVER' | 'TOOL' | 'SKILL'
    metadata?: Record<string, unknown>
  },
): Promise<{ ok: boolean; record: unknown }> {
  return api.post('/v1/registry/publish', payload)
}

export function searchRegistry(
  api: ApiClient,
  q: string,
): Promise<{ configured: boolean; records: RegistryRecord[] }> {
  return api.get(`/v1/registry/search?q=${encodeURIComponent(q)}`)
}

// --- AgentCore Browser --------------------------------------------------------

export type BrowserStatus = {
  configured: boolean
  browserId: string | null
  region: string
  allowedDomains: string[]
  sessionTimeout: number
}

export type BrowserSession = {
  sessionId: string
  browserId: string
  liveViewUrl: string | null
  wsHeaders?: Record<string, string>
}

export function fetchBrowser(api: ApiClient): Promise<BrowserStatus> {
  return api.get<BrowserStatus>('/v1/browser')
}

export function checkBrowserUrl(
  api: ApiClient,
  url: string,
): Promise<{ allowed: boolean; reason: string }> {
  return api.post('/v1/browser/check', { url })
}

export function openBrowserSession(
  api: ApiClient,
  url: string,
): Promise<BrowserSession> {
  return api.post<BrowserSession>('/v1/browser/session', { url })
}

export function closeBrowserSession(
  api: ApiClient,
  sessionId: string,
): Promise<{ stopped: boolean }> {
  return api.post('/v1/browser/session/close', { sessionId })
}

// --- AgentCore Optimization ---------------------------------------------------

export type OptimizationStatus = {
  configured: boolean
  insightsArn: string | null
  region: string
  targets: string[]
  note: string
}

export function fetchOptimization(api: ApiClient): Promise<OptimizationStatus> {
  return api.get<OptimizationStatus>('/v1/optimization')
}

// --- Bedrock cost/latency levers ---------------------------------------------

export type BedrockFeatures = {
  promptCache: { strategy: string; ttl: string | null } | null
  serviceTier: string | null
  promptRouterArn: string | null
  applicationProfiles: Record<string, string | null>
}

export function fetchBedrockFeatures(api: ApiClient): Promise<BedrockFeatures> {
  return api.get<BedrockFeatures>('/v1/bedrock-features')
}

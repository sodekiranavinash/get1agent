import { type ApiClient } from '../../lib/api'
import {
  type BrowserSession,
  type BrowserStatus,
  type IdentityStatus,
  type IdentityTokenResult,
} from '../../lib/platform'

/**
 * Admin Platform status: the full set of AgentCore services (Identity, Registry,
 * Browser, Optimization) plus the Bedrock cost/latency levers, served by the
 * admin-console Lambda under `/v1/admin/platform/*`. These are admin-view routes
 * (no user-view header override needed).
 *
 * Identity/Browser reuse the user-facing response shapes; the shared `core.*`
 * helpers back both.
 */

const BASE = '/v1/admin/platform'

// Re-export the shared identity/browser shapes so pages only import from here.
export type {
  BrowserSession,
  BrowserStatus,
  IdentityStatus,
  IdentityTokenResult,
}

// --- Identity -----------------------------------------------------------------

export function fetchIdentity(api: ApiClient): Promise<IdentityStatus> {
  return api.get<IdentityStatus>(`${BASE}/identity`)
}

export function requestIdentityToken(
  api: ApiClient,
  payload: { provider: string; scopes?: string[] },
): Promise<IdentityTokenResult> {
  return api.post<IdentityTokenResult>(`${BASE}/identity/token`, payload)
}

// --- Registry -----------------------------------------------------------------

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
  return api.get<RegistryStatus>(`${BASE}/registry`)
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
  return api.post(`${BASE}/registry/publish`, payload)
}

export function searchRegistry(
  api: ApiClient,
  q: string,
): Promise<{ configured: boolean; records: RegistryRecord[] }> {
  return api.get(`${BASE}/registry/search?q=${encodeURIComponent(q)}`)
}

// --- Browser ------------------------------------------------------------------

export function fetchBrowser(api: ApiClient): Promise<BrowserStatus> {
  return api.get<BrowserStatus>(`${BASE}/browser`)
}

export function checkBrowserUrl(
  api: ApiClient,
  url: string,
): Promise<{ allowed: boolean; reason: string }> {
  return api.post(`${BASE}/browser/check`, { url })
}

export function openBrowserSession(
  api: ApiClient,
  url: string,
): Promise<BrowserSession> {
  return api.post<BrowserSession>(`${BASE}/browser/session`, { url })
}

export function closeBrowserSession(
  api: ApiClient,
  sessionId: string,
): Promise<{ stopped: boolean }> {
  return api.post(`${BASE}/browser/session/close`, { sessionId })
}

// --- Optimization -------------------------------------------------------------

export type OptimizationStatus = {
  configured: boolean
  insightsArn: string | null
  region: string
  targets: string[]
  note: string
}

export function fetchOptimization(api: ApiClient): Promise<OptimizationStatus> {
  return api.get<OptimizationStatus>(`${BASE}/optimization`)
}

// --- Bedrock cost/latency levers ---------------------------------------------

export type BedrockFeatures = {
  promptCache: { strategy: string; ttl: string | null } | null
  serviceTier: string | null
  promptRouterArn: string | null
  applicationProfiles: Record<string, string | null>
}

export function fetchBedrockFeatures(api: ApiClient): Promise<BedrockFeatures> {
  return api.get<BedrockFeatures>(`${BASE}/bedrock-features`)
}

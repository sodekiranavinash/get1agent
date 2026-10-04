import { type ApiClient } from './api'

/**
 * User-facing Platform status: the AgentCore services an end user can actually
 * use — Identity (their own provider tokens) and Browser (their sessions).
 * The admin-only services (Registry, Optimization and the Bedrock levers) live
 * on the admin console; see `admin/lib/adminPlatform.ts`.
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

import { API_BASE_URL } from './api'

/**
 * Resolve a run's shareable trace link to an absolute URL.
 *
 * The API returns a signed, 30-minute public link as a relative path
 * (`/trace/<token>`); live links resolve against the API origin. Returns `null`
 * when there is no trace to link to.
 */
export function traceHref(traceUrl?: string | null): string | null {
  if (!traceUrl) return null
  if (/^https?:\/\//i.test(traceUrl)) return traceUrl
  const path = traceUrl.startsWith('/') ? traceUrl : `/${traceUrl}`
  // The in-app public trace page (`/trace/<token>`) is same-origin; every other
  // relative path must resolve against the API origin.
  if (path.startsWith('/trace/')) return path
  return `${API_BASE_URL}${path}`
}

/**
 * The link a signed-in user should follow to view a run's trace.
 *
 * Prefers the signed public share link when present, but always falls back to
 * the in-app full-screen viewer (`/traces/<traceId>`) — which needs no secret
 * and is available the moment the run records its trace id (so a live run gets
 * a link without waiting for the conversation to be re-fetched).
 */
export function traceViewHref(
  traceUrl?: string | null,
  traceId?: string | null,
): string | null {
  const signed = traceHref(traceUrl)
  if (signed) return signed
  const id = (traceId || '').trim()
  return id ? `/traces/${encodeURIComponent(id)}` : null
}

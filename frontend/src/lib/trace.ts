import { API_BASE_URL } from './api'

/**
 * Resolve a run's Langfuse trace link to an absolute URL.
 *
 * The API returns a signed, 30-minute link as a relative path
 * (`/v1/traces/<token>`); live runs may carry the raw Langfuse URL instead.
 * Returns `null` when there is no trace to link to.
 */
export function traceHref(traceUrl?: string | null): string | null {
  if (!traceUrl) return null
  if (/^https?:\/\//i.test(traceUrl)) return traceUrl
  const path = traceUrl.startsWith('/') ? traceUrl : `/${traceUrl}`
  return `${API_BASE_URL}${path}`
}

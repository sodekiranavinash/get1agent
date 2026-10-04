import { useLocation } from 'react-router-dom'
import { useAuth0 } from '@auth0/auth0-react'
import { useDemoMode } from '../../auth/useDemoMode'
import { useView } from '../../auth/ViewProvider'

/**
 * Navigation origin carried on `location.state` when a link opens a secondary
 * page (docs, legal, architecture). `from` is the exact path to return to and
 * `public` marks that it was opened from the public landing surface, so the
 * destination keeps the minimal public shell instead of the app sidebar.
 */
export type OriginState = {
  from?: string
  fromLabel?: string
  public?: boolean
}

export function originState(
  from: string,
  options: { label?: string; isPublic?: boolean } = {},
): OriginState {
  return { from, fromLabel: options.label, public: options.isPublic }
}

const LABELS: Record<string, string> = {
  '/': 'home',
  '/dashboard': 'the dashboard',
  '/architecture': 'the architecture',
  '/docs': 'docs',
  '/support': 'support',
  '/status': 'status',
  '/changelog': 'the changelog',
  '/privacy': 'the privacy policy',
  '/terms': 'the terms',
  '/security': 'security',
  '/chat': 'chat',
  '/knowledge-bases': 'knowledge',
  '/agent-skills': 'skills',
  '/tools': 'MCP tools',
  '/vault': 'the Vault',
  '/usage': 'usage',
  '/traces': 'traces',
  '/evaluations': 'evaluations',
  '/metrics': 'metrics',
  '/storage': 'storage',
  '/mcp-builder': 'the MCP Builder',
  '/agent-builder': 'the agent builder',
  '/workflow-builder': 'the workflow builder',
  '/agent-store': 'agents',
  '/workflow-store': 'workflows',
  '/scheduled-jobs': 'schedules',
  '/settings': 'settings',
}

function labelFor(to: string): string {
  if (LABELS[to]) return LABELS[to]
  const segment = to.split(/[?#]/)[0].split('/').filter(Boolean)[0]
  if (!segment) return 'home'
  if (segment === 'admin') return 'the admin console'
  return LABELS[`/${segment}`] ?? 'where you came from'
}

/** The path (and label) a secondary page should send the user back to. */
export function useReturnTarget(fallbackTo?: string): {
  to: string
  label: string
} {
  const location = useLocation()
  const { isAuthenticated } = useAuth0()
  const demo = useDemoMode()
  const { view } = useView()
  const state = (location.state ?? null) as OriginState | null

  const signedInHome = view === 'admin' ? '/admin/mcp-tools' : '/dashboard'
  const fallback = fallbackTo ?? (isAuthenticated || demo ? signedInHome : '/')
  const from = state?.from
  const to = from && from !== location.pathname ? from : fallback

  return { to, label: state?.fromLabel ?? labelFor(to) }
}

import { useAuth0 } from '@auth0/auth0-react'
import type { AppView } from './view'

/**
 * Auth0 namespaced custom claims set by the Login Action. The ID token copy
 * powers the UI gates; the access token copy is what the API enforces.
 */
export const ADMIN_CLAIM = 'https://get1agent.com/isAdmin'
export const ROLES_CLAIM = 'https://get1agent.com/roles'
export const ADMIN_ROLE = 'admin'

function readBoolean(value: unknown): boolean {
  if (typeof value === 'boolean') return value
  if (typeof value === 'number') return value !== 0
  if (typeof value === 'string') {
    return ['true', '1', 'yes'].includes(
      value.replace(/[[\]"']/g, '').trim().toLowerCase(),
    )
  }
  return false
}

function cleanRole(value: unknown): string {
  return String(value).replace(/[[\]"']/g, '').trim().toLowerCase()
}

/** Accept roles as a list, a JSON array string, `[admin]`, or CSV. */
function normalizeRoles(value: unknown): string[] {
  if (value == null) return []
  if (typeof value === 'string') {
    const text = value.trim()
    if (!text) return []
    try {
      const parsed: unknown = JSON.parse(text)
      if (parsed !== value) return normalizeRoles(parsed)
    } catch {
      // not JSON; fall through to bracket/CSV parsing
    }
    return text
      .replace(/^\[|\]$/g, '')
      .split(',')
      .map(cleanRole)
      .filter(Boolean)
  }
  if (Array.isArray(value)) return value.flatMap(normalizeRoles)
  const role = cleanRole(value)
  return role ? [role] : []
}

function claimRoles(user: unknown): string[] {
  if (!user || typeof user !== 'object') return []
  const claims = user as Record<string, unknown>
  return normalizeRoles(claims[ROLES_CLAIM] ?? claims.roles)
}

/** Pure helper so routing and tests can reason about a raw Auth0 user object. */
export function isAdminUser(user: unknown): boolean {
  if (!user || typeof user !== 'object') return false
  const claims = user as Record<string, unknown>
  if (readBoolean(claims[ADMIN_CLAIM]) || readBoolean(claims.isAdmin)) return true
  return claimRoles(user).includes(ADMIN_ROLE)
}

/**
 * Views this user may enter. Everyone can use the app; the admin console is
 * additive when the `admin` role is present.
 */
export function availableViews(user: unknown): AppView[] {
  const views: AppView[] = ['user']
  if (isAdminUser(user)) views.push('admin')
  return views
}

export function useIsAdmin(): boolean {
  const { user } = useAuth0()
  return isAdminUser(user)
}

export function useAvailableViews(): AppView[] {
  const { user } = useAuth0()
  return availableViews(user)
}

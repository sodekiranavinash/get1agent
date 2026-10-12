import { type ApiClient } from '../../lib/api'

export type AdminUser = {
  userId: string
  email: string
  fullName: string
  createdAt: string | null
  isAdmin: boolean
  budgetCredits: number
  spentCredits: number
  remainingCredits: number
}

export type AdminUsersResponse = {
  users: AdminUser[]
  creditsPerUsd: number
  defaultCredits: number
  nextCursor: string | null
}

export async function fetchAdminUsers(
  api: ApiClient,
  cursor?: string,
): Promise<AdminUsersResponse> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : ''
  return api.get<AdminUsersResponse>(`/v1/admin/users${query}`)
}

/** Credit operations. `add` tops the grant up; `set` replaces it outright. */
export type CreditMode = 'add' | 'set'

/**
 * Grant AI credits. There is no unlimited mode: an admin raises the limit when
 * a user runs out (`add`, the default) or rewrites it explicitly (`set`).
 */
export async function setUserCredits(
  api: ApiClient,
  userId: string,
  credits: number,
  mode: CreditMode = 'add',
): Promise<AdminUser> {
  return api.post<AdminUser>(`/v1/admin/users/${userId}/credits`, { credits, mode })
}

/** Reset a user's spent credits back to zero. */
export async function resetUserCredits(api: ApiClient, userId: string): Promise<AdminUser> {
  return api.post<AdminUser>(`/v1/admin/users/${userId}/reset`)
}

/** A user's effective resource caps, with the platform default and override flag. */
export type LimitValue = { value: number; override: boolean }

export type UserLimits = {
  maxKnowledgeBases: LimitValue
  maxFilesPerKb: LimitValue
  maxFilesPerUser: LimitValue
  maxFileBytes: LimitValue
  maxStorageBytes: LimitValue
  counters: { kbCount: number; fileCount: number; storageBytes: number }
}

export type UserLimitsResponse = {
  userId: string
  limits: UserLimits
  budget: AdminUser
}

/** The editable caps, keyed by their API field. `null` clears the override. */
export type UserLimitsInput = Partial<{
  maxKnowledgeBases: number | null
  maxFilesPerKb: number | null
  maxFilesPerUser: number | null
  maxFileBytes: number | null
  maxStorageBytes: number | null
}>

export async function fetchUserLimits(
  api: ApiClient,
  userId: string,
): Promise<UserLimitsResponse> {
  return api.get<UserLimitsResponse>(`/v1/admin/users/${userId}/limits`)
}

/**
 * Tighten (or clear) a user's resource caps. Clearing a field falls back to the
 * platform default — this is the lever for a user who is abusing the workspace.
 */
export async function setUserLimits(
  api: ApiClient,
  userId: string,
  limits: UserLimitsInput,
): Promise<UserLimitsResponse> {
  return api.post<UserLimitsResponse>(`/v1/admin/users/${userId}/limits`, limits)
}

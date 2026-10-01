import { type ApiClient } from '../../lib/api'

export type AdminUser = {
  userId: string
  email: string
  fullName: string
  createdAt: string | null
  isAdmin: boolean
  budgetCredits: number
  spentCredits: number
  remainingCredits: number | null
  unlimited: boolean
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

/** Grant (or reduce) a user's AI credits. */
export async function setUserCredits(
  api: ApiClient,
  userId: string,
  credits: number,
): Promise<AdminUser> {
  return api.post<AdminUser>(`/v1/admin/users/${userId}/credits`, { credits })
}

/** Reset a user's spent credits back to zero. */
export async function resetUserCredits(api: ApiClient, userId: string): Promise<AdminUser> {
  return api.post<AdminUser>(`/v1/admin/users/${userId}/reset`)
}

/** Turn a user's unlimited override on or off. */
export async function setUserUnlimited(
  api: ApiClient,
  userId: string,
  unlimited: boolean,
): Promise<AdminUser> {
  return api.post<AdminUser>(`/v1/admin/users/${userId}/unlimited`, { unlimited })
}

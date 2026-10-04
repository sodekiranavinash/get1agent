import { useApiClient, type ApiClient } from './api'
import { invalidateQuery } from './query'
import { usePageQuery } from '../hooks/usePageQuery'

export const NOTIFICATIONS_QUERY_KEY = 'notifications'

/** Machine tag the SPA maps to an icon/colour. */
export type NotificationKind =
  | 'ingestion_ready'
  | 'ingestion_failed'
  | 'schedule_completed'
  | 'schedule_failed'
  | 'info'

export type AppNotification = {
  id: string
  kind: string
  title: string
  detail: string
  link?: string | null
  read: boolean
  createdAt: string
}

export type NotificationsPayload = {
  notifications: AppNotification[]
  unreadCount: number
}

export async function fetchNotifications(api: ApiClient): Promise<NotificationsPayload> {
  return api.get<NotificationsPayload>('/v1/notifications')
}

export async function markNotificationRead(api: ApiClient, id: string): Promise<void> {
  await api.post(`/v1/notifications/${encodeURIComponent(id)}/read`)
}

export async function markAllNotificationsRead(api: ApiClient): Promise<void> {
  await api.post('/v1/notifications/read-all')
}

export async function deleteNotification(api: ApiClient, id: string): Promise<void> {
  await api.delete(`/v1/notifications/${encodeURIComponent(id)}`)
}

export function useNotifications() {
  const api = useApiClient()
  return usePageQuery(NOTIFICATIONS_QUERY_KEY, () => fetchNotifications(api), {
    refetchOnMount: true,
  })
}

export function invalidateNotifications(): void {
  invalidateQuery(NOTIFICATIONS_QUERY_KEY)
}
